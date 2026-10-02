# SPDX-FileCopyrightText: Copyright 2026 GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests with recorded samples put through a channel model before being received.

The other test modules run the recordings as they were captured, which says nothing about
what happens once the signal is poor. These run the same recordings through
`channels.channel_model` first, on the per-file calibrated scale `channel.py` defines, and
check two different things:

- every packet that comes out is still a real packet: a length the recording contains, and
  for the coded samples a valid frame check sequence. This is the sharp check — noise must
  cost packets, never invent them — and it holds at ratios far below the point where
  anything is still decoded, which is where it matters most.
- at least a floor fraction of packets still comes out. This is the loose check. It exists
  to catch a collapse of the receive chain, not to pin down a decode rate: the floors come
  from a measured baseline with margin, so they say "no worse than it was" rather than "as
  good as it should be". Only ratios where the baseline actually decodes something carry a
  floor, since a floor of zero asserts nothing.

Several recordings hold packets at two levels, because the device under test had extra
attenuation relative to the router. Those files lose roughly half their packets some 10 dB
before the other half, so a rate near 0.5 partway down is the expected shape rather than a
sign of trouble.

Run `pytest -m sweep -s` for the curve these floors were read off; see README.md.
"""

from functools import cache

import pmt
import pytest

from channel import ChannelImpairment, measure_power
from isolation import run_isolated
from receiver import single_channel_packet_receiver
from reference import best_match, hamming_distance, reference_packets
from sample_files import fileinfo, uses_fec

# Signal-to-noise ratios to test, in dB, wideband at the receiver input — see channel.py for
# what that means. The receive chain breaks down between 15 dB and 10 dB for most
# recordings, so this brackets the interesting region and then goes well past it, because
# the "no invented packets" check is most valuable where nothing should decode at all.
SNR_LEVELS = (20, 15, 12, 10, 6)

# Noise seeds each point is run with. The recordings hold only 4 to 21 packets, so a single
# run gives a decode rate far too coarse to assert on; a fixed list keeps the aggregate
# deterministic while giving it some resolution.
SEEDS = (1, 2, 3)

# Decimation to test at. Both the coded and the uncoded clean-sample tests pass here, and it
# is the cheaper of the two they share.
DECIMATION = 2

# Minimum fraction of packets that must still be decoded, per file and signal-to-noise
# ratio, with the measured baseline each floor was derived from beside it. Ratios where the
# baseline decodes nothing are left out rather than given a floor of zero.
#
# Points whose baseline is well below 1.0 sit on a cliff and move a long way for a small
# change anywhere in the chain, so their floors are set at roughly half the baseline and do
# no more than catch a collapse. Points near 1.0 are held close.
MINIMUM_DECODE_RATE = {
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': {
        20: 0.90,  # 0.98
        15: 0.90,  # 0.98
        12: 0.90,  # 1.00
        10: 0.90,  # 1.00
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile': {
        20: 0.95,  # 1.00
        15: 0.95,  # 1.00
        12: 0.90,  # 0.98
        10: 0.30,  # 0.49
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile': {
        20: 0.95,  # 1.00
        15: 0.90,  # 1.00
        12: 0.35,  # 0.56
    },
    'samples/single_channel/ping_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': {
        20: 0.60,  # 0.75 - the first packet of this recording is marginal even unimpaired
        15: 0.60,  # 0.83
    },
    'samples/single_channel/ping2_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': {
        20: 0.95,  # 1.00
        15: 0.95,  # 1.00
        12: 0.25,  # 0.42
    },
}

# Carrier frequency offsets to test, in Hz. The receive chain corrects the carrier only
# after demodulation, so the channel filter ahead of it has to stay wide; these document the
# tolerance that buys rather than asserting a target.
CARRIER_OFFSETS_HZ = (0, 2500, 5000, 10000, 15000, 20000)

# Sample clock errors to test, as the ratio channel_model calls epsilon. 100 ppm either way
# is far beyond any real crystal; the point is to show the symbol synchronizer tracks.
CLOCK_ERRORS = (0.9999, 0.99995, 1.0, 1.00005, 1.0001)

# Signal-to-noise ratio the carrier offset and clock error sweeps are run at. Native SNR is
# far too clean to show either impairment costing anything within the ranges above, so these
# combine them with a moderate, already-lossy noise level from SNR_LEVELS -- the fixed point
# the decode-rate floors below are measured at.
FIXED_IMPAIRMENT_SNR_DB = 12

DECODE_RATE_POINTS = [(filename, snr_db)
                      for filename, floors in MINIMUM_DECODE_RATE.items()
                      for snr_db in sorted(floors, reverse=True)]


def receive(filename, impairment, decimation=DECIMATION):
    """Receive a sample file through the given impairment and return the flow graph."""
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, _, phy_mode_id = fileinfo[filename]
    rx = single_channel_packet_receiver(filename,
                                        sample_rate=sample_rate,
                                        frequency_offset=frequency_offset,
                                        channel_spacing=channel_spacing,
                                        decimation=decimation,
                                        samples_per_symbol=sample_rate // decimation // symbol_rate,
                                        gated_power_squelch=False,
                                        fec=uses_fec(phy_mode_id),
                                        impairment=impairment)
    rx.process()
    return rx


def measure_point(filename, snr_db=None, carrier_offset_hz=0.0, epsilon=1.0,
                  decimation=DECIMATION, seeds=SEEDS):
    """Run one point of the grid over every seed.

    Returns how many packets were decoded, how many were transmitted, the lengths of
    anything received that was not a packet the recording contains, how many coded packets
    came out with a bad frame check sequence, and a bit error count against a clean-decode
    reference (see `reference.py`).

    The bit error count is conditioned on successful framing: a packet that never decodes
    contributes to `decoded`/`transmitted` (the packet-error-rate side), not to
    `bit_errors`/`bits_compared`, since there is no bit alignment to compare without a
    frame. The two must not be combined into one rate.
    """
    expected_lengths = fileinfo[filename][5]
    plausible = set(expected_lengths)
    references = reference_packets(filename)
    decoded = 0
    implausible = []
    fcs_invalid = 0
    bit_errors = 0
    bits_compared = 0

    for seed in seeds:
        impairment = ChannelImpairment(filename, snr_db=snr_db, carrier_offset_hz=carrier_offset_hz,
                                       epsilon=epsilon, seed=seed)
        rx = receive(filename, impairment, decimation)
        for packet in rx.get_all_messages():
            payload = bytes(packet)
            if len(payload) in plausible:
                decoded += 1
                match = best_match(payload, references)
                if match is not None:
                    bit_errors += hamming_distance(payload, match)
                    bits_compared += 8 * len(payload)
            else:
                implausible.append(len(payload))
        if uses_fec(fileinfo[filename][6]):
            fcs_invalid += sum(1 for tag in rx.get_all_message_tags('wisun-fcs-valid')
                               if not pmt.to_python(pmt.cdr(tag)))

    return {
        'decoded': decoded,
        'transmitted': len(expected_lengths) * len(seeds),
        'implausible': implausible,
        'fcs_invalid': fcs_invalid,
        'bit_errors': bit_errors,
        'bits_compared': bits_compared,
    }


@cache
def run_point(filename, **kwargs):
    """Measure one point of the grid in a throwaway process, remembering the result.

    Both the isolation and the cache are there to keep the number of flow graphs this module
    builds in any one interpreter small — see `isolation.py` for why that matters. The cache
    also means the two tests asserting on the same point share a single run.
    """
    return run_isolated(measure_point, filename, **kwargs)


def assert_no_invented_packets(result):
    """Assert that everything received was a real packet."""
    assert result['implausible'] == [], \
        f"received packets of implausible length: {result['implausible']}"
    assert result['fcs_invalid'] == 0, \
        f"{result['fcs_invalid']} coded packets came out with an invalid frame check sequence"


@pytest.mark.parametrize("snr_db", SNR_LEVELS)
@pytest.mark.parametrize("filename", list(fileinfo))
def test_noise_does_not_invent_packets(filename, snr_db):
    """Under noise, every packet received must still be a real packet."""
    assert_no_invented_packets(run_point(filename, snr_db=snr_db))


@pytest.mark.parametrize("filename,snr_db", DECODE_RATE_POINTS)
def test_decode_rate_does_not_regress(filename, snr_db):
    """At least the baseline fraction of packets must still be decoded."""
    result = run_point(filename, snr_db=snr_db)
    rate = result['decoded'] / result['transmitted']
    floor = MINIMUM_DECODE_RATE[filename][snr_db]
    assert rate >= floor, \
        f"decoded {result['decoded']}/{result['transmitted']} = {rate:.2f}, floor is {floor:.2f}"


def is_subsequence(received, expected):
    """Check that `received` is `expected` with zero or more entries dropped."""
    remaining = iter(expected)
    return all(any(length == candidate for candidate in remaining) for length in received)


@pytest.mark.parametrize("filename", list(fileinfo))
def test_unimpaired_channel_model_costs_almost_nothing(filename):
    """A channel model with no impairment must cost at most one packet and invent none.

    It is not quite transparent: `channel_model` puts an `mmse_resampler` in the path even at
    `epsilon = 1.0`, so the signal is very slightly filtered and delayed whatever the
    settings. On these recordings that is enough to cost one already-marginal packet, which
    is why the numbers in this module are not directly comparable with the clean-sample
    tests.

    The point of the check is to separate a fault in the harness from one in the receiver: if
    a change makes *this* fail, the channel model insertion is wrong rather than the receive
    chain.
    """
    expected_lengths = fileinfo[filename][5]
    received_lengths = [len(packet)
                        for packet in receive(filename, ChannelImpairment(filename)).get_all_messages()]
    assert is_subsequence(received_lengths, expected_lengths), \
        f"received {received_lengths}, which is not {expected_lengths} with packets dropped"
    assert len(received_lengths) >= len(expected_lengths) - 1, \
        f"received only {len(received_lengths)} of {len(expected_lengths)} packets"


@pytest.mark.parametrize("carrier_offset_hz", CARRIER_OFFSETS_HZ)
@pytest.mark.parametrize("filename", list(fileinfo))
def test_carrier_offset_does_not_invent_packets(filename, carrier_offset_hz):
    """A carrier offset must cost packets at worst, never produce wrong ones."""
    assert_no_invented_packets(run_point(filename, carrier_offset_hz=carrier_offset_hz))


@pytest.mark.parametrize("epsilon", CLOCK_ERRORS)
@pytest.mark.parametrize("filename", list(fileinfo))
def test_sample_clock_error_does_not_invent_packets(filename, epsilon):
    """A sample clock error must cost packets at worst, never produce wrong ones."""
    assert_no_invented_packets(run_point(filename, epsilon=epsilon))


# Minimum decode rate at each carrier offset, at FIXED_IMPAIRMENT_SNR_DB, with the measured
# baseline beside it -- same convention as MINIMUM_DECODE_RATE, read off
# test_sweep_decode_rate_vs_carrier_offset. The first FEC sample is left out, same as it is
# from MINIMUM_DECODE_RATE at this SNR: its baseline is already marginal unimpaired (per the
# note there) and its 12-packet count makes the rate too coarse to floor meaningfully.
MINIMUM_DECODE_RATE_CARRIER_OFFSET = {
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': {
        0: 0.90,       # 1.00
        2500: 0.85,    # 0.98
        5000: 0.90,    # 1.00
        10000: 0.90,   # 1.00
        15000: 0.85,   # 0.98
        20000: 0.85,   # 0.98
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile': {
        0: 0.90,       # 1.00
        2500: 0.90,    # 1.00
        5000: 0.90,    # 1.00
        10000: 0.90,   # 1.00
        15000: 0.90,   # 1.00
        20000: 0.80,   # 0.94
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile': {
        0: 0.35,       # 0.56
        2500: 0.40,    # 0.67
        5000: 0.40,    # 0.68
        10000: 0.35,   # 0.56
        15000: 0.40,   # 0.65
        20000: 0.30,   # 0.51
    },
    'samples/single_channel/ping2_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': {
        0: 0.25,       # 0.42
        2500: 0.30,    # 0.50
        5000: 0.30,    # 0.50
        10000: 0.25,   # 0.42
        15000: 0.30,   # 0.50
        20000: 0.30,   # 0.50
    },
}

# Minimum decode rate at each clock error, at FIXED_IMPAIRMENT_SNR_DB, read off
# test_sweep_decode_rate_vs_clock_error. ping2's 1.00005 point used to be a full collapse
# (0/12) before the symbol-synchronizer retuning in baseband_channel_receiver.py; it
# recovers to a floorable rate now and is included like every other point.
MINIMUM_DECODE_RATE_CLOCK_ERROR = {
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': {
        0.9999: 0.90,    # 1.00
        0.99995: 0.90,   # 1.00
        1.0: 0.90,       # 1.00
        1.00005: 0.90,   # 1.00
        1.0001: 0.90,    # 1.00
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile': {
        0.9999: 0.90,    # 1.00
        0.99995: 0.90,   # 1.00
        1.0: 0.90,       # 0.98
        1.00005: 0.90,   # 1.00
        1.0001: 0.90,    # 1.00
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile': {
        0.9999: 0.35,    # 0.57
        0.99995: 0.35,   # 0.56
        1.0: 0.35,       # 0.56
        1.00005: 0.35,   # 0.59
        1.0001: 0.35,    # 0.54
    },
    'samples/single_channel/ping2_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': {
        0.9999: 0.30,    # 0.50
        0.99995: 0.30,   # 0.50
        1.0: 0.25,       # 0.42
        1.00005: 0.20,   # 0.33
        1.0001: 0.30,    # 0.50
    },
}

CARRIER_OFFSET_POINTS = [(filename, offset)
                        for filename, floors in MINIMUM_DECODE_RATE_CARRIER_OFFSET.items()
                        for offset in floors]
CLOCK_ERROR_POINTS = [(filename, epsilon)
                      for filename, floors in MINIMUM_DECODE_RATE_CLOCK_ERROR.items()
                      for epsilon in floors]

# Maximum bit error rate at each signal-to-noise ratio, with the measured baseline beside
# it (read off test_sweep_bit_error_rate). A ceiling rather than a floor: bit error rate
# must not exceed this. Measured bit error rate is exactly zero at every point tested --
# whenever a packet still frames and passes its own checks (length, path metric, FCS), its
# payload bits are already right; errors at this signal-to-noise range cost whole packets
# rather than flipping bits within one that otherwise passes -- so the ceiling is a small
# margin, not half the baseline the way the decode-rate floors above are. Points use the
# same SNR levels as MINIMUM_DECODE_RATE where that dict already has an entry, since those
# are already known-good decode points; the first FEC file gets one even though
# MINIMUM_DECODE_RATE omits 12 dB for it, since enough packets still decode there to compare.
MAXIMUM_BIT_ERROR_RATE = {
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': {
        20: 0.0005,    # 0.0000
        15: 0.0005,    # 0.0000
        12: 0.0005,    # 0.0000
        10: 0.0005,    # 0.0000
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile': {
        20: 0.0005,    # 0.0000
        15: 0.0005,    # 0.0000
        12: 0.0005,    # 0.0000
    },
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile': {
        20: 0.0005,    # 0.0000
        15: 0.0005,    # 0.0000
        12: 0.0005,    # 0.0000
    },
    'samples/single_channel/ping_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': {
        20: 0.0005,    # 0.0000
        15: 0.0005,    # 0.0000
        12: 0.0005,    # 0.0000
    },
    'samples/single_channel/ping2_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': {
        20: 0.0005,    # 0.0000
        15: 0.0005,    # 0.0000
        12: 0.0005,    # 0.0000
    },
}

BIT_ERROR_RATE_POINTS = [(filename, snr_db)
                        for filename, ceilings in MAXIMUM_BIT_ERROR_RATE.items()
                        for snr_db in ceilings]


@pytest.mark.parametrize("filename,carrier_offset_hz", CARRIER_OFFSET_POINTS)
def test_decode_rate_vs_carrier_offset_does_not_regress(filename, carrier_offset_hz):
    """At a fixed moderate SNR, at least the baseline fraction must still decode."""
    result = run_point(filename, snr_db=FIXED_IMPAIRMENT_SNR_DB, carrier_offset_hz=carrier_offset_hz)
    rate = result['decoded'] / result['transmitted']
    floor = MINIMUM_DECODE_RATE_CARRIER_OFFSET[filename][carrier_offset_hz]
    assert rate >= floor, \
        f"decoded {result['decoded']}/{result['transmitted']} = {rate:.2f}, floor is {floor:.2f}"


@pytest.mark.parametrize("filename,epsilon", CLOCK_ERROR_POINTS)
def test_decode_rate_vs_clock_error_does_not_regress(filename, epsilon):
    """At a fixed moderate SNR, at least the baseline fraction must still decode."""
    result = run_point(filename, snr_db=FIXED_IMPAIRMENT_SNR_DB, epsilon=epsilon)
    rate = result['decoded'] / result['transmitted']
    floor = MINIMUM_DECODE_RATE_CLOCK_ERROR[filename][epsilon]
    assert rate >= floor, \
        f"decoded {result['decoded']}/{result['transmitted']} = {rate:.2f}, floor is {floor:.2f}"


@pytest.mark.parametrize("filename,snr_db", BIT_ERROR_RATE_POINTS)
def test_bit_error_rate_does_not_regress(filename, snr_db):
    """Bit error rate, among packets that still decode, must not exceed the baseline ceiling."""
    result = run_point(filename, snr_db=snr_db)
    assert result['bits_compared'] > 0, "no decoded packet could be matched to a reference"
    rate = result['bit_errors'] / result['bits_compared']
    ceiling = MAXIMUM_BIT_ERROR_RATE[filename][snr_db]
    assert rate <= ceiling, \
        f"{result['bit_errors']}/{result['bits_compared']} bits wrong = {rate:.4f}, ceiling is {ceiling:.4f}"


@pytest.mark.sweep
def test_sweep_decode_rate(capsys):
    """Print decode rate against signal-to-noise ratio for every sample file.

    Deselected by default: this is the measurement the floors in `MINIMUM_DECODE_RATE` are
    read off, not an assertion. Run it with `pytest -m sweep -s`.
    """
    levels = (25, 20, 17, 15, 13, 12, 11, 10, 8, 6)
    with capsys.disabled():
        print(f"\ndecode rate, decimation {DECIMATION}, seeds {SEEDS}\n")
        print(f"{'sample file':52s} {'native':>7s} " + " ".join(f"{level:>5d}" for level in levels))
        print(f"{'':52s} {'SNR':>7s} " + " ".join(f"{'dB':>5s}" for _ in levels))
        for filename in fileinfo:
            rates = []
            for snr_db in levels:
                result = run_point(filename, snr_db=snr_db)
                rates.append(result['decoded'] / result['transmitted'])
            native = measure_power(filename).snr_db
            print(f"{filename.split('/')[-1][:52]:52s} {native:6.1f}  "
                  + " ".join(f"{rate:5.2f}" for rate in rates))


@pytest.mark.sweep
def test_sweep_decode_rate_vs_carrier_offset(capsys):
    """Print decode rate against carrier offset, at a fixed moderate SNR, for every file.

    Deselected by default: this is the measurement the floors in
    `MINIMUM_DECODE_RATE_CARRIER_OFFSET` are read off. Run it with `pytest -m sweep -s`.
    """
    offsets = (0, 2500, 5000, 7500, 10000, 12500, 15000, 17500, 20000)
    with capsys.disabled():
        print(f"\ndecode rate vs carrier offset, SNR {FIXED_IMPAIRMENT_SNR_DB} dB, "
              f"decimation {DECIMATION}, seeds {SEEDS}\n")
        print(f"{'sample file':52s} " + " ".join(f"{offset:>6d}" for offset in offsets))
        print(f"{'':52s} " + " ".join(f"{'Hz':>6s}" for _ in offsets))
        for filename in fileinfo:
            rates = []
            for offset in offsets:
                result = run_point(filename, snr_db=FIXED_IMPAIRMENT_SNR_DB, carrier_offset_hz=offset)
                rates.append(result['decoded'] / result['transmitted'])
            print(f"{filename.split('/')[-1][:52]:52s} " + " ".join(f"{rate:6.2f}" for rate in rates))


@pytest.mark.sweep
def test_sweep_decode_rate_vs_clock_error(capsys):
    """Print decode rate against sample clock error, at a fixed moderate SNR, for every file.

    Deselected by default: this is the measurement the floors in
    `MINIMUM_DECODE_RATE_CLOCK_ERROR` are read off. Run it with `pytest -m sweep -s`.
    """
    epsilons = (0.9999, 0.99993, 0.99995, 0.99998, 1.0, 1.00002, 1.00005, 1.00007, 1.0001)
    with capsys.disabled():
        print(f"\ndecode rate vs clock error, SNR {FIXED_IMPAIRMENT_SNR_DB} dB, "
              f"decimation {DECIMATION}, seeds {SEEDS}\n")
        print(f"{'sample file':52s} " + " ".join(f"{epsilon:>8g}" for epsilon in epsilons))
        for filename in fileinfo:
            rates = []
            for epsilon in epsilons:
                result = run_point(filename, snr_db=FIXED_IMPAIRMENT_SNR_DB, epsilon=epsilon)
                rates.append(result['decoded'] / result['transmitted'])
            print(f"{filename.split('/')[-1][:52]:52s} " + " ".join(f"{rate:8.2f}" for rate in rates))


@pytest.mark.sweep
def test_sweep_bit_error_rate(capsys):
    """Print bit error rate against signal-to-noise ratio for every sample file.

    Deselected by default: this is the measurement the ceilings in `MAXIMUM_BIT_ERROR_RATE`
    are read off. Run it with `pytest -m sweep -s`.
    """
    levels = (25, 20, 17, 15, 13, 12, 11, 10, 8, 6)
    with capsys.disabled():
        print(f"\nbit error rate, decimation {DECIMATION}, seeds {SEEDS}\n")
        print(f"{'sample file':52s} " + " ".join(f"{level:>7d}" for level in levels))
        print(f"{'':52s} " + " ".join(f"{'SNR dB':>7s}" for _ in levels))
        for filename in fileinfo:
            rates = []
            for snr_db in levels:
                result = run_point(filename, snr_db=snr_db)
                rates.append(result['bit_errors'] / result['bits_compared'] if result['bits_compared'] else None)
            print(f"{filename.split('/')[-1][:52]:52s} "
                  + " ".join("     n/a" if rate is None else f"{rate:8.4f}" for rate in rates))
