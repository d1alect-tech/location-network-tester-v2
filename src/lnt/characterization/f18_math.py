"""F18: normalized bicoherence, biphase и их declared domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

type Float64Array = NDArray[np.float64]
type Complex128Array = NDArray[np.complex128]
type Int64Array = NDArray[np.int64]

_BICOHERENCE_LOW: float = 0.0
_BICOHERENCE_HIGH: float = 1.0
_TRIAD_COLUMNS: int = 3
_MATRIX_COLUMNS: int = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class F18Bicoherence:
    """Квадрат нормированного bicoherence, биспектр и его знаменатель."""

    bicoherence_squared: Float64Array
    bispectrum: Complex128Array
    denominator: Float64Array


def triad_bicoherence(coefficients: Complex128Array, rows: Int64Array) -> F18Bicoherence:
    """Посчитать B и b2 для всех измеряемых триад одним проходом по кадрам.

    `coefficients` имеет форму (D, frames) — коэффициенты rfft по distinct-строкам,
    `rows` — (K, 3) индексов строк f1, f2 и f1+f2. Кадровые фазовые множители
    2*pi*f*n0/fs сокращаются в B при f1+f2 = f3 на exact bin, поэтому связанная
    триада копит |B| линейно по числу кадров, а независимые фазы дают E[b2] = 1/M.
    """
    data = np.asarray(coefficients, dtype=np.complex128)
    index = np.asarray(rows, dtype=np.int64)
    if (
        data.ndim != _MATRIX_COLUMNS
        or index.ndim != _MATRIX_COLUMNS
        or index.shape[1] != _TRIAD_COLUMNS
        or index.shape[0] == 0
    ):
        raise ValueError("F18 bicoherence needs a (D, frames) matrix and a (K, 3) row index")
    if data.shape[1] == 0:
        raise ValueError("F18 bicoherence needs at least one qualified frame")
    if int(index.min()) < 0 or int(index.max()) >= data.shape[0]:
        raise ValueError("F18 bicoherence row index left the gathered coefficient matrix")
    first = data[index[:, 0]]
    second = data[index[:, 1]]
    third = data[index[:, 2]]
    bispectrum = np.sum(first * second * np.conjugate(third), axis=1)
    pair_energy = np.sum(np.abs(first * second) ** 2, axis=1)
    third_energy = np.sum(np.abs(third) ** 2, axis=1)
    denominator = pair_energy * third_energy
    squared = _normalized(np.abs(bispectrum) ** 2, denominator)
    return F18Bicoherence(
        bicoherence_squared=squared,
        bispectrum=np.asarray(bispectrum, dtype=np.complex128),
        denominator=np.asarray(denominator, dtype=np.float64),
    )


def _normalized(numerator: Float64Array, denominator: Float64Array) -> Float64Array:
    """Разделить и зажать в [0, 1]; нулевой знаменатель остаётся явным NaN."""
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = numerator / denominator
    clipped = np.clip(ratio, _BICOHERENCE_LOW, _BICOHERENCE_HIGH)
    return np.asarray(
        np.where(denominator > 0.0, clipped, np.nan),
        dtype=np.float64,
    )
