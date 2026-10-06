# coding: utf-8
#
# Copyright (c) 2026 Gardena GmbH
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reading the pcapng blocks the multi-channel receiver emits.

Its output is the stream that would be written for Wireshark, not bare packets, so a test
has to read it the way Wireshark does. Parsing it here also means the stream itself is
checked: a malformed block, or a section header repeated per packet, shows up as a test
failure rather than as something only noticed in Wireshark.

All blocks are little endian, which is what the block writes (it does not byte-swap, so a
big-endian machine would need more than this).
"""

import struct
from collections import namedtuple

SECTION_HEADER_BLOCK = 0x0A0D0D0A
INTERFACE_DESCRIPTION_BLOCK = 0x00000001
ENHANCED_PACKET_BLOCK = 0x00000006

# IEEE 802.15.4 TAP TLV types, as the sniffer writes them
TLV_RSS = 1
TLV_BIT_RATE = 2
TLV_CHANNEL_ASSIGNMENT = 3

# an enhanced packet block: 8 bytes of block header, interface ID, two timestamp words,
# captured and original length, then the payload
EPB_HEADER_LENGTH = 28
# the TAP header starts with version, reserved and its own length
TAP_HEADER_LENGTH = 4

# enhanced packet block options, and the bits of the flags option the receiver sets
# ([pcapng] 4.3.1, where bit 0 is the least significant)
OPTION_CODE_END_OF_OPTIONS = 0
OPTION_CODE_EPB_FLAGS = 2
EPB_FLAGS_CRC_ERROR = 1 << 24

Packet = namedtuple("Packet", ["channel", "bit_rate", "rssi", "payload", "crc_error", "fcs_length"])


def block_type(block):
    """Return the pcapng block type of one message."""
    return struct.unpack("<I", block[:4])[0]


def parse_packet(block):
    """Parse one enhanced packet block into its TAP metadata and payload."""
    assert block_type(block) == ENHANCED_PACKET_BLOCK, "not an enhanced packet block"
    captured_length = struct.unpack("<I", block[20:24])[0]
    tap_length = struct.unpack("<H", block[EPB_HEADER_LENGTH + 2:EPB_HEADER_LENGTH + 4])[0]

    channel = bit_rate = rssi = None
    offset = EPB_HEADER_LENGTH + TAP_HEADER_LENGTH
    while offset < EPB_HEADER_LENGTH + tap_length:
        tlv_type, tlv_length = struct.unpack("<HH", block[offset:offset + 4])
        value = block[offset + 4:offset + 4 + tlv_length]
        if tlv_type == TLV_CHANNEL_ASSIGNMENT:
            channel = struct.unpack("<H", value[:2])[0]
        elif tlv_type == TLV_BIT_RATE:
            bit_rate = struct.unpack("<I", value[:4])[0]
        elif tlv_type == TLV_RSS:
            rssi = struct.unpack("<f", value[:4])[0]
        # TLV lengths exclude the padding to the next multiple of four
        offset += 4 + (tlv_length + 3) // 4 * 4

    payload = block[EPB_HEADER_LENGTH + tap_length:EPB_HEADER_LENGTH + captured_length]

    # the options follow the payload and its padding to a multiple of four
    crc_error = fcs_length = None
    offset = EPB_HEADER_LENGTH + (captured_length + 3) // 4 * 4
    while offset + 4 <= len(block) - 4:
        code, length = struct.unpack("<HH", block[offset:offset + 4])
        if code == OPTION_CODE_END_OF_OPTIONS:
            break
        if code == OPTION_CODE_EPB_FLAGS:
            flags = struct.unpack("<I", block[offset + 4:offset + 8])[0]
            crc_error = bool(flags & EPB_FLAGS_CRC_ERROR)
            fcs_length = (flags >> 5) & 0xf
        offset += 4 + (length + 3) // 4 * 4

    return Packet(channel=channel, bit_rate=bit_rate, rssi=rssi, payload=payload,
                  crc_error=crc_error, fcs_length=fcs_length)


def parse_stream(blocks):
    """Split a sequence of blocks into packets and a count of each leading block type."""
    packets = []
    counts = {SECTION_HEADER_BLOCK: 0, INTERFACE_DESCRIPTION_BLOCK: 0}
    for block in blocks:
        kind = block_type(block)
        if kind == ENHANCED_PACKET_BLOCK:
            packets.append(parse_packet(block))
        else:
            assert kind in counts, f"unexpected pcapng block type {kind:#x}"
            counts[kind] += 1
    return packets, counts
