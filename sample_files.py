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
    "expected_packets",         # Wi-SUN channel -> payload lengths, in the order received
    "packets_at_default",       # how many the default channelizer oversampling gets
    "clipped_input_samples",    # samples at full scale, i.e. how hard the input was driven
    "crc_error_packets",        # (channel, length) of the frames whose FCS does not verify
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
            },
            packets_at_default=18,
            clipped_input_samples=0,
            crc_error_packets=[]),
    'samples/multi_channel/ping_5x_8Msps_866.7MHz_EU_channel_plan_33_phy_type_1_phy_mode_3_high_gain.cfile':
        MultiChannelSample(
            description=(
                "The same exchange as above, recorded at too high a gain, which is what makes it worth keeping. "
                "Three things show up that the other recording does not have. One burst reaches full scale over "
                "1.4 % of its samples, so the input clips. One ping request went unacknowledged and was "
                "retransmitted with the same MAC sequence number, which is why there are 21 transmissions rather "
                "than 20. And three frames appear a second time 5.0 MHz above their own channel, 25 to 27 dB "
                "down: channel 1 again on 26, channel 2 on 27 and channel 4 on 29. All three are frames of the "
                "device whose crystal is 24 ppm low, while the other device - which arrives some 8 dB stronger - "
                "produces none, so they are that transmitter's spurious emission rather than anything in the "
                "receiver. The gain only lifted them above the noise. Two of the three are corrupted and their "
                "frame check sequence says so; the third is bit-exact and indistinguishable from a real frame."),
            sample_rate=8_000_000,
            center_frequency=866_700_000,
            regulatory_domain="EU",
            channel_plan_id=33,
            phy_mode_id=0x13,
            expected_packets={
                1: [167, 50],
                2: [167],
                4: [142, 56],
                5: [167, 50],
                11: [142, 56, 167, 50],
                14: [167, 50],
                15: [142, 56],
                20: [167, 50],
                21: [142, 56],
                26: [167],          # a copy of channel 1's request
                27: [167],          # a copy of channel 2's request
                29: [56],           # a copy of channel 4's acknowledgement
                30: [142, 56],
            },
            packets_at_default=19,
            clipped_input_samples=10252,
            crc_error_packets=[(26, 167), (27, 167)]),
}


def expected_packet_count(sample):
    """Return how many packets a multi-channel recording holds."""
    return sum(len(lengths) for lengths in sample.expected_packets.values())
