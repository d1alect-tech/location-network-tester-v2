"""F12: family-wide Benjamini-Hochberg и connected significant band."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]


def benjamini_hochberg(raw_p_values: Float64Array) -> Float64Array:
    """Скорректировать один declared family-wide candidate list ровно один раз.

    Stable ascending sort сохраняет original-index order при ties; step-up
    adjustment применяется от наибольшего raw p-value к наименьшему.
    """
    values = np.asarray(raw_p_values, dtype=np.float64)
    if (
        values.ndim != 1
        or values.size == 0
        or not np.all(np.isfinite(values))
        or np.any(values <= 0.0)
        or np.any(values > 1.0)
    ):
        raise ValueError("F12 BH needs one finite nonempty p-value vector")
    order = np.argsort(values, kind="stable")
    ranks = np.arange(1, values.size + 1, dtype=np.float64)
    adjusted_sorted = np.minimum(1.0, values[order] * values.size / ranks)
    adjusted_sorted = np.minimum.accumulate(adjusted_sorted[::-1])[::-1]
    result = np.empty(values.size, dtype=np.float64)
    result[order] = adjusted_sorted
    return result


def connected_significant_band(
    frequencies_hz: Float64Array,
    adjusted_p_values: Float64Array,
    false_discovery_rate: float,
    maximum_index: int,
) -> tuple[float, float] | None:
    """Вернуть contiguous significant run, содержащий declared global maximum."""
    frequencies = np.asarray(frequencies_hz, dtype=np.float64)
    adjusted = np.asarray(adjusted_p_values, dtype=np.float64)
    if (
        frequencies.shape != adjusted.shape
        or frequencies.ndim != 1
        or frequencies.size == 0
        or not np.all(np.isfinite(frequencies))
        or not np.all(np.isfinite(adjusted))
        or np.any(np.diff(frequencies) <= 0.0)
        or np.any((adjusted <= 0.0) | (adjusted > 1.0))
        or not 0.0 < false_discovery_rate <= 1.0
        or not 0 <= maximum_index < frequencies.size
    ):
        raise ValueError("F12 significant band inputs are inconsistent")
    if adjusted[maximum_index] > false_discovery_rate:
        return None
    low = maximum_index
    high = maximum_index
    while low > 0 and adjusted[low - 1] <= false_discovery_rate:
        low -= 1
    while high + 1 < adjusted.size and adjusted[high + 1] <= false_discovery_rate:
        high += 1
    return float(frequencies[low]), float(frequencies[high])


def bounded_significant_order(
    significant_indices: Int64Array,
    selected_band_indices: Int64Array,
    maximum_count: int,
    *,
    maximum_index: int | None = None,
) -> Int64Array:
    """Сохранить maximum и selected band первыми по CAP_STORAGE_CONVENTION."""
    significant = np.sort(np.asarray(significant_indices, dtype=np.int64))
    selected = np.sort(np.asarray(selected_band_indices, dtype=np.int64))
    if (
        significant.ndim != 1
        or selected.ndim != 1
        or significant.size == 0
        or maximum_count <= 0
        or np.unique(significant).size != significant.size
        or np.any(selected < 0)
        or not np.all(np.isin(selected, significant))
        or (maximum_index is not None and int(maximum_index) not in selected.tolist())
    ):
        raise ValueError("F12 stored-bin cap inputs are inconsistent")
    if maximum_index is None:
        priority = selected
    else:
        priority = np.asarray([int(maximum_index)], dtype=np.int64)
        priority = np.concatenate((priority, selected[selected != int(maximum_index)]))
    remaining = np.setdiff1d(significant, priority, assume_unique=True)
    return np.concatenate((priority, remaining))[:maximum_count]
