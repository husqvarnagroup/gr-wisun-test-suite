# SPDX-FileCopyrightText: Copyright 2026 GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ground-truth reference packets, derived from a clean decode of each sample file.

The recordings carry no stored reference payload bits -- only expected packet lengths
(`sample_files.fileinfo`). This decodes each file with no impairment and keeps the
resulting payloads as ground truth for the bit error rate measurement in
`test_single_channel_noise.py`, after checking each one against the frame check sequence
the receiver already computes -- for both the coded and the uncoded path, now that both
validate it (gr-wisun's `pdu_fec_decode` and `pdu_fcs_check`). A reference that fails that
check is not used: feeding a wrong reference into every bit error count downstream would
be worse than simply having one fewer reference to match against.
"""

from functools import cache

import pmt

from receiver import single_channel_packet_receiver
from sample_files import fileinfo, uses_fec

# Decimation for the clean reference decode. Any value the clean-sample tests pass at
# works; this matches test_single_channel_noise.py's own default.
DECIMATION = 2


@cache
def reference_packets(filename):
    """Return the payloads of a clean decode of `filename`, verified by frame check sequence."""
    _, sample_rate, frequency_offset, channel_spacing, symbol_rate, _, phy_mode_id = fileinfo[filename]
    rx = single_channel_packet_receiver(filename,
                                        sample_rate=sample_rate,
                                        frequency_offset=frequency_offset,
                                        channel_spacing=channel_spacing,
                                        decimation=DECIMATION,
                                        samples_per_symbol=sample_rate // DECIMATION // symbol_rate,
                                        gated_power_squelch=False,
                                        fec=uses_fec(phy_mode_id))
    rx.process()

    messages = rx.get_all_messages()
    valid_tags = rx.get_all_message_tags('wisun-fcs-valid')
    references, rejected = [], 0
    for message, tag in zip(messages, valid_tags, strict=True):
        if pmt.is_null(tag) or not pmt.to_python(pmt.cdr(tag)):
            rejected += 1
            continue
        references.append(bytes(message))
    # Loudly, rather than quietly returning a thinner reference set: every bit error
    # measured later is counted against these, so losing some would weaken that
    # measurement invisibly while the tests still passed.
    assert not rejected, (f"{filename}: {rejected} of {len(messages)} packets from a clean "
                          "decode failed their frame check sequence")
    return references


def hamming_distance(a, b):
    """Count differing bits between two byte sequences of the same length."""
    return sum((x ^ y).bit_count() for x, y in zip(a, b, strict=True))


def best_match(payload, references):
    """Return the reference with the smallest Hamming distance to `payload`.

    Only references of the same length as `payload` are considered, since a Hamming
    distance needs equal-length operands; this also naturally disambiguates recordings
    that hold several packets of the same length, such as repeated pings or ACKs. Returns
    `None` if no reference shares `payload`'s length.
    """
    candidates = [reference for reference in references if len(reference) == len(payload)]
    if not candidates:
        return None
    return min(candidates, key=lambda reference: hamming_distance(payload, reference))
