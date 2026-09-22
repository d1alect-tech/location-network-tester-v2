"""Общая синхронная сетка: ресэмплинг 10 циклов и перечисление полных окон."""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

type Float64Array = NDArray[np.float64]

CYCLES_PER_WINDOW: Final = 10

__all__ = [
    "CYCLES_PER_WINDOW",
    "complete_window_count",
    "nominal_window_samples",
    "resampled_window",
    "window_start_sample",
]


def nominal_window_samples(window_s: float, sample_rate_hz: float) -> int:
    """Число отсчётов номинального окна: round(window_s * fs)."""
    return round(float(window_s) * float(sample_rate_hz))


def complete_window_count(sample_count: int, n_nominal: int) -> int:
    """Число полных непересекающихся окон в записи."""
    if int(n_nominal) <= 0:
        return 0
    return int(int(sample_count) // int(n_nominal))


def window_start_sample(index: int, n_nominal: int) -> int:
    """Стартовый отсчёт окна: окна идут подряд без перекрытия."""
    return int(index) * int(n_nominal)


def resampled_window(
    signal: Float64Array,
    fs: float,
    f1: float,
    start_sample: int,
    n_nominal: int,
) -> Float64Array:
    """Ресэмплинг ровно 10 циклов от ``start_sample`` линейной интерполяцией."""
    span = CYCLES_PER_WINDOW / float(f1) * float(fs)
    source = np.linspace(
        float(start_sample),
        float(start_sample) + span,
        int(n_nominal),
        endpoint=False,
    )
    clipped = np.clip(source, 0.0, float(signal.size - 1) - 1e-9)
    indices = np.arange(signal.size, dtype=np.float64)
    return np.interp(clipped, indices, signal).astype(np.float64)
