"""F18: declared phase-randomized и IAAFT null-ансамбли с явным seed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

type Float64Array = NDArray[np.float64]
type Complex128Array = NDArray[np.complex128]
type Int64Array = NDArray[np.int64]

_TWO_PI: float = 2.0 * np.pi


class F18ZeroResidualError(ValueError):
    """Остаток без энергии: ни IAAFT, ни знаменатель bicoherence не имеют смысла."""


@dataclass(slots=True)
class F18ExceedanceCounter:
    """Счётчик суррогатов, у которых b2 не меньше наблюдённого."""

    observed: Float64Array
    exceedance: Int64Array = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    generated: int = 0

    def __post_init__(self) -> None:
        """Начать с нулевого счётчика той же declared длины, что и наблюдённый домен."""
        self.observed = np.asarray(self.observed, dtype=np.float64)
        if self.exceedance.size == 0:
            self.exceedance = np.zeros(self.observed.size, dtype=np.int64)

    def add(self, surrogate: Float64Array) -> None:
        """Учесть один суррогат; превышением является строго больший b2.

        Строгое `>` вместо `>=` обязательно: для record из exact-bin синусоид b2
        насыщается единицей и у наблюдения, и у каждого суррогата, потому что
        постоянная случайная фаза компоненты всё равно сокращается в
        X(f1)X(f2)conj(X(f1+f2)) между кадрами. Сравнение по равенству считало бы
        весь ансамбль превышением и делало бы семейство вечно незначимым.
        """
        values = np.asarray(surrogate, dtype=np.float64)
        if values.shape != self.observed.shape:
            raise ValueError("F18 surrogate bicoherence left the declared triad domain")
        exceeded = np.isfinite(values) & (values > self.observed)
        self.exceedance += exceeded.astype(np.int64)
        self.generated += 1


def phase_randomized_surrogate(residual: Float64Array, *, rng: np.random.Generator) -> Float64Array:
    """Сохранить модули record FFT, заменив фазы равномерными из явного генератора."""
    values = np.asarray(residual, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("F18 surrogate source must be one finite nonempty residual")
    spectrum = np.fft.rfft(values)
    magnitudes = np.abs(spectrum)
    replacement = np.asarray(magnitudes * np.exp(1j * _TWO_PI * rng.random(magnitudes.size)))
    return np.asarray(
        np.fft.irfft(_force_real_endpoints(replacement, magnitudes), n=values.size),
        dtype=np.float64,
    )


def iaaft_rank_remap(surrogate: Float64Array, observed: Float64Array) -> Float64Array:
    """Exact rank remap: ранги позиций по |surrogate| получают observed значения.

    Набор значений совпадает с observed по битам, включая знак: амплитудное
    распределение сохраняется точно, а не приближённо.
    """
    current = np.asarray(surrogate, dtype=np.float64)
    source = np.asarray(observed, dtype=np.float64)
    if current.shape != source.shape or current.ndim != 1 or current.size == 0:
        raise ValueError("F18 rank remap needs two nonempty vectors of equal length")
    return _remap(current, _rank_ordered(source))


def iaaft_surrogate(
    residual: Float64Array,
    *,
    rng: np.random.Generator,
    iterations: int,
    tolerance: float,
) -> tuple[Float64Array, float]:
    """IAAFT: seeded permutation, затем declared rank-remap и magnitude replacement.

    Rank remap переносит observed значения, отсортированные по |x|, на позиции,
    отсортированные по текущей |y|, — распределение амплитуд сохраняется точно
    (вместе со знаком). Replacement подставляет observed модули Фурье и держит
    фазу y, поэтому power spectrum выданного суррогата равен observed спектру.
    Возвращается и относительная RMS-ошибка модулей для declared acceptance-теста.
    """
    values = np.asarray(residual, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("F18 IAAFT source must be one finite nonempty residual")
    if iterations <= 0 or not 0.0 < tolerance < 1.0:
        raise ValueError("F18 IAAFT iterations and tolerance are outside their domain")
    observed = np.abs(np.fft.rfft(values))
    scale = float(np.sqrt(np.mean(observed**2)))
    if scale <= 0.0:
        raise F18ZeroResidualError
    target = _rank_ordered(values)
    surrogate = values[rng.permutation(values.size)]
    for _ in range(iterations):
        spectrum = np.fft.rfft(_remap(surrogate, target))
        unit = np.empty_like(spectrum)
        magnitude = np.abs(spectrum)
        np.divide(spectrum, magnitude, out=unit, where=magnitude > 0.0)
        unit[0] = 1.0
        unit[-1] = 1.0
        surrogate = np.fft.irfft(_force_real_endpoints(observed * unit, observed), n=values.size)
    produced = np.abs(np.fft.rfft(surrogate))
    error = float(np.sqrt(np.mean((produced - observed) ** 2)) / scale)
    return np.asarray(surrogate, dtype=np.float64), error


def _force_real_endpoints(
    replacement: Complex128Array, magnitudes: Float64Array
) -> Complex128Array:
    """Перенести DC и Nyquist буквально: у вещественного сигнала они вещественны.

    `irfft` отбрасывает мнимую часть DC и Nyquist, поэтому фаза там не несёт свободы
    и модуль обязан быть observed. Без этого обе крайние частоты теряли бы спектр и
    объявленная tolerance 1e-6 была бы недостижима для обоих null.
    """
    replacement[0] = magnitudes[0]
    replacement[-1] = magnitudes[-1]
    return replacement


def _rank_ordered(values: Float64Array) -> Float64Array:
    """Отсортировать observed значения по модулю: их набор и есть declared target."""
    return values[np.argsort(np.abs(values))]


def _remap(current: Float64Array, target: Float64Array) -> Float64Array:
    """Перенести target на позиции, отсортированные по текущему модулю."""
    ranks = np.empty(current.size, dtype=np.int64)
    ranks[np.argsort(np.abs(current))] = np.arange(current.size)
    return np.asarray(target[ranks], dtype=np.float64)
