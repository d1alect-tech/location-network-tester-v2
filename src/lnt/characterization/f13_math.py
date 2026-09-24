"""F13: сетка лагов, MAD и нормализованная FFT-корреляция остатков."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy import signal

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

PAIR_INDICES: Final = ((0, 1), (0, 2), (1, 2))


def declared_lag_samples(
    low_s: float, high_s: float, sample_rate_hz: float, maximum_points: int
) -> Int64Array:
    """Дать целочисленные лаги с шагом 1/fs; кэп прореживает сетку, а не обрезает диапазон.

    Спека объявляет диапазон `[-0.02, +0.02] s` И кап 2049 точки одновременно. Кэп
    ограничивает ЧИСЛО точек, а диапазон заморожен рецептом, поэтому при нехватке
    места шаг умножается на целое число вокруг нуля: сохраняются и границы, и
    симметрия, и нулевой лаг. Обрезка по краям оставила бы ±2.048 мс вместо
    объявленных ±20 мс — при 50 Гц это один период сети, — и `F13Result` заявлял бы
    `lag_low_s`/`lag_high_s`, которых в сетке нет.
    """
    if (
        not all(math.isfinite(value) for value in (low_s, high_s, sample_rate_hz))
        or sample_rate_hz <= 0.0
        or low_s >= 0.0
        or high_s <= 0.0
        or low_s >= high_s
        or maximum_points <= 0
    ):
        raise ValueError("F13 lag declaration is outside its numeric domain")
    lower = round(low_s * sample_rate_hz)
    upper = round(high_s * sample_rate_hz)
    if upper - lower + 1 <= maximum_points:
        return np.arange(lower, upper + 1, dtype=np.int64)
    if maximum_points == 1:
        return np.zeros(1, dtype=np.int64)
    span = min(-lower, upper)
    decimation = max(1, math.ceil((2 * span + 1) / (maximum_points - 1)))
    reach = min(span // decimation, (maximum_points - 1) // 2)
    return np.arange(-reach, reach + 1, dtype=np.int64) * decimation


def envelope_mad(values: Float64Array) -> float:
    """Вернуть population MAD без нормализации 1.4826."""
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size == 0 or not np.all(np.isfinite(data)):
        raise ValueError("F13 MAD needs one finite nonempty vector")
    centre = float(np.median(data))
    return float(np.median(np.abs(data - centre)))


def select_peak_lag(correlations: Float64Array, lag_samples: Int64Array) -> int:
    """Выбрать max |r|, затем min |lag|, затем отрицательный знак."""
    values = np.asarray(correlations, dtype=np.float64)
    lags = np.asarray(lag_samples, dtype=np.int64)
    if values.shape != lags.shape or values.ndim != 1 or values.size == 0:
        raise ValueError("F13 lag selection needs one nonempty correlation axis")
    if not np.all(np.isfinite(values)):
        raise ValueError("F13 lag correlations must be finite")
    order = sorted(
        range(values.size),
        key=lambda index: (-abs(float(values[index])), abs(int(lags[index])), int(lags[index])),
    )
    return order[0]


@dataclass(slots=True)
class LagAccumulator:
    """Суммы FFT-корреляции по непрерывным квалифицированным спанам."""

    lag_samples: Int64Array
    cross: Float64Array
    first_energy: Float64Array
    second_energy: Float64Array
    usable_segment_count: int = 0

    @classmethod
    def empty(cls, lag_samples: Int64Array) -> LagAccumulator:
        """Создать три пары с пустыми накопителями."""
        shape = (len(PAIR_INDICES), lag_samples.size)
        return cls(
            lag_samples=np.asarray(lag_samples, dtype=np.int64).copy(),
            cross=np.zeros(shape, dtype=np.float64),
            first_energy=np.zeros(shape, dtype=np.float64),
            second_energy=np.zeros(shape, dtype=np.float64),
        )

    def add(self, values: Float64Array) -> None:
        """Добавить один непрерывный общий.support всех трёх полос."""
        data = np.asarray(values, dtype=np.float64)
        largest = int(np.max(np.abs(self.lag_samples)))
        if data.shape != (3, data.shape[1]) or data.shape[1] <= largest:
            return
        self.usable_segment_count += 1
        for pair, (first, second) in enumerate(PAIR_INDICES):
            correlation, first_energy, second_energy = _lag_terms(
                data[second], data[first], self.lag_samples
            )
            self.cross[pair] += correlation
            self.first_energy[pair] += first_energy
            self.second_energy[pair] += second_energy

    def normalized(self) -> Float64Array:
        """Нормировать накопленные спаны по всей энергии перекрытий."""
        denominator = np.sqrt(self.first_energy * self.second_energy)
        if (
            self.usable_segment_count == 0
            or not np.all(np.isfinite(denominator))
            or bool(np.any(denominator <= 0.0))
        ):
            raise ValueError("F13 lag support has no positive normalized overlap")
        return np.clip(self.cross / denominator, -1.0, 1.0)


def _lag_terms(
    first: Float64Array, second: Float64Array, lag_samples: Int64Array
) -> tuple[Float64Array, Float64Array, Float64Array]:
    """Вернуть cross/energy; положительный лаг означает, что вторая полоса позже."""
    size = first.size
    full_lags = signal.correlation_lags(size, size, mode="full")
    positions = np.searchsorted(full_lags, lag_samples)
    if np.any(positions < 0) or np.any(positions >= full_lags.size):
        raise ValueError("F13 lag grid left the segment correlation domain")
    full = np.asarray(signal.correlate(first, second, mode="full", method="fft"))
    cross = full[positions]
    first_cumsum = np.concatenate((np.asarray([0.0]), np.cumsum(first * first)))
    second_cumsum = np.concatenate((np.asarray([0.0]), np.cumsum(second * second)))
    first_energy = np.empty(lag_samples.size, dtype=np.float64)
    second_energy = np.empty(lag_samples.size, dtype=np.float64)
    for index, lag in enumerate(lag_samples.tolist()):
        if lag >= 0:
            first_energy[index] = first_cumsum[size - lag]
            second_energy[index] = second_cumsum[size] - second_cumsum[lag]
        else:
            first_energy[index] = first_cumsum[size] - first_cumsum[-lag]
            second_energy[index] = second_cumsum[size + lag]
    return cross, first_energy, second_energy
