<!--
SPDX-FileCopyrightText: 2026 GARDENA GmbH

SPDX-License-Identifier: GPL-3.0-or-later
-->

Overview
========

This repository contains real-world samples and `pytest` tests to
verify the performance of `gr-wisun`.

Running the tests
=================

The tests need an installed `gr-wisun` (they import
`gnuradio.wisun`), GNU Radio itself, `pytest` and `numpy` — the last
comes with GNU Radio, which depends on it. None of these is pinned in
`requirements.in`; that file covers only the FOSS compliance tooling
CI installs.

```bash
pytest
```

Samples
=======

The directory `samples/` contains recorded samples of Wi-SUN packets
sent with various modes. A description of the individual files (data
rate, content, ..) can be found in `sample_files.py`.

The samples have been recorded with a Nuand bladeRF 2.0 micro.

Tests with a channel model
==========================

`test_single_channel_noise.py` runs the same recordings through
`channels.channel_model` before receiving them, which is the only way
this repository says anything about a signal that is not already good.
It checks two separate things:

- **nothing is invented.** Every packet that comes out must have a
  length the recording contains, and for the coded samples a valid
  frame check sequence. Noise must cost packets, never produce wrong
  ones. This holds well below the point where anything still decodes,
  and it barely moves with the noise seed, so it is the sharp check.
- **nothing collapses.** At least a floor fraction of the packets must
  still be decoded. The floors are recorded from a measured baseline
  with margin: they say "no worse than it was", not "as good as it
  should be".

Noise is specified as a *wideband* signal-to-noise ratio — burst power
over added noise power in the full recording bandwidth, at the input of
the receiver. The receive chain's channel filter then throws most of
that noise away, so the ratio the bit slicer sees is a good deal
better. `channel.py` measures the burst power of each file so that one
ratio means the same thing across recordings whose absolute levels
differ by some 75 dB, and `test_channel.py` pins down the conversion
against the block itself rather than trusting it.

Carrier frequency offset and sample clock error are exercised through
the same harness, with the "nothing is invented" check only.

Reading the curve
-----------------

The floors come from a sweep, which is a measurement rather than an
assertion and so is deselected by default:

```bash
pytest -m sweep -s
```

That prints decode rate against signal-to-noise ratio for every sample
file. To re-derive the floors after a change to `gr-wisun`, run it
before and after, and set each floor in `MINIMUM_DECODE_RATE` below the
new measurement — roughly half of it wherever the baseline is far from
1.0, since those points sit on a cliff and move a long way for a small
change anywhere in the chain.

Note that these numbers are not directly comparable with the
clean-sample tests: `channel_model` puts an `mmse_resampler` in the
path even with no impairment at all, and on these recordings that
alone is enough to cost one marginal packet.

Each measurement runs in a throwaway process (`isolation.py`). A GNU
Radio flow graph does not give everything back when it is dropped —
roughly 60 mmap regions and a few MB each — so a module building a
couple of hundred of them in one interpreter dies of `std::bad_alloc`
inside `top_block.start()` and takes every later test with it.
