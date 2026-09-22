"""Перекрывающаяся девиация Аллана, АКФ циклов и фазовый слип для F04."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

__all__ = [
    "autocorrelate_durations",
    "overlapping_adev",
    "phase_slip_cycles",
    "valid_averaging_factors",
]

_EPS: Final = 1e-30
_MINIMUM_INTERVALS: Final = 3


def valid_averaging_factors(
    sample_total: int, declared: Sequence[int], maximum_fraction: float
) -> tuple[tuple[int, ...], bool]:
    """Допустимые m: m <= floor(N*доля) и floor(N/m) >= 3, в порядке объявления."""
    cap = int(float(sample_total) * float(maximum_fraction))
    kept: list[int] = []
    truncated = False
    for raw in declared:
        factor = int(raw)
        if factor < 1 or factor > sample_total:
            truncated = True
            continue
        if factor <= cap and sample_total // factor >= _MINIMUM_INTERVALS:
            kept.append(factor)
        else:
            truncated = True
    return tuple(kept), truncated


def overlapping_adev(
    y: Float64Array, factors: Sequence[int], tau0_s: float
) -> tuple[Float64Array, Float64Array]:
    """Перекрывающаяся ADEV дословно по спеке:218-220 для готового ряда y.

    Средние ``ybar`` берутся скользящим окном длины m, разности — со сдвигом m
    (пары без перекрытия), нормировка ``1/(2*(N-2m+1))``. Возвращает сетку
    ``tau = m*tau0`` и ADEV в том же порядке, что ``factors``.
    """
    series = np.asarray(y, dtype=np.float64)
    total = int(series.size)
    taus: list[float] = []
    adevs: list[float] = []
    for raw in factors:
        factor = int(raw)
        count = total - 2 * factor + 1
        if count < 1:
            continue
        window = np.cumsum(series)
        window = window[factor - 1 :] - np.concatenate(([0.0], window[: total - factor]))
        means = window / float(factor)
        diffs = means[factor:] - means[:-factor]
        variance = float(np.sum(diffs * diffs)) / (2.0 * float(count))
        taus.append(float(factor) * float(tau0_s))
        adevs.append(float(np.sqrt(max(variance, 0.0))))
    return np.array(taus, dtype=np.float64), np.array(adevs, dtype=np.float64)


def autocorrelate_durations(
    durations_s: Float64Array, lags: Sequence[int]
) -> tuple[Int64Array, Float64Array]:
    """Нормированная АКФ длительностей циклов на объявленных лагах.

    Описательная, без p-value: циклы одной записи не независимые повторы.
    Нулевая дисперсия (стабильный тон) публикуется нулями, а не NaN: метод
    не выдумывает структуру из ничего.
    """
    series = np.asarray(durations_s, dtype=np.float64)
    total = int(series.size)
    lag_array = np.array([int(lag) for lag in lags], dtype=np.int64)
    if total == 0:
        return lag_array, np.zeros(lag_array.size, dtype=np.float64)
    mean = float(np.mean(series))
    centered = series - mean
    energy = float(np.sum(centered * centered))
    out = np.zeros(lag_array.size, dtype=np.float64)
    if energy <= _EPS * max(1.0, mean * mean):
        return lag_array, out
    for pos, raw in enumerate(lag_array):
        lag = int(raw)
        if lag < 1 or lag >= total:
            continue
        out[pos] = float(np.sum(centered[: total - lag] * centered[lag:])) / energy
    return lag_array, out


def phase_slip_cycles(start_samples: Float64Array, sample_rate_hz: float, f0_hz: float) -> float:
    """Накопленное отклонение границ циклов от номинальной сетки, в циклах.

    ``slip_k = (t_k - t_0 - k/f0) * f0``, публикуется максимум по модулю.
    """
    starts = np.asarray(start_samples, dtype=np.float64)
    if starts.size == 0:
        return 0.0
    times = (starts - float(starts[0])) / float(sample_rate_hz)
    nominal = np.arange(starts.size, dtype=np.float64) / float(f0_hz)
    return float(np.max(np.abs((times - nominal) * float(f0_hz))))
