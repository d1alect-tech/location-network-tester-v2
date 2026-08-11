"""Точная bounded-рекомпутация интервала и полосы."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np
from scipy import signal

from lnt.spectrogram.errors import SpectrogramCancelledError, SpectrogramLimitError
from lnt.spectrogram.models import (
    CancellationToken,
    ExactSpectrogram,
    StftSettings,
    ZoomLimits,
    ZoomRequest,
)
from lnt.spectrogram.overview import (
    DEFAULT_CEILING_DB,
    DEFAULT_DB_REFERENCE,
    DEFAULT_FLOOR_DB,
    linear_power_to_db,
)
from lnt.spectrogram.stft import frame_count, frequencies, open_samples

if TYPE_CHECKING:
    from pathlib import Path


def compute_exact_zoom(  # noqa: PLR0913 - request, limits and recipe are separate contracts
    sample_path: Path,
    *,
    sample_rate_hz: float,
    settings: StftSettings,
    request: ZoomRequest,
    limits: ZoomLimits,
    cancellation: CancellationToken | None = None,
) -> ExactSpectrogram:
    """Проверяет размеры до slice/FFT и возвращает точные SciPy STFT cells."""
    started = time.monotonic()
    samples = open_samples(sample_path)
    start = round(request.start_s * sample_rate_hz)
    stop = min(round(request.end_s * sample_rate_hz), int(samples.size))
    sample_count = max(0, stop - start)
    if sample_count > limits.max_samples:
        raise SpectrogramLimitError("samples", sample_count, limits.max_samples)
    all_frequency = frequencies(sample_rate_hz, settings)
    mask = (all_frequency >= request.low_hz) & (all_frequency <= request.high_hz)
    frames = frame_count(sample_count, settings)
    cells = frames * int(np.count_nonzero(mask))
    if cells > limits.max_cells:
        raise SpectrogramLimitError("cells", cells, limits.max_cells)
    _check(cancellation, started, limits)
    stft = vars(signal)["stft"]
    _, time_axis, transformed = stft(
        samples[start:stop],
        fs=sample_rate_hz,
        window=settings.window,
        nperseg=settings.segment_samples,
        noverlap=settings.segment_samples - settings.hop_samples,
        detrend=settings.detrend,
        boundary=None,
        padded=False,
        scaling=settings.scaling,
    )
    _check(cancellation, started, limits)
    linear = np.asarray(np.abs(transformed[mask]) ** 2, dtype=np.float64)
    return ExactSpectrogram(
        linear_power=linear,
        power_db=linear_power_to_db(
            linear, DEFAULT_DB_REFERENCE, DEFAULT_FLOOR_DB, DEFAULT_CEILING_DB
        ),
        time_s=np.asarray(time_axis + request.start_s, dtype=np.float64),
        frequency_hz=all_frequency[mask].copy(),
        settings=settings,
        db_reference=DEFAULT_DB_REFERENCE,
        floor_db=DEFAULT_FLOOR_DB,
        ceiling_db=DEFAULT_CEILING_DB,
    )


def _check(token: CancellationToken | None, started: float, limits: ZoomLimits) -> None:
    if token is not None and token.cancelled():
        raise SpectrogramCancelledError
    elapsed = time.monotonic() - started
    if elapsed > limits.max_wall_time_s:
        raise SpectrogramLimitError("wall_time_s", elapsed, limits.max_wall_time_s)
