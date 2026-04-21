# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Receiver flow graph for testing with single channel Wi-SUN packet samples."""

from gnuradio import blocks, gr
from gnuradio.wisun import single_channel_receiver
import pmt


class single_channel_packet_receiver(gr.top_block):
    """GNU Radio flow graph for receiving packets on a single channel from a file."""

    def __init__(self, filename, sample_rate, frequency_offset, channel_spacing, decimation, samples_per_symbol,
                 gated_power_squelch):
        """Build the flow graph."""
        gr.top_block.__init__(self, "Single Channel Packet Receiver (File Source)")
        self.src = blocks.file_source(gr.sizeof_gr_complex*1, filename, False, 0, 0)
        self.scpr = single_channel_receiver(sample_rate=sample_rate,
                                            frequency_offset=frequency_offset,
                                            channel_spacing=channel_spacing,
                                            decimation=decimation,
                                            samples_per_symbol=samples_per_symbol,
                                            gated_power_squelch=gated_power_squelch)
        self.msg_debug = blocks.message_debug()

        self.connect((self.src, 0), (self.scpr, 0))
        self.msg_connect((self.scpr, 'pdus'), (self.msg_debug, 'store'))

    def get_message_count(self):
        """Get total number of messages received."""
        return self.msg_debug.num_messages()

    def get_all_messages(self):
        """Get all messages."""
        return self.get_messages_since(0)

    def get_all_message_tags(self, key):
        """Get all message tags with given key."""
        msgs = [self.msg_debug.get_message(i) for i in range(self.msg_debug.num_messages())]
        tags = [pmt.assoc(pmt.string_to_symbol(key), pmt.car(m)) for m in msgs]
        return tags

    def get_messages_since(self, start_index=0):
        """Get all messages starting from given index."""
        return [pmt.u8vector_elements(pmt.cdr(self.msg_debug.get_message(i)))
                for i in range(start_index, self.msg_debug.num_messages())]

    def get_last_message(self):
        """Get last received message."""
        num_messages = self.msg_debug.num_messages()
        assert num_messages > 0
        msg = self.msg_debug.get_message(num_messages - 1)
        return pmt.u8vector_elements(pmt.cdr(msg))

    def process(self):
        """Process samples (and run to completion)."""
        self.start()
        self.wait()
        self.stop()
