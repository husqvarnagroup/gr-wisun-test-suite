# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests with a wideband recording covering many channels at once.

These drive `multi_channel_receiver`, i.e. the polyphase channelizer and one receive chain
per channel, which the single-channel tests never reach. Two things about it only show up
here: the samples per symbol the channelizer leaves the chains with, and whether channels
the regulatory mask excludes are received at all.

Each measurement runs in its own process — a 35-channel flow graph over a 65 MB recording
leaves a lot behind; see `isolation.py`.
"""

import collections

import pytest
from isolation import run_isolated
from pcapng import INTERFACE_DESCRIPTION_BLOCK, SECTION_HEADER_BLOCK, parse_stream
from receiver import multi_channel_packet_receiver
from sample_files import expected_packet_count, multi_channel_fileinfo

from gnuradio.wisun.configuration import WiSunConfiguration

# The oversampling needed to decode everything. The default is lower, trading packets for
# the headroom to keep up with an SDR, so the complete decode is asserted at this one and
# the default gets a floor of its own.
FULL_OVERSAMPLING = 4

SAMPLES = sorted(multi_channel_fileinfo.keys())


def receive(filename, oversampling):
    """Receive a recording and return its packets per channel plus the leading block counts."""
    sample = multi_channel_fileinfo[filename]
    config = WiSunConfiguration(sample.regulatory_domain, sample.channel_plan_id, sample.phy_mode_id)
    receiver = multi_channel_packet_receiver(filename, config, sample.sample_rate,
                                            sample.center_frequency, oversampling=oversampling)
    receiver.process()
    packets, counts = parse_stream(receiver.blocks())
    per_channel = collections.defaultdict(list)
    for packet in packets:
        per_channel[packet.channel].append(len(packet.payload))
    return {
        'per_channel': dict(per_channel),
        'total': len(packets),
        'bit_rates': sorted({packet.bit_rate for packet in packets}),
        'fcs_lengths': sorted({packet.fcs_length for packet in packets}),
        'crc_errors': sorted((packet.channel, len(packet.payload))
                             for packet in packets if packet.crc_error),
        'section_headers': counts[SECTION_HEADER_BLOCK],
        'interface_descriptions': counts[INTERFACE_DESCRIPTION_BLOCK],
        'clipped_input_samples': receiver.mcpr.clipping_detector.clipped_samples(),
    }


@pytest.mark.parametrize("filename", SAMPLES)
def test_every_packet_is_received(filename):
    """Every packet of the recording must be received, on the right channel and intact."""
    sample = multi_channel_fileinfo[filename]
    result = run_isolated(receive, filename, FULL_OVERSAMPLING)

    assert result['per_channel'] == sample.expected_packets
    assert result['total'] == expected_packet_count(sample)


@pytest.mark.parametrize("filename", SAMPLES)
def test_the_default_oversampling_receives_most_packets(filename):
    """The default must stay close to the complete decode.

    It is deliberately below what decodes everything, so this is a floor rather than an
    equality: 2 samples per symbol would receive little more than half.
    """
    sample = multi_channel_fileinfo[filename]
    result = run_isolated(receive, filename, None)

    assert result['total'] >= sample.packets_at_default


@pytest.mark.parametrize("filename", SAMPLES)
def test_channels_the_regulatory_mask_excludes_are_received(filename):
    """Packets on channels the mask excludes must be reported, not dropped.

    The recording holds some, and a sniffer that only listens where devices are allowed to
    transmit cannot say they were there.
    """
    sample = multi_channel_fileinfo[filename]
    config = WiSunConfiguration(sample.regulatory_domain, sample.channel_plan_id, sample.phy_mode_id)
    excluded = set(config.channels_outside_mask())
    assert excluded, "this recording's channel plan has no excluded channels to test with"

    result = run_isolated(receive, filename, FULL_OVERSAMPLING)
    received_outside_mask = excluded & set(result['per_channel'])

    assert received_outside_mask, f"no packet received on any of the excluded channels {sorted(excluded)}"
    assert received_outside_mask <= set(sample.expected_packets)


@pytest.mark.parametrize("filename", SAMPLES)
def test_the_pcapng_stream_is_well_formed(filename):
    """The stream must carry its leading blocks once per channel, and the bit rate per packet.

    Each channel receiver writes its own section header and interface description, so there
    is one of each per channel that produced a packet - no more, which is what a repeated
    interface description would mean.
    """
    sample = multi_channel_fileinfo[filename]
    result = run_isolated(receive, filename, FULL_OVERSAMPLING)
    channels_with_packets = len(result['per_channel'])

    assert result['section_headers'] == channels_with_packets
    assert result['interface_descriptions'] == channels_with_packets

    config = WiSunConfiguration(sample.regulatory_domain, sample.channel_plan_id, sample.phy_mode_id)
    assert result['bit_rates'] == [config.radio_configuration().data_rate()]


@pytest.mark.parametrize("filename", SAMPLES)
def test_a_failed_frame_check_is_reported(filename):
    """A frame whose check sequence does not verify must be marked as such.

    The frame carries its own check sequence, so a reader can verify it; the receiver's
    verdict travels alongside in the packet flags. Without either, a corrupted frame reaches
    Wireshark looking exactly like a good one - which is how the copies in the high-gain
    recording would otherwise pass for real traffic.
    """
    sample = multi_channel_fileinfo[filename]
    result = run_isolated(receive, filename, FULL_OVERSAMPLING)

    assert result['crc_errors'] == sorted(sample.crc_error_packets)
    # the FCS width has to be declared, or a reader cannot find the check sequence at all
    assert result['fcs_lengths'] == [4]


@pytest.mark.parametrize("filename", SAMPLES)
def test_clipping_is_noticed(filename):
    """A clipping input must be counted, and a clean one must not be.

    Nothing else in the receiver reacts to too much gain, so this is the only warning that
    the signal is being distorted before any of it is demodulated.
    """
    sample = multi_channel_fileinfo[filename]
    result = run_isolated(receive, filename, FULL_OVERSAMPLING)

    assert result['clipped_input_samples'] == sample.clipped_input_samples
