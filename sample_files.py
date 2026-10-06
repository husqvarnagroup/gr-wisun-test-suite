# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Information about sample files."""

from collections import namedtuple

fileinfo = {
    # filename: description, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths,
    #           phy_mode_id
    #
    # Note: expected_packet_lengths are the lengths of the PDUs the receiver produces. Those hold the SFD, the PHY
    # header and the whole PSDU, frame check sequence included, so each one is the frame length from the PHY header
    # plus the 4 octets of SFD and PHY header.
    'samples/single_channel/ping_1Msps_863MHz_50ksps_channel0.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Device and router connected via cables & RF power splitter with a total attenuation of 56 dB.",
        1000000,
        100000,
        100000,
        50000,
        [172, 52, 158, 52] * 5,
        0x01
    ),
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Device and router connected via cables & RF power splitter with a total attenuation of 56 dB. "
        "DUT has 10 dB additional attenuation. "
        "Additionally has a packet with a DODAG information object as last packet.",
        1000000,
        100000,
        200000,
        100000,
        [172, 52, 158, 52] * 5 + [173],
        0x03
    ),
    'samples/single_channel/ping_1Msps_863MHz_100ksps_channel0_on_air.cfile': (
        "5 pings from a device to a router. Each ping consists of ping request, ACK, ping response, ACK. "
        "Device and router connected using antennas. DUT has 10 dB additional attenuation. "
        "Additionally contains a PAN advertisement as last packet.",
        1000000,
        100000,
        200000,
        100000,
        [172, 52, 158, 52] * 5 + [74],
        0x03
    ),
    'samples/single_channel/ping_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': (
        "One ping from a device to a router on a FEC-coded PHY: ping request, ACK, ping response, ACK. "
        "Channel plan 33, channel 0 (863.1 MHz).",
        1000000,
        100000,
        200000,
        100000,
        [173, 54, 146, 60],
        0x13
    ),
    'samples/single_channel/ping2_1Msps_863MHz_PhyModeId_0x13_channel_0.cfile': (
        "One ping from a device to a router on a FEC-coded PHY: ping request, ACK, ping response, ACK. "
        "Channel plan 33, channel 0 (863.1 MHz). Second recording of the same exchange.",
        1000000,
        100000,
        200000,
        100000,
        [173, 54, 146, 60],
        0x13
    ),
}


def uses_fec(phy_mode_id):
    """Check whether the given Wi-SUN PhyModeID uses forward error correction.

    PhyType 1 is FSK with NRNSC FEC, i.e. the uncoded PhyType 0 modes plus coding.
    """
    return phy_mode_id >> 4 == 1


# Recordings covering many channels at once, for the multi-channel receiver.
#
# These are described by their Wi-SUN configuration rather than by a tuning offset: the
# channel set, spacing and symbol rate all follow from the regulatory domain, channel plan
# and PHY mode, which is also how the sniffer applications are told what to receive.
MultiChannelSample = namedtuple("MultiChannelSample", [
    "description",
    "sample_rate",
    "center_frequency",
    "regulatory_domain",
    "channel_plan_id",
    "phy_mode_id",
    "expected_packets",     # Wi-SUN channel -> payload lengths, in the order received
])

multi_channel_fileinfo = {
    'samples/multi_channel/ping_5x_8Msps_866.7MHz_EU_channel_plan_33_phy_type_1_phy_mode_3.cfile':
        MultiChannelSample(
            description=(
                "5 pings between a device and a router, frequency hopping over channel plan 33. Each ping is a "
                "request, its ACK, the reply and its ACK; the request and its ACK share a channel, the reply and "
                "its ACK another. The idle stretches have been cut out, leaving 60 ms around each of the five "
                "groups, which was measured not to change what the receiver decodes. Two of the twenty packets "
                "are on channels 28 and 31, which the EU channel mask for this plan excludes - devices do "
                "transmit there. The requesting device's crystal is about 24 ppm low, the other about 5 ppm "
                "high. Note that the capture's centre frequency is 200 kHz above what gqrx was set to "
                "(866.5 MHz); 866.7 MHz is the value under which every packet lands on a channel of the plan."),
            sample_rate=8_000_000,
            center_frequency=866_700_000,
            regulatory_domain="EU",
            channel_plan_id=33,
            phy_mode_id=0x13,
            expected_packets={
                0: [142, 56],
                8: [167, 50],
                15: [167, 50],
                18: [142, 56],
                19: [167, 50, 142, 56],
                20: [142, 56, 167, 50],
                28: [167, 50],
                31: [142, 56],
            }),
}


def expected_packet_count(sample):
    """Return how many packets a multi-channel recording holds."""
    return sum(len(lengths) for lengths in sample.expected_packets.values())
