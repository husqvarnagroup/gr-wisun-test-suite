# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests with recorded samples (packets on a single channel)."""

import pytest
from receiver import single_channel_packet_receiver
from sample_files import fileinfo


@pytest.mark.parametrize("decimation", [1, 4, 5, 10])
@pytest.mark.parametrize("gated_power_squelch", [False, True])
def test_ping_packets(decimation, gated_power_squelch):
    """Test with recorded samples for 5 pings."""
    filename = "samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile"
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths = fileinfo[filename]
    samples_per_symbol = sample_rate // decimation // symbol_rate
    rx = single_channel_packet_receiver(filename,
                                        sample_rate=sample_rate,
                                        frequency_offset=frequency_offset,
                                        channel_spacing=channel_spacing,
                                        decimation=decimation,
                                        samples_per_symbol=samples_per_symbol,
                                        gated_power_squelch=False)
    rx.process()
    packets = rx.get_all_messages()
    assert len(packets) == len(expected_packet_lengths)
    for i in range(len(packets)):
        assert len(packets[i]) == expected_packet_lengths[i]
