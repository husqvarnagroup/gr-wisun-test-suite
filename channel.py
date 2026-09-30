# SPDX-FileCopyrightText: Copyright 2026 GARDENA GmbH
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Impairing recorded samples with a channel model, on a per-file calibrated scale.

The recordings differ in absolute level by some 75 dB, so a sweep over
`channel_model`'s `noise_voltage` — an absolute amplitude — would mean something
different for every file. Everything here exists to turn that knob into a signal-to-noise
ratio measured against the bursts each individual file actually contains.

The signal-to-noise ratio used throughout is a *wideband* one: burst power over added
noise power in the full recording bandwidth, at the input of the receiver. The receive
chain's channel filter then discards most of that noise, so the ratio the bit slicer sees
is higher by roughly the ratio of sample rate to filter bandwidth. That makes these
numbers a reproducible knob rather than a statement about Eb/N0, which is all the
regression tests need.
"""

from functools import cache

import numpy as np
from gnuradio import channels

# Length of the moving average used to turn instantaneous power into an envelope, in
# samples. At 1 MS/s this is 100 us, i.e. long enough to average over the modulation and
# short enough to resolve the shortest burst (a 48-octet ACK is about 4 ms).
ENVELOPE_LENGTH = 100

# Percentiles of the envelope taken as the noise floor and as the burst peak. The
# recordings have a burst duty cycle between 4% and 28%, so the peak percentile has to
# sit above the highest of those idle fractions.
NOISE_PERCENTILE = 10
PEAK_PERCENTILE = 99.9

# Least ratio between peak and noise floor for a file to be considered to hold bursts at
# all, as a guard against measuring the noise of an empty recording.
MINIMUM_DYNAMIC_RANGE_DB = 10


class SampleFilePower:
    """Power levels measured from a recorded sample file."""

    def __init__(self, signal, noise):
        """Store in-burst signal power and noise floor power, both linear."""
        self.signal = signal
        self.noise = noise

    @property
    def snr_db(self):
        """Signal-to-noise ratio the recording already has, in dB."""
        return 10 * np.log10(self.signal / self.noise)

    def __str__(self):
        """Describe the measured levels."""
        return (f"signal {10 * np.log10(self.signal):.1f} dB, "
                f"noise floor {10 * np.log10(self.noise):.1f} dB, "
                f"SNR {self.snr_db:.1f} dB")


@cache
def measure_power(filename):
    """Measure in-burst signal power and noise floor of a sample file.

    The envelope is split at the geometric mean of its noise and peak percentiles, i.e. at
    the midpoint in dB, and the signal power is the median of everything above that split.
    Taking the median rather than the peak keeps the value an average over the burst
    instead of over its strongest moment.
    """
    samples = np.fromfile(filename, dtype=np.complex64)
    kernel = np.ones(ENVELOPE_LENGTH) / ENVELOPE_LENGTH
    envelope = np.convolve(np.abs(samples) ** 2, kernel, mode="valid")

    noise = np.percentile(envelope, NOISE_PERCENTILE)
    peak = np.percentile(envelope, PEAK_PERCENTILE)
    dynamic_range_db = 10 * np.log10(peak / noise)
    assert dynamic_range_db >= MINIMUM_DYNAMIC_RANGE_DB, \
        f"{filename} has only {dynamic_range_db:.1f} dB between noise floor and peak"

    in_burst = envelope > np.sqrt(noise * peak)
    return SampleFilePower(signal=float(np.median(envelope[in_burst])), noise=float(noise))


def noise_voltage_for_snr(filename, snr_db):
    """Return the `channel_model` noise voltage giving the requested wideband SNR.

    `channels.channel_model` adds complex Gaussian noise whose total power is exactly the
    square of its `noise_voltage` — see `test_channel.py`, which pins that convention
    down rather than trusting it.
    """
    noise_power = measure_power(filename).signal / 10 ** (snr_db / 10)
    return float(np.sqrt(noise_power))


class ChannelImpairment:
    """The impairments to apply to a recording before receiving it.

    Note that `carrier_offset` is not the `frequency_offset` the receiver is given: that
    one says where in the recorded band the channel sits, whereas this one is an error on
    top of it, of the kind a transmitter's crystal tolerance produces.
    """

    def __init__(self, filename, snr_db=None, carrier_offset_hz=0.0, epsilon=1.0, seed=0):
        """Build an impairment for the given file, from an SNR rather than an amplitude."""
        self.snr_db = snr_db
        self.noise_voltage = 0.0 if snr_db is None else noise_voltage_for_snr(filename, snr_db)
        self.carrier_offset_hz = carrier_offset_hz
        self.epsilon = epsilon
        self.seed = seed

    def make_block(self, sample_rate):
        """Return a `channel_model` block applying these impairments."""
        return channels.channel_model(noise_voltage=self.noise_voltage,
                                      # channel_model wants the offset normalized to the
                                      # sample rate, not in Hz
                                      frequency_offset=self.carrier_offset_hz / sample_rate,
                                      epsilon=self.epsilon,
                                      taps=[1.0 + 0.0j],
                                      noise_seed=self.seed,
                                      block_tags=False)

    def __str__(self):
        """Describe the impairment, for test identifiers and sweep output."""
        parts = ["no noise" if self.snr_db is None else f"SNR {self.snr_db:g} dB"]
        if self.carrier_offset_hz:
            parts.append(f"offset {self.carrier_offset_hz / 1e3:g} kHz")
        if self.epsilon != 1.0:
            parts.append(f"epsilon {self.epsilon:g}")
        return ", ".join(parts) + f", seed {self.seed}"
