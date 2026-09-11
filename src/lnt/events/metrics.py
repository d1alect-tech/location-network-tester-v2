"""Deterministic metrics for already delimited candidate events."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.events.models import CandidateEvent, Polarity, QualificationStatus

if TYPE_CHECKING:
    from typing import Literal

    from lnt.events.settings import DetectionSettings, FrequencyBand

FloatArray = NDArray[np.floating]
MINIMUM_FFT_SAMPLES = 4


@dataclass(frozen=True, slots=True, kw_only=True)
class EventRun:
    """Final merged candidate bounds and robust threshold measurements."""

    start: int
    end: int
    peak: int
    peak_value: float
    peak_deviation: float
    peak_sigma: float
    positive: bool
    negative: bool
    excess_energy_sum: float


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricContext:
    """Shared signal and detector metadata used to materialize events."""

    samples: FloatArray
    sample_rate_hz: float
    settings: DetectionSettings


def materialize_event(run: EventRun, context: MetricContext) -> CandidateEvent:
    """Build all persisted metrics for one merged candidate run."""
    length = run.end - run.start + 1
    snr = run.peak_deviation / run.peak_sigma
    if length < context.settings.minimum_event_samples:
        status = QualificationStatus.TOO_SHORT
    elif snr < context.settings.minimum_snr:
        status = QualificationStatus.BELOW_MINIMUM_SNR
    else:
        status = QualificationStatus.QUALIFIED
    if run.positive and run.negative:
        polarity = Polarity.BIPOLAR
    elif run.positive:
        polarity = Polarity.POSITIVE
    else:
        polarity = Polarity.NEGATIVE
    span = np.asarray(context.samples[run.start : run.end + 1], dtype=np.float64)
    clipped = bool(
        np.any(span <= context.settings.rail_low_v + context.settings.rail_tolerance_v)
        or np.any(span >= context.settings.rail_high_v - context.settings.rail_tolerance_v)
    )
    return CandidateEvent(
        start_sample=run.start,
        end_sample=run.end,
        peak_sample=run.peak,
        start_time_s=run.start / context.sample_rate_hz,
        end_time_s=run.end / context.sample_rate_hz,
        peak_time_s=run.peak / context.sample_rate_hz,
        peak_value_v=run.peak_value,
        polarity=polarity,
        dominant_band=_dominant_band(span, context),
        excess_energy_v2_s=run.excess_energy_sum / context.sample_rate_hz,
        snr=snr,
        qualification_status=status,
        boundary=run.start == 0 or run.end == context.samples.size - 1,
        clipped=clipped,
    )


def _dominant_band(span: NDArray[np.float64], context: MetricContext) -> str | None:
    return dominant_band(
        span,
        sample_rate_hz=context.sample_rate_hz,
        bands=context.settings.bands,
        fft_max_samples=context.settings.fft_max_samples,
    )


def dominant_band(
    span: NDArray[np.float64],
    *,
    sample_rate_hz: float,
    bands: tuple[FrequencyBand, ...],
    fft_max_samples: int,
    interval_rule: Literal["closed", "half_open_last_closed"] = "closed",
) -> str | None:
    """Return the strongest declared band from a bounded native-or-strided FFT."""
    if span.size < MINIMUM_FFT_SAMPLES:
        return None
    stride = max(1, math.ceil(span.size / fft_max_samples))
    bounded = span[::stride]
    effective_rate = sample_rate_hz / stride
    spectrum = np.fft.rfft((bounded - np.mean(bounded)) * np.hanning(bounded.size))
    power = np.square(np.abs(spectrum))
    frequencies = np.fft.rfftfreq(bounded.size, d=1.0 / effective_rate)
    last_index = len(bands) - 1
    energies = np.asarray(
        [
            float(
                np.sum(
                    power[
                        (frequencies >= band.low_hz)
                        & (
                            (frequencies <= band.high_hz)
                            if interval_rule == "closed"
                            else (frequencies < band.high_hz)
                            | ((index == last_index) & (frequencies == band.high_hz))
                        )
                    ]
                )
            )
            for index, band in enumerate(bands)
        ]
    )
    if not energies.size or not np.any(energies > 0.0):
        return None
    return bands[int(np.argmax(energies))].name
