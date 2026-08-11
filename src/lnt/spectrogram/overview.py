"""Линейная агрегация ограниченного log-frequency обзора."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.errors import InputError
from lnt.spectrogram.models import (
    MAX_OVERVIEW_FREQUENCY_BANDS,
    MAX_OVERVIEW_TIME_BINS,
    CancellationToken,
    SpectrogramOverview,
    StftSettings,
)
from lnt.spectrogram.stft import frame_count, frequencies, open_samples, stream_power

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

DEFAULT_DB_REFERENCE: Final = 1.0
DEFAULT_FLOOR_DB: Final = -200.0
DEFAULT_CEILING_DB: Final = 100.0


def linear_power_to_db(
    power: NDArray[np.float64],
    reference: float,
    floor_db: float,
    ceiling_db: float,
) -> NDArray[np.float32]:
    """Конвертирует только конечный линейный агрегат; NaN остаются NaN."""
    output = np.full(power.shape, np.nan, dtype=np.float32)
    available = np.isfinite(power) & (power >= 0.0)
    output[available] = np.asarray(
        np.clip(
            10.0 * np.log10(np.maximum(power[available] / reference, np.finfo(np.float64).tiny)),
            floor_db,
            ceiling_db,
        ),
        dtype=np.float32,
    )
    return output


def build_overview(  # noqa: PLR0913 - compute boundary exposes explicit safety caps
    sample_path: Path,
    *,
    sample_rate_hz: float,
    settings: StftSettings,
    max_time_bins: int = MAX_OVERVIEW_TIME_BINS,
    max_frequency_bands: int = MAX_OVERVIEW_FREQUENCY_BANDS,
    band_low_hz: float,
    band_high_hz: float,
    cancellation: CancellationToken | None = None,
) -> SpectrogramOverview:
    """Строит bounded overview, суммируя linear power и coverage.

    Рёбра полос — геометрическая сетка между положительными low/high. DC и
    частоты ниже первого ребра исключаются; high является открытой границей.
    """
    if not 1 <= max_time_bins <= MAX_OVERVIEW_TIME_BINS:
        raise InputError("спектрограмма: max_time_bins вне предела 1..2048")
    if not 1 <= max_frequency_bands <= MAX_OVERVIEW_FREQUENCY_BANDS:
        raise InputError("спектрограмма: max_frequency_bands вне предела 1..1024")
    nyquist = sample_rate_hz / 2.0
    effective_high = min(band_high_hz, nyquist)
    if sample_rate_hz <= 0 or band_low_hz <= 0 or effective_high <= band_low_hz:
        raise InputError("спектрограмма: пустая или некорректная рабочая полоса")
    samples = open_samples(sample_path)
    frames = frame_count(int(samples.size), settings)
    if frames == 0:
        raise InputError("спектрограмма: запись короче одного окна STFT")
    time_bins = min(max_time_bins, frames)
    edges = np.geomspace(band_low_hz, effective_high, max_frequency_bands + 1)
    frequency = frequencies(sample_rate_hz, settings)
    frequency_cells = np.searchsorted(edges, frequency, side="right") - 1
    sums = np.zeros((max_frequency_bands, time_bins), dtype=np.float64)
    coverage = np.zeros(sums.shape, dtype=np.uint32)
    for chunk in stream_power(samples, sample_rate_hz, settings, cancellation):
        frame_indices = chunk.first_frame + np.arange(chunk.power.shape[1])
        time_cells = np.minimum(frame_indices * time_bins // frames, time_bins - 1)
        for source_frequency, target_frequency in enumerate(frequency_cells):
            if 0 <= target_frequency < max_frequency_bands:
                np.add.at(sums[target_frequency], time_cells, chunk.power[source_frequency])
                np.add.at(coverage[target_frequency], time_cells, 1)
    linear = np.full(sums.shape, np.nan, dtype=np.float64)
    np.divide(sums, coverage, out=linear, where=coverage > 0)
    frame_time = (
        np.arange(frames) * settings.hop_samples + settings.segment_samples / 2
    ) / sample_rate_hz
    time_axis = np.array(
        [
            frame_time[
                np.minimum(np.arange(frames) * time_bins // frames, time_bins - 1) == cell
            ].mean()
            for cell in range(time_bins)
        ],
        dtype=np.float64,
    )
    return SpectrogramOverview(
        power_db=linear_power_to_db(
            linear, DEFAULT_DB_REFERENCE, DEFAULT_FLOOR_DB, DEFAULT_CEILING_DB
        ),
        linear_power=linear,
        coverage=coverage,
        time_s=time_axis,
        frequency_hz=np.sqrt(edges[:-1] * edges[1:]),
        frequency_edges_hz=edges,
        settings=settings,
        db_reference=DEFAULT_DB_REFERENCE,
        floor_db=DEFAULT_FLOOR_DB,
        ceiling_db=DEFAULT_CEILING_DB,
    )
