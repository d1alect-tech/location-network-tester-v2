"""F12: bounded shared-STFT passes по четырём declared scales."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.analysis_store.characterization_settings import StftSettings
from lnt.characterization.f12_contract import INSUFFICIENT_FRAMES, SCALE_UNSUPPORTED
from lnt.characterization.f12_math import antoni_from_moments
from lnt.characterization.records import Status
from lnt.characterization.stft import stream_phase_residual_stft

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f12_result import F12Declarations
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]


@dataclass(frozen=True, slots=True, kw_only=True)
class ScaleObservation:
    """Один STFT scale с frame support и Antoni values."""

    segment_samples: int
    frame_count: int
    frequencies_hz: Float64Array
    spectral_kurtosis: Float64Array
    reason_code: str | None


def observe_scale(  # noqa: PLR0913 - shared STFT scale inputs are explicit
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    *,
    segment_samples: int,
    declarations: F12Declarations,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> ScaleObservation:
    """Собрать один scale через общий complex STFT без второго transform path."""
    if (
        segment_samples not in declarations.segment_samples
        or segment_samples > resources.hard_max_chunk_samples
        or segment_samples > samples.size
        or phase.status is Status.UNAVAILABLE
        or means.status is Status.UNAVAILABLE
    ):
        return _empty(segment_samples, SCALE_UNSUPPORTED)
    settings = _settings(segment_samples, declarations)
    if not _has_search_bin(segment_samples, phase.sample_rate_hz, declarations):
        return _empty(segment_samples, SCALE_UNSUPPORTED)
    frequencies: Float64Array | None = None
    second_moment: Float64Array | None = None
    fourth_moment: Float64Array | None = None
    frame_count = 0
    for chunk in stream_phase_residual_stft(
        samples,
        phase,
        means,
        sample_rate_hz=phase.sample_rate_hz,
        settings=settings,
        resources=resources,
        segment_samples=segment_samples,
        checkpoint=checkpoint,
    ):
        if checkpoint is not None:
            checkpoint()
        current_frequencies = np.asarray(chunk.frequencies_hz, dtype=np.float64)
        if frequencies is None:
            frequencies = current_frequencies
            second_moment = np.zeros(current_frequencies.size, dtype=np.float64)
            fourth_moment = np.zeros(current_frequencies.size, dtype=np.float64)
        elif not np.array_equal(frequencies, current_frequencies):
            raise ValueError("F12 STFT frequency domain changed within one scale")
        power = np.abs(chunk.coefficients) ** 2
        if second_moment is None or fourth_moment is None:
            raise ValueError("F12 STFT scale lost its frequency moments")
        second_moment += np.sum(power, axis=1)
        fourth_moment += np.sum(power * power, axis=1)
        frame_count += int(chunk.frame_indices.size)
    if frequencies is None or second_moment is None or fourth_moment is None:
        return ScaleObservation(
            segment_samples=segment_samples,
            frame_count=frame_count,
            frequencies_hz=np.empty(0, dtype=np.float64),
            spectral_kurtosis=np.empty(0, dtype=np.float64),
            reason_code=INSUFFICIENT_FRAMES,
        )
    if frame_count < declarations.minimum_frames:
        return ScaleObservation(
            segment_samples=segment_samples,
            frame_count=frame_count,
            frequencies_hz=frequencies,
            spectral_kurtosis=np.empty(0, dtype=np.float64),
            reason_code=INSUFFICIENT_FRAMES,
        )
    return ScaleObservation(
        segment_samples=segment_samples,
        frame_count=frame_count,
        frequencies_hz=frequencies,
        spectral_kurtosis=antoni_from_moments(second_moment, fourth_moment, frame_count),
        reason_code=None,
    )


def _has_search_bin(
    segment_samples: int, sample_rate_hz: float, declarations: F12Declarations
) -> bool:
    frequencies = np.fft.rfftfreq(segment_samples, d=1.0 / sample_rate_hz)
    high_hz = min(declarations.analysis_high_hz, declarations.nyquist_fraction_max * sample_rate_hz)
    return bool(
        np.any(
            (frequencies > 0.0)
            & (frequencies >= declarations.analysis_low_hz)
            & (frequencies <= high_hz)
        )
    )


def _settings(segment_samples: int, declarations: F12Declarations) -> StftSettings:
    return StftSettings(
        window=declarations.window,
        segment_samples=segment_samples,
        overlap_fraction=declarations.overlap_fraction,
        detrend=declarations.detrend,
        analysis_low_hz=declarations.analysis_low_hz,
        analysis_high_hz=declarations.analysis_high_hz,
        nyquist_fraction_max=declarations.nyquist_fraction_max,
    )


def _empty(segment_samples: int, reason_code: str) -> ScaleObservation:
    return ScaleObservation(
        segment_samples=segment_samples,
        frame_count=0,
        frequencies_hz=np.empty(0, dtype=np.float64),
        spectral_kurtosis=np.empty(0, dtype=np.float64),
        reason_code=reason_code,
    )
