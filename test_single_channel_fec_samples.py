# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests with recorded samples of FEC-coded packets on a single channel."""

import pmt
import pytest
from receiver import single_channel_packet_receiver
from sample_files import fileinfo, uses_fec

FEC_SAMPLES = [filename for filename in fileinfo if uses_fec(fileinfo[filename][6])]

# Decimations to test. The uncoded samples are also tested at a decimation of 5, i.e. at
# 2 samples per symbol, but a coded frame does not survive that reliably: the receiver
# loses one of the four packets. That is the clock synchronization rather than the
# decoding — every packet that is received decodes with no corrections at all.
DECIMATIONS = [1, 2]

# Note: these tests run with the gated power squelch disabled. Enabling it makes the
# number of received packets non-deterministic, for coded and uncoded samples alike
# (an uncoded sample of 21 packets yields anything from 17 to 20), so it cannot be
# asserted on. That is independent of the FEC support tested here.


@pytest.mark.parametrize("decimation", DECIMATIONS)
@pytest.mark.parametrize("filename", FEC_SAMPLES)
def test_fec_ping_packets(decimation, filename):
    """Test with recorded samples of a FEC-coded ping exchange."""
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths, _ = \
        fileinfo[filename]
    samples_per_symbol = sample_rate // decimation // symbol_rate
    rx = single_channel_packet_receiver(filename,
                                        sample_rate=sample_rate,
                                        frequency_offset=frequency_offset,
                                        channel_spacing=channel_spacing,
                                        decimation=decimation,
                                        samples_per_symbol=samples_per_symbol,
                                        gated_power_squelch=False,
                                        fec=True)
    rx.process()
    packets = rx.get_all_messages()
    assert len(packets) == len(expected_packet_lengths), \
        f"wrong number of packets received ({len(packets)} / {len(expected_packet_lengths)})"
    for i in range(len(packets)):
        assert len(packets[i]) == expected_packet_lengths[i], "wrong packet length"


@pytest.mark.parametrize("decimation", DECIMATIONS)
@pytest.mark.parametrize("filename", FEC_SAMPLES)
def test_fec_packets_decode_without_corrections(decimation, filename):
    """Every packet must decode with a Viterbi path metric of zero and a valid FCS.

    On a clean link a real frame needs no corrections at all. A metric of "nearly zero"
    is not success — it means something in the chain is slightly wrong — so this is a far
    sharper check than the packet lengths, and it is what the frame check sequence alone
    cannot tell us: a 16-bit FCS accepts noise once in 65536.
    """
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, expected_packet_lengths, _ = \
        fileinfo[filename]
    samples_per_symbol = sample_rate // decimation // symbol_rate
    rx = single_channel_packet_receiver(filename,
                                        sample_rate=sample_rate,
                                        frequency_offset=frequency_offset,
                                        channel_spacing=channel_spacing,
                                        decimation=decimation,
                                        samples_per_symbol=samples_per_symbol,
                                        gated_power_squelch=False,
                                        fec=True)
    rx.process()
    assert rx.get_message_count() == len(expected_packet_lengths)
    # get_all_message_tags returns the whole (key . value) pair
    metrics = [pmt.to_python(pmt.cdr(tag)) for tag in rx.get_all_message_tags('wisun-fec-metric')]
    assert metrics == [0] * len(expected_packet_lengths), f"packets needed corrections: {metrics}"
    fcs_valid = [pmt.to_python(pmt.cdr(tag)) for tag in rx.get_all_message_tags('wisun-fcs-valid')]
    assert all(fcs_valid), f"invalid frame check sequence: {fcs_valid}"


@pytest.mark.parametrize("filename", FEC_SAMPLES)
def test_fec_samples_are_not_received_as_uncoded(filename):
    """A receiver locked to the uncoded SFD must be deaf to these coded packets."""
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, _, _ = fileinfo[filename]
    rx = single_channel_packet_receiver(filename,
                                        sample_rate=sample_rate,
                                        frequency_offset=frequency_offset,
                                        channel_spacing=channel_spacing,
                                        decimation=1,
                                        samples_per_symbol=sample_rate // symbol_rate,
                                        gated_power_squelch=False,
                                        fec=False)
    rx.process()
    assert rx.get_message_count() == 0
