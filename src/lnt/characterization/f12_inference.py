"""F12: raw p-values, one family-wide BH и bounded significant selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f12_multiple_testing import (
    benjamini_hochberg,
    bounded_significant_order,
    connected_significant_band,
)

if TYPE_CHECKING:
    from lnt.characterization.f12_candidates import CandidateTable

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class InferenceSelection:
    """Все family-wide p-values и indices, разрешённые declared artifact cap."""

    adjusted_p_value: Float64Array
    significant_indices: Int64Array
    stored_indices: Int64Array
    maximum_index: int
    selected_scale_index: int | None
    selected_band_low_hz: float | None
    selected_band_high_hz: float | None
    significant_count: int


def infer_f12_candidates(
    candidates: CandidateTable,
    surrogate_maxima: Float64Array,
    *,
    false_discovery_rate: float,
    maximum_stored_bins: int,
) -> InferenceSelection:
    """Применить add-one global-max p и BH ровно один раз к CandidateTable."""
    values: Float64Array = np.asarray(candidates.spectral_kurtosis, dtype=np.float64)
    nulls: Float64Array = np.sort(np.asarray(surrogate_maxima, dtype=np.float64))
    if values.size == 0 or nulls.size == 0 or not np.all(np.isfinite(nulls)):
        raise ValueError("F12 inference needs finite observed candidates and surrogate maxima")
    exceedances: Int64Array = np.asarray(
        nulls.size - np.searchsorted(nulls, values, side="left"), dtype=np.int64
    )
    raw_p: Float64Array = np.asarray((1.0 + exceedances) / (nulls.size + 1.0), dtype=np.float64)
    adjusted: Float64Array = benjamini_hochberg(raw_p)
    maximum_index = int(np.argmax(values))
    significant = np.flatnonzero(adjusted <= false_discovery_rate).astype(np.int64)
    if significant.size == 0:
        return InferenceSelection(
            adjusted_p_value=np.empty(0, dtype=np.float64),
            significant_indices=significant,
            stored_indices=np.empty(0, dtype=np.int64),
            maximum_index=maximum_index,
            selected_scale_index=None,
            selected_band_low_hz=None,
            selected_band_high_hz=None,
            significant_count=0,
        )
    scale = int(candidates.scale_index[maximum_index])
    scale_positions = np.flatnonzero(candidates.scale_index == scale)
    local_maximum = int(np.flatnonzero(scale_positions == maximum_index)[0])
    band = connected_significant_band(
        candidates.frequencies_hz[scale_positions],
        adjusted[scale_positions],
        false_discovery_rate,
        local_maximum,
    )
    if band is None:
        raise ValueError("F12 global maximum lost its significant run")
    local_band = scale_positions[
        (candidates.frequencies_hz[scale_positions] >= band[0])
        & (candidates.frequencies_hz[scale_positions] <= band[1])
    ]
    stored = bounded_significant_order(
        significant,
        local_band,
        maximum_stored_bins,
        maximum_index=maximum_index,
    )
    return InferenceSelection(
        adjusted_p_value=adjusted[stored],
        significant_indices=significant,
        stored_indices=stored,
        maximum_index=maximum_index,
        selected_scale_index=scale,
        selected_band_low_hz=band[0],
        selected_band_high_hz=band[1],
        significant_count=int(significant.size),
    )
