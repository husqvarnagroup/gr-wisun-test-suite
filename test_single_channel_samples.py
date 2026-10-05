# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests with recorded samples (packets on a single channel)."""

import pytest
import receiver
from receiver import decode_sample_file
from sample_files import fileinfo


@pytest.mark.parametrize("decimation", [1, 4, 5, 10])
@pytest.mark.parametrize("gated_power_squelch", [False, True])
def test_ping_packets_50ksps(decimation, gated_power_squelch):
    """Test with recorded samples for 5 pings."""
    filename = "samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile"
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths, _ = \
        fileinfo[filename]
    samples_per_symbol = sample_rate // decimation // symbol_rate
    _, packets = decode_sample_file(filename,
                                    len(expected_packet_lengths),
                                    sample_rate=sample_rate,
                                    frequency_offset=frequency_offset,
                                    channel_spacing=channel_spacing,
                                    decimation=decimation,
                                    samples_per_symbol=samples_per_symbol,
                                    gated_power_squelch=gated_power_squelch)
    assert len(packets) == len(expected_packet_lengths)
    for i in range(len(packets)):
        assert len(packets[i]) == expected_packet_lengths[i]


@pytest.mark.parametrize("decimation", [1, 2, 5])
@pytest.mark.parametrize("gated_power_squelch", [False, True])
@pytest.mark.parametrize("filename", [
    "samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile",
    "samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile"
])
def test_ping_packets_100ksps(decimation, gated_power_squelch, filename):
    """Test with recorded samples for 5 pings."""
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths, _ = \
        fileinfo[filename]
    samples_per_symbol = sample_rate // decimation // symbol_rate
    _, packets = decode_sample_file(filename,
                                    len(expected_packet_lengths),
                                    sample_rate=sample_rate,
                                    frequency_offset=frequency_offset,
                                    channel_spacing=channel_spacing,
                                    decimation=decimation,
                                    samples_per_symbol=samples_per_symbol,
                                    gated_power_squelch=gated_power_squelch)
    assert len(packets) == len(expected_packet_lengths), \
        f"wrong number of packets received ({len(packets)} / {len(expected_packet_lengths)})"
    for i in range(len(packets)):
        assert len(packets[i]) == expected_packet_lengths[i], "wrong packet length"


def test_a_decode_that_falls_short_is_retried(monkeypatch):
    """A shortfall must actually make `decode_sample_file` run the flow graph again.

    Without this the retry could be inert and the tests above would still pass, since they
    pass on the first attempt almost always. An unreachable target also has to come back as
    the best attempt rather than an exception, so a real regression is reported by the
    assertion in the test rather than as an error here.
    """
    filename = "samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile"
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths, _ = \
        fileinfo[filename]
    attempts = []
    build = receiver.single_channel_packet_receiver

    def counting_receiver(*args, **kwargs):
        attempts.append(1)
        return build(*args, **kwargs)

    monkeypatch.setattr(receiver, "single_channel_packet_receiver", counting_receiver)
    _, packets = decode_sample_file(filename,
                                    len(expected_packet_lengths) + 1,  # never reached
                                    attempts=3,
                                    sample_rate=sample_rate,
                                    frequency_offset=frequency_offset,
                                    channel_spacing=channel_spacing,
                                    decimation=1,
                                    samples_per_symbol=sample_rate // symbol_rate,
                                    gated_power_squelch=False)
    assert len(attempts) == 3
    assert len(packets) == len(expected_packet_lengths)
