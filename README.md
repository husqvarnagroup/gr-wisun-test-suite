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

`samples/single_channel/` holds recordings of one channel, described by
a tuning offset in `fileinfo`. `samples/multi_channel/` holds wideband
recordings covering a whole channel plan, described by their Wi-SUN
configuration in `multi_channel_fileinfo` — the channel set, spacing and
symbol rate follow from the regulatory domain, channel plan and PHY
mode, as they do for the sniffer applications.

A wideband recording costs 64 MB per second at 8 MS/s, so the idle
stretches between packets are cut out, leaving a short dead time around
each burst. Verify after cutting that the receiver still decodes the
same packets: the squelch tracks a noise floor and the DC correction
estimates per burst, so both need some idle signal to work with.

Tests covering many channels
============================

`test_multi_channel_samples.py` drives `multi_channel_receiver`, i.e.
the polyphase channelizer plus one receive chain per channel, which the
single-channel tests never reach. Two properties only show up there:

- **the samples per symbol the channelizer leaves.** Its normal output
  rate is the channel spacing, which is twice the symbol rate for every
  Wi-SUN FSK mode, and 2 samples per symbol costs packets. The complete
  decode is asserted at the oversampling that achieves it; the default,
  which trades packets for the headroom to keep up with an SDR, gets a
  floor of its own.
- **channels the regulatory mask excludes.** Devices do transmit there,
  so the receiver listens and reports; a test asserts packets on those
  channels come through rather than being dropped.
- **what too much gain does.** One recording was deliberately made at too
  high a gain. Its input clips, one request was retransmitted after going
  unacknowledged, and three frames appear a second time 5 MHz above their
  own channel, 25 to 27 dB down — the spurious emission of one of the two
  devices, which the gain lifted above the noise rather than created.
  Tests pin the clipping count, the frames whose check sequence fails, and
  the one copy that is bit-exact and so can only be found by having been
  received already.

The receiver's output is a pcapng stream rather than bare packets, so
`pcapng.py` reads it the way Wireshark would. That also checks the
stream itself — a repeated interface description block, say, fails a
test here rather than being noticed in Wireshark. Each packet carries its
own frame check sequence, the TAP header says how wide it is, and the
packet flags carry the receiver's own verdict, so a corrupted frame can
be told from a good one.

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
the same harness. At native recording signal-to-noise ratio neither
costs a packet within the ranges tested, so alongside the "nothing is
invented" check, both are also swept at a fixed, already-lossy signal-
to-noise ratio (`FIXED_IMPAIRMENT_SNR_DB`) with their own decode-rate
floors, `MINIMUM_DECODE_RATE_CARRIER_OFFSET` and
`MINIMUM_DECODE_RATE_CLOCK_ERROR`.

Bit error rate
--------------

The decode-rate floors above are a packet-error-rate measure: a packet
either comes out intact or it does not count. `test_single_channel_noise.py`
additionally measures bit error rate among the packets that do still
decode, against a reference derived from a clean (unimpaired) decode of
each file (`reference.py`) and checked by its own frame check sequence
before being trusted. This is a separate question from decode rate — a
packet that never frames contributes to the packet-error-rate side, not
to the bit error count, since there is no bit alignment to compare
without a frame — and the two must not be combined into one rate.
Ceilings live in `MAXIMUM_BIT_ERROR_RATE`, one per file and signal-to-
noise ratio.

Reading the curves
-------------------

The floors and ceilings above come from a sweep, which is a measurement
rather than an assertion and so is deselected by default:

```bash
pytest -m sweep -s
```

That prints decode rate or bit error rate against signal-to-noise
ratio, carrier offset or clock error, for every sample file (one sweep
function per metric and impairment axis). To re-derive a floor or
ceiling after a change to `gr-wisun`, run the matching sweep before and
after, and set each value in the matching dictionary below the new
measurement — roughly half of it wherever the baseline is far from 1.0
(for a decode-rate floor), since those points sit on a cliff and move a
long way for a small change anywhere in the chain. Bit error rate has
been exactly zero at every point measured so far — a packet that still
frames and passes its own checks has not been seen to carry a wrong
bit — so its ceilings are a small fixed margin rather than half the
baseline.

Note that these numbers are not directly comparable with the
clean-sample tests: `channel_model` puts an `mmse_resampler` in the
path even with no impairment at all, and on these recordings that
alone is enough to cost one marginal packet.

Each measurement runs in a throwaway process (`isolation.py`). A GNU
Radio flow graph does not give everything back when it is dropped —
roughly 60 mmap regions and a few MB each — so a module building a
couple of hundred of them in one interpreter dies of `std::bad_alloc`
inside `top_block.start()` and takes every later test with it.
