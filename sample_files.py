# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Information about sample files."""

fileinfo = {
    # filename: description, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Device and router were connected via a RF power splitter with a total attenuation of 56 dB.",
        1000000,
        100000,
        100000,
        50000,
        [168, 48, 154, 48] * 5
    ),
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Devices connected via cables using RF power splitter with attenuators. DUT has 10 dB additional attenuation. "
        "Additionally has a packet with a DODAG information object as last packet.",
        1000000,
        100000,
        200000,
        100000,
        [168, 48, 154, 48] * 5 + [169]
    ),
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Devices connected using antennas. DUT has 10 dB additional attenuation. "
        "Additionally contains a PAN advertisement as last packet.",
        1000000,
        100000,
        200000,
        100000,
        [168, 48, 154, 48] * 5 + [70]
    ),
}
