# SPDX-FileCopyrightText: Copyright 2026 GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Running a measurement in a throwaway process.

A GNU Radio flow graph does not give everything back when it is dropped: each one leaves
roughly 60 mmap regions and a few MB behind, whatever is done on the Python side —
`disconnect_all`, dropping the last reference and a `gc.collect()` all make no difference.
A test module that builds a couple of hundred graphs in one interpreter therefore dies of
`std::bad_alloc` inside `top_block.start()`, and takes every test that runs after it down
as well.

Running each measurement in its own process sidesteps that completely, because the leak goes
away with the child. It also isolates the runtime between measurements, which is worth
having on its own for something whose whole purpose is to produce comparable numbers.

The `forkserver` start method is used rather than plain `fork`. By the time a measurement
runs, GNU Radio has threads going, and forking a multi-threaded process risks the child
deadlocking on a lock no surviving thread will release. `forkserver` forks from a separate,
single-threaded server process instead, which costs one interpreter startup for the whole
session and nothing per measurement.
"""

import multiprocessing
import os
import traceback

# Start method and the modules the server has ready before the first measurement. Preloading
# is what keeps a child cheap: without it every measurement re-imports GNU Radio.
START_METHOD = "forkserver"
PRELOAD = ["channel", "receiver", "sample_files", "reference"]

_context = None


def _child(connection, function, args, kwargs):
    """Run the function and send its result back, then leave without cleaning up."""
    try:
        connection.send(("value", function(*args, **kwargs)))
    # deliberately broad, BaseException included: whatever goes wrong, the parent is waiting
    # on recv() and has to be told, or it hangs
    except BaseException:  # noqa: BLE001
        connection.send(("error", traceback.format_exc()))
    finally:
        connection.close()
    # _exit rather than a normal return: the child has a copy of the parent's interpreter,
    # including whatever test framework state, and none of that should run teardown twice
    os._exit(0)


def _get_context():
    """Return the process context, setting the server up on first use."""
    global _context
    if _context is None:
        _context = multiprocessing.get_context(START_METHOD)
        _context.set_forkserver_preload(PRELOAD)
    return _context


def run_isolated(function, *args, **kwargs):
    """Call `function` in a throwaway child process and return its result.

    The function is pickled by reference, so it has to be importable by name — a
    module-level function, not a lambda or a closure — and its arguments and result have to
    be picklable, which for plain data they are.
    """
    context = _get_context()
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, function, args, kwargs))
    process.start()
    sender.close()

    try:
        outcome, payload = receiver.recv()
    except EOFError:
        process.join()
        raise RuntimeError(f"isolated measurement died, exit code {process.exitcode}") from None
    finally:
        receiver.close()
        process.join()

    if outcome == "error":
        raise RuntimeError(f"isolated measurement raised:\n{payload}")
    return payload
