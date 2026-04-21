# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Information about sample files."""

fileinfo = {
    # filename: description, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. Device and router were connected via a RF power splitter with a total attenuation of 56 dB.",
        1000000,
        100000,
        100000,
        50000,
        [168, 48, 154, 48] * 5
    )
}
