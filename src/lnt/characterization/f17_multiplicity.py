"""F17: one BH correction across every tested alpha-frequency cell."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from lnt.statistics.spectra import benjamini_hochberg

type Float64Array = NDArray[np.float64]
type BoolArray = NDArray[np.bool_]


def benjamini_hochberg_masked(p_values: Float64Array, available: BoolArray) -> Float64Array:
    """Скорректировать только реально протестированные ячейки, сохранив маску."""
    values = np.asarray(p_values, dtype=np.float64)
    mask = np.asarray(available, dtype=np.bool_)
    if values.shape != mask.shape:
        raise ValueError("F17 p-value and availability domains must match")
    result = np.full(values.shape, np.nan, dtype=np.float64)
    selected = mask & np.isfinite(values)
    if not bool(np.any(selected)):
        return result
    if bool(np.any((values[selected] < 0.0) | (values[selected] > 1.0))):
        raise ValueError("F17 p-values must stay in [0, 1]")
    adjusted = benjamini_hochberg(tuple(float(value) for value in values[selected]))
    result[selected] = np.asarray(adjusted, dtype=np.float64)
    return result


def significant_cells(
    adjusted_p_values: Float64Array,
    available: BoolArray,
    false_discovery_rate: float,
) -> BoolArray:
    """Отметить только BH-значимые ячейки без повторного threshold search."""
    values = np.asarray(adjusted_p_values, dtype=np.float64)
    mask = np.asarray(available, dtype=np.bool_)
    if values.shape != mask.shape:
        raise ValueError("F17 adjusted p-value and availability domains must match")
    return mask & np.isfinite(values) & (values <= float(false_discovery_rate))
