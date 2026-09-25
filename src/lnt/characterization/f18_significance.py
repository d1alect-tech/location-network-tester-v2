"""F18: add-one p-values, dual-null combination и один BH-проход."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]

_P_VALUE_HIGH: float = 1.0


def add_one_p_value(exceedance: Int64Array, surrogate_count: int) -> Float64Array:
    """(1 + превышений) / (число суррогатов + 1) — declared add-one p-value."""
    counts = np.asarray(exceedance, dtype=np.int64)
    if surrogate_count <= 0 or bool(np.any(counts > surrogate_count)) or bool(np.any(counts < 0)):
        raise ValueError("F18 exceedance left its declared surrogate domain")
    return np.asarray((1.0 + counts.astype(np.float64)) / (surrogate_count + 1), dtype=np.float64)


def dual_null_p_value(phase_randomized: Float64Array, iaaft: Float64Array) -> Float64Array:
    """Взять maximum_add_one_p_value: худший из двух declared null."""
    first = np.asarray(phase_randomized, dtype=np.float64)
    second = np.asarray(iaaft, dtype=np.float64)
    if first.shape != second.shape:
        raise ValueError("F18 dual null needs two p-values on the same triad domain")
    return np.asarray(np.maximum(first, second), dtype=np.float64)


def benjamini_hochberg(
    p_values: Float64Array, false_discovery_rate: float
) -> tuple[Float64Array, BoolArray]:
    """Один step-up проход BH: adjusted p и флаг из p_(i) <= i*q/m.

    Флаг берётся из step-up правила, а не из сравнения adjusted <= q: при m=15,
    q=0.05 и p=0.01 adjusted на i=3 равен 0.05000000000000001 > q из-за
    округления float64, тогда как сам BH-порог 0.01 ровно выполнен. Оба решения
    совпадают везде, кроме этой границы, где step-up устойчив.
    """
    values = np.asarray(p_values, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not 0.0 < false_discovery_rate <= 1.0:
        raise ValueError("F18 BH needs a nonempty p-value axis and 0 < q <= 1")
    if (
        not np.all(np.isfinite(values))
        or bool(np.any(values < 0.0))
        or bool(np.any(values > _P_VALUE_HIGH))
    ):
        raise ValueError("F18 BH p-values left [0, 1]")
    count = values.size
    order = np.argsort(values, kind="stable")
    ranks = np.arange(1, count + 1, dtype=np.float64)
    ordered = values[order]
    thresholds = ranks * false_discovery_rate / count
    passing = np.flatnonzero(ordered <= thresholds)
    cutoff = int(passing[-1]) if passing.size else -1
    scaled = ordered * count / ranks
    adjusted_ordered = np.minimum.accumulate(scaled[::-1])[::-1]
    adjusted_ordered = np.minimum(adjusted_ordered, _P_VALUE_HIGH)
    adjusted = np.empty(count, dtype=np.float64)
    adjusted[order] = adjusted_ordered
    significant = np.zeros(count, dtype=np.bool_)
    if cutoff >= 0:
        significant[order[: cutoff + 1]] = True
    return adjusted, significant
