"""Результат F03: замороженный датакласс, константы и отказ без фабрикации."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.records import Status

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

METHOD: Final = "synchronous_bin_nearest_neighbor_tracks"

_BELOW_RESOLUTION: Final = "below_resolution"
_PEAK_NOT_OBSERVED: Final = "peak_not_observed"
_TRACK_TOO_SHORT: Final = "track_too_short"
_LEAKAGE_AMBIGUOUS: Final = "leakage_ambiguous"
_GRID_UNSTABLE: Final = "grid_unstable"

__all__ = [
    "METHOD",
    "_BELOW_RESOLUTION",
    "_GRID_UNSTABLE",
    "_LEAKAGE_AMBIGUOUS",
    "_PEAK_NOT_OBSERVED",
    "_TRACK_TOO_SHORT",
    "F03Result",
    "_unavailable",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class F03Result:
    """Ограниченный результат F03 по трекам интергармоник и субгармоник."""

    status: Status
    reason_codes: tuple[str, ...]
    f_hz: Float64Array
    a_v: Float64Array
    df_hz: Float64Array
    t_life_s: Float64Array
    windows_observed: Int64Array
    windows_missing: Int64Array
    evaluated_window_count: int
    candidate_track_count: int
    omitted_track_count: int
    sample_count: int
    observation_count: int
    missing_count: int
    stored_count: int


def _unavailable(
    codes: tuple[str, ...], total_windows: int, candidates: int, omitted: int
) -> F03Result:
    """Отказ без выдуманных значений: массивы пусты, счётчики честны."""
    return F03Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        f_hz=np.empty(0, dtype=np.float64),
        a_v=np.empty(0, dtype=np.float64),
        df_hz=np.empty(0, dtype=np.float64),
        t_life_s=np.empty(0, dtype=np.float64),
        windows_observed=np.empty(0, dtype=np.int64),
        windows_missing=np.empty(0, dtype=np.int64),
        evaluated_window_count=int(total_windows),
        candidate_track_count=int(candidates),
        omitted_track_count=int(omitted),
        sample_count=int(candidates),
        observation_count=0,
        missing_count=int(candidates),
        stored_count=0,
    )
