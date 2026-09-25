"""F18: reuse shared phase-residual STFT и сборка declared triad-столбцов."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.phase import phase_residual
from lnt.characterization.stft import stream_phase_residual_stft

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

    from lnt.analysis_store.characterization_settings import ResourceLimits, StftSettings
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Complex128Array = NDArray[np.complex128]
type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

# Один суррогат в памяти: остаток + суррогат + половина rFFT-спектра + temporaries.
SURROGATE_BYTES_PER_SAMPLE: int = 32
_RESIDUAL_BYTES_PER_SAMPLE: int = 64


def zero_phase_means(means: PhaseMeans) -> PhaseMeans:
    """Суррогат строится из уже phase-removed остатка: mean не вычитается дважды."""
    return replace(means, means_v=np.zeros_like(np.asarray(means.means_v, dtype=np.float64)))


def triad_coefficients(  # noqa: PLR0913 - полный shared STFT input
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    *,
    sample_rate_hz: float,
    settings: StftSettings,
    resources: ResourceLimits,
    distinct_bins: Int64Array,
    checkpoint: Callable[[], None] | None = None,
) -> Complex128Array:
    """Собрать коэффициенты (D, frames) только для объявленных exact bins.

    Используется единственный framing-путь репозитория — `stream_phase_residual_stft`.
    Никакого второго STFT: собираются те же complete, fully phase-qualified кадры.
    """
    blocks: list[Complex128Array] = []
    rows: Int64Array | None = None
    for chunk in stream_phase_residual_stft(
        samples,
        phase,
        means,
        sample_rate_hz=sample_rate_hz,
        settings=settings,
        resources=resources,
        checkpoint=checkpoint,
    ):
        if rows is None:
            rows = _rows(chunk.frequencies_hz, distinct_bins, settings, sample_rate_hz)
        blocks.append(np.asarray(chunk.coefficients[rows, :], dtype=np.complex128))
    if rows is None or not blocks:
        return np.empty((int(np.asarray(distinct_bins).size), 0), dtype=np.complex128)
    return np.concatenate(blocks, axis=1)


def observed_residual(
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    *,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> Float64Array | None:
    """Материализовать bounded phase-removed остаток — источник обоих null.

    Это тот же shared `phase_residual`, что и у framing-пути; второй STFT или
    второй framing-путь не создаётся. Остаток уже очищен от 64-бинного phase mean,
    поэтому суррогат проходит дальше с нулевым mean и не вычитает его дважды.

    ``None`` означает, что корень фазы не покрывает запись целиком: нули на
    неквалифицированных позициях исказили бы спектр суррогата, поэтому источник
    null считается негодным. Это состояние записи, а не повреждение данных, —
    поэтому сигнал возвращается значением, а не исключением: непойманное
    исключение унесло бы весь прогон характеризации, а не одно семейство.
    """
    values = np.asarray(samples, dtype=np.float64)
    capacity = min(
        int(resources.hard_max_chunk_samples),
        int(resources.max_work_bytes) // _RESIDUAL_BYTES_PER_SAMPLE,
    )
    if capacity <= 0:
        raise ValueError("F18 resource limits leave no residual capacity")
    parts: list[Float64Array] = []
    for start in range(0, int(values.size), capacity):
        if checkpoint is not None:
            checkpoint()
        stop = min(int(values.size), start + capacity)
        residual, valid = phase_residual(values, phase, means, start, stop, resources=resources)
        if not bool(np.all(valid)):
            return None
        parts.append(residual)
    if not parts:
        return np.empty(0, dtype=np.float64)
    return np.concatenate(parts)


def _rows(
    band_hz: Float64Array,
    distinct_bins: Int64Array,
    settings: StftSettings,
    sample_rate_hz: float,
) -> Int64Array:
    """Найти строку shared band-оси для каждого exact bin; ось вычисляется тем же rfftfreq."""
    if band_hz.size == 0:
        raise ValueError("F18 triad coefficients found no shared STFT band")
    axis = np.fft.rfftfreq(int(settings.segment_samples), d=1.0 / sample_rate_hz)
    rows = np.searchsorted(band_hz, axis[np.asarray(distinct_bins, dtype=np.int64)])
    rows = np.clip(rows, 0, band_hz.size - 1)
    if not np.array_equal(band_hz[rows], axis[np.asarray(distinct_bins, dtype=np.int64)]):
        raise ValueError("F18 exact triad bin is absent from the shared STFT band")
    return np.asarray(rows, dtype=np.int64)
