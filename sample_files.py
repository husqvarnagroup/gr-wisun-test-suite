# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Information about sample files."""

fileinfo = {
    # filename: description, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths,
    #           phy_mode_id
    #
    # Note: expected_packet_lengths are the lengths of the PDUs the receiver produces. Those hold the SFD, the PHY
    # header and the payload without its frame check sequence, so each one is the frame length from the PHY header.
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Device and router were connected via a RF power splitter with a total attenuation of 56 dB.",
        1000000,
        100000,
        100000,
        50000,
        [168, 48, 154, 48] * 5,
        0x01
    ),
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Devices connected via cables using RF power splitter with attenuators. DUT has 10 dB additional attenuation. "
        "Additionally has a packet with a DODAG information object as last packet.",
        1000000,
        100000,
        200000,
        100000,
        [168, 48, 154, 48] * 5 + [169],
        0x03
    ),
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Devices connected using antennas. DUT has 10 dB additional attenuation. "
        "Additionally contains a PAN advertisement as last packet.",
        1000000,
        100000,
        200000,
        100000,
        [168, 48, 154, 48] * 5 + [70],
        0x03
    ),
    'samples/single_channel/ping_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': (
        "One ping from a device to a router on a FEC-coded PHY: ping request, ACK, ping response, ACK. "
        "Channel plan 33, channel 0 (863.1 MHz).",
        1000000,
        100000,
        200000,
        100000,
        [169, 50, 142, 56],
        0x13
    ),
    'samples/single_channel/ping2_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': (
        "One ping from a device to a router on a FEC-coded PHY: ping request, ACK, ping response, ACK. "
        "Channel plan 33, channel 0 (863.1 MHz). Second recording of the same exchange.",
        1000000,
        100000,
        200000,
        100000,
        [169, 50, 142, 56],
        0x13
    ),
}


def uses_fec(phy_mode_id):
    """Check whether the given Wi-SUN PhyModeID uses forward error correction.

    PhyType 1 is FSK with NRNSC FEC, i.e. the uncoded PhyType 0 modes plus coding.
    """
    return phy_mode_id >> 4 == 1
