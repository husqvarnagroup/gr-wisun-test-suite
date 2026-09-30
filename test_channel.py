# SPDX-FileCopyrightText: Copyright 2026 GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the channel model helper.

The noise tests are only as meaningful as the scale they sweep, so the conversion from a
signal-to-noise ratio to a `channel_model` noise voltage is checked here against the block
itself rather than taken on trust.
"""

import numpy as np
import pytest
from gnuradio import blocks, channels, gr

from channel import measure_power, noise_voltage_for_snr
from sample_files import fileinfo

NOISE_SAMPLES = 200000

# Tolerance for a measured power against its nominal value, in dB. With 200000 samples the
# standard error on the mean power is well under 1%, so this is generous.
POWER_TOLERANCE_DB = 0.2


def added_noise_power(noise_voltage, seed=42):
    """Return the mean power `channel_model` adds to a silent input."""
    tb = gr.top_block()
    source = blocks.vector_source_c([0j] * NOISE_SAMPLES, False)
    channel = channels.channel_model(noise_voltage=noise_voltage,
                                     frequency_offset=0.0,
                                     epsilon=1.0,
                                     taps=[1.0 + 0.0j],
                                     noise_seed=seed,
                                     block_tags=False)
    sink = blocks.vector_sink_c()
    tb.connect(source, channel, sink)
    tb.run()
    return float(np.mean(np.abs(np.array(sink.data())) ** 2))


@pytest.mark.parametrize("noise_voltage", [0.1, 0.5, 1.0, 2.0])
def test_noise_power_is_the_square_of_the_noise_voltage(noise_voltage):
    """`channel_model` must add noise of power `noise_voltage ** 2`.

    This is the one assumption `noise_voltage_for_snr` makes. If a GNU Radio release ever
    changes the convention, every signal-to-noise ratio in the noise tests silently shifts,
    so it is asserted rather than documented.
    """
    measured = added_noise_power(noise_voltage)
    expected = noise_voltage ** 2
    assert abs(10 * np.log10(measured / expected)) < POWER_TOLERANCE_DB


@pytest.mark.parametrize("filename", list(fileinfo))
def test_sample_files_have_measurable_bursts(filename):
    """Every sample file must have a burst level well clear of its noise floor."""
    power = measure_power(filename)
    assert power.signal > power.noise
    # all recordings were made over cable or a short air path, so this is a low bar
    assert power.snr_db > 20, f"{filename}: {power}"


@pytest.mark.parametrize("snr_db", [0, 10, 20])
@pytest.mark.parametrize("filename", list(fileinfo))
def test_noise_voltage_produces_the_requested_snr(filename, snr_db):
    """The requested ratio must come out as the ratio of measured signal to added noise."""
    noise_voltage = noise_voltage_for_snr(filename, snr_db)
    achieved_db = 10 * np.log10(measure_power(filename).signal / added_noise_power(noise_voltage))
    assert abs(achieved_db - snr_db) < POWER_TOLERANCE_DB
