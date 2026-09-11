"""Bounded complex STFT of the qualified phase residual."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.phase import phase_residual
from lnt.characterization.records import Status
from lnt.errors import InputError
from lnt.spectrogram.models import StftSettings as SpectrogramStftSettings
from lnt.spectrogram.stft import frame_count, frequencies, stream_complex

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.characterization_settings import ResourceLimits, StftSettings
    from lnt.characterization.phase import PhaseCycles, PhaseMeans

type FloatInput = NDArray[np.float32] | NDArray[np.float64]

_MAX_FRAME_CHUNK = 256
_RESIDUAL_WORK_BYTES_PER_SAMPLE = 64
_TRANSFORM_WORK_BYTES_PER_SAMPLE = 32
_TRANSFORM_WORK_BYTES_PER_COEFFICIENT = 48


@dataclass(frozen=True, slots=True, kw_only=True)
class ResidualStftChunk:
    """Qualified globally indexed phase-residual STFT frames."""

    frame_indices: NDArray[np.int64]
    time_s: NDArray[np.float64]
    frequencies_hz: NDArray[np.float64]
    coefficients: NDArray[np.complex128]
    valid_frames: NDArray[np.bool_]


def stream_phase_residual_stft(  # noqa: PLR0913
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    *,
    sample_rate_hz: float,
    settings: StftSettings,
    resources: ResourceLimits,
    segment_samples: int | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> Iterator[ResidualStftChunk]:
    """Yield only complete, fully phase-qualified, globally anchored frames."""
    if checkpoint is not None:
        checkpoint()
    length = settings.segment_samples if segment_samples is None else segment_samples
    transform_settings = _transform_settings(length, settings)
    _validate_inputs(samples, phase, sample_rate_hz, length, resources)
    all_frequencies = frequencies(sample_rate_hz, transform_settings)
    effective_high_hz = min(
        settings.analysis_high_hz,
        settings.nyquist_fraction_max * sample_rate_hz,
    )
    frequency_indices = np.flatnonzero(
        (all_frequencies > 0.0)
        & (all_frequencies >= settings.analysis_low_hz)
        & (all_frequencies <= effective_high_hz)
    )
    total_frames = frame_count(int(samples.size), transform_settings)
    if (
        total_frames == 0
        or frequency_indices.size == 0
        or phase.status is Status.UNAVAILABLE
        or not np.any(means.valid_bins)
    ):
        if checkpoint is not None:
            checkpoint()
        return

    frame_capacity = _frame_capacity(
        transform_settings,
        resources,
        int(frequency_indices.size),
        int(all_frequencies.nbytes),
    )
    for first_frame in range(0, total_frames, frame_capacity):
        if checkpoint is not None:
            checkpoint()
        batch_frames = min(frame_capacity, total_frames - first_frame)
        start_sample = first_frame * transform_settings.hop_samples
        stop_sample = start_sample + length + (batch_frames - 1) * transform_settings.hop_samples
        residual, valid_samples = phase_residual(
            samples,
            phase,
            means,
            start_sample,
            stop_sample,
        )
        valid_frames = _valid_frames(valid_samples, transform_settings, batch_frames)
        for transformed in stream_complex(
            residual,
            sample_rate_hz,
            transform_settings,
            max_chunk_samples=int(residual.size),
            checkpoint=checkpoint,
        ):
            local_count = transformed.coefficients.shape[1]
            local_valid = valid_frames[
                transformed.first_frame : transformed.first_frame + local_count
            ]
            qualified = np.flatnonzero(local_valid)
            if qualified.size == 0:
                continue
            global_indices = np.asarray(
                first_frame + transformed.first_frame + qualified,
                dtype=np.int64,
            )
            coefficients = np.asarray(
                transformed.coefficients[np.ix_(frequency_indices, qualified)],
                dtype=np.complex128,
            )
            yield ResidualStftChunk(
                frame_indices=global_indices,
                time_s=np.asarray(
                    (global_indices * transform_settings.hop_samples + length / 2) / sample_rate_hz,
                    dtype=np.float64,
                ),
                frequencies_hz=np.asarray(all_frequencies[frequency_indices], dtype=np.float64),
                coefficients=coefficients,
                valid_frames=np.ones(global_indices.size, dtype=np.bool_),
            )
    if checkpoint is not None:
        checkpoint()


def _transform_settings(length: int, settings: StftSettings) -> SpectrogramStftSettings:
    hop = max(1, round(length * (1.0 - settings.overlap_fraction)))
    return SpectrogramStftSettings(
        version=1,
        window="hann",
        segment_samples=length,
        hop_samples=hop,
        detrend="constant",
        scaling="spectrum",
    )


def _validate_inputs(
    samples: FloatInput,
    phase: PhaseCycles,
    sample_rate_hz: float,
    length: int,
    resources: ResourceLimits,
) -> None:
    if samples.ndim != 1 or not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("characterization STFT: invalid samples or sample_rate_hz")
    if phase.sample_count != int(samples.size) or phase.sample_rate_hz != sample_rate_hz:
        raise InputError("characterization STFT: phase reference does not match samples")
    if length > resources.hard_max_chunk_samples:
        raise InputError("characterization STFT: segment_samples exceeds hard limit")


def _frame_capacity(
    settings: SpectrogramStftSettings,
    resources: ResourceLimits,
    selected_frequency_count: int,
    retained_bytes: int,
) -> int:
    sample_cap = min(
        resources.hard_max_chunk_samples,
        max(resources.chunk_samples, settings.segment_samples),
    )
    by_samples = 1 + (sample_cap - settings.segment_samples) // settings.hop_samples
    full_frequency_count = settings.segment_samples // 2 + 1
    for frames in range(min(_MAX_FRAME_CHUNK, by_samples), 0, -1):
        span = settings.segment_samples + (frames - 1) * settings.hop_samples
        planned_bytes = (
            retained_bytes
            + span * _RESIDUAL_WORK_BYTES_PER_SAMPLE
            + frames * settings.segment_samples * _TRANSFORM_WORK_BYTES_PER_SAMPLE
            + frames * full_frequency_count * _TRANSFORM_WORK_BYTES_PER_COEFFICIENT
            + frames * selected_frequency_count * np.dtype(np.complex128).itemsize
        )
        if planned_bytes <= resources.max_work_bytes:
            return frames
    raise InputError("characterization STFT: max_work_bytes is too small for one frame")


def _valid_frames(
    valid_samples: NDArray[np.bool_],
    settings: SpectrogramStftSettings,
    count: int,
) -> NDArray[np.bool_]:
    windows = np.lib.stride_tricks.sliding_window_view(
        valid_samples,
        settings.segment_samples,
    )[:: settings.hop_samples]
    return np.asarray(np.all(windows[:count], axis=1), dtype=np.bool_)
