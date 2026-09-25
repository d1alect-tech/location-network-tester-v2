"""F17: exact symmetric FFT-bin mapping and declared analysis axis."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from lnt.characterization.f17_contract import F17Declarations

type Int64Array = NDArray[np.int64]
type Float64Array = NDArray[np.float64]
type BoolArray = NDArray[np.bool_]

_GRID_EPSILON = 1e-12


@dataclass(frozen=True, slots=True, kw_only=True)
class FrequencyGrid:
    """Center frequencies and exact sideband bins for every declared alpha."""

    frequencies_hz: Float64Array
    center_bins: Int64Array
    alpha_offsets: Int64Array
    lower_bins: Int64Array
    upper_bins: Int64Array
    available: BoolArray
    alpha_on_grid: BoolArray


def build_frequency_grid(declarations: F17Declarations, sample_rate_hz: float) -> FrequencyGrid:
    """Построить fixed center axis; off-grid alpha остаётся unavailable без округления."""
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("F17 sample rate must be finite and positive")
    segment = int(declarations.segment_samples)
    bin_count = segment // 2 + 1
    resolution = sample_rate_hz / float(segment)
    effective_high = min(
        float(declarations.analysis_high_hz),
        float(declarations.nyquist_fraction_max) * sample_rate_hz,
    )
    first = max(1, math.ceil(float(declarations.analysis_low_hz) / resolution - _GRID_EPSILON))
    last = min(bin_count - 1, math.floor(effective_high / resolution + _GRID_EPSILON))
    center_bins = np.arange(first, last + 1, dtype=np.int64)
    frequencies = center_bins.astype(np.float64) * resolution
    shape = (len(declarations.cyclic_frequencies_hz), center_bins.size)
    offsets = np.full(len(declarations.cyclic_frequencies_hz), -1, dtype=np.int64)
    on_grid = np.zeros(offsets.size, dtype=np.bool_)
    lower = np.full(shape, -1, dtype=np.int64)
    upper = np.full(shape, -1, dtype=np.int64)
    available = np.zeros(shape, dtype=np.bool_)
    for alpha_index, alpha_hz in enumerate(declarations.cyclic_frequencies_hz):
        scaled = float(alpha_hz) / (2.0 * resolution)
        nearest = round(scaled)
        if nearest <= 0 or not math.isclose(scaled, nearest, rel_tol=0.0, abs_tol=_GRID_EPSILON):
            continue
        offsets[alpha_index] = nearest
        on_grid[alpha_index] = True
        candidate_lower = center_bins - nearest
        candidate_upper = center_bins + nearest
        valid = (candidate_lower >= 0) & (candidate_upper < bin_count)
        lower[alpha_index, valid] = candidate_lower[valid]
        upper[alpha_index, valid] = candidate_upper[valid]
        available[alpha_index, valid] = True
    return FrequencyGrid(
        frequencies_hz=frequencies,
        center_bins=center_bins,
        alpha_offsets=offsets,
        lower_bins=lower,
        upper_bins=upper,
        available=available,
        alpha_on_grid=on_grid,
    )
