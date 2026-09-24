"""F16: locked declarations and published multiscale-memory record."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f16_contract import (
    AUTOCOVARIANCE,
    COUNT_WINDOW_OVERLAP_FRACTION,
    COUNT_WINDOWS_S,
    FANO_VARIANCE_DDOF,
    LAGS_S,
    MAXIMUM_FFT_SEGMENT_SAMPLES,
    MINIMUM_COUNT_WINDOWS,
    MINIMUM_PAIRS,
    PARTIAL_COUNT_WINDOW_HANDLING,
    PHASE_BINS,
    RECURRENCE_RADIUS_MAD,
)

if TYPE_CHECKING:
    from lnt.characterization.records import Status

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True, kw_only=True)
class F16Declarations:
    """Полный locked surface F16 без скрытых численных настроек."""

    phase_bins: int
    autocovariance: str
    lags_s: tuple[float, ...]
    recurrence_radius_mad: tuple[float, ...]
    count_windows_s: tuple[float, ...]
    count_window_overlap_fraction: float
    partial_count_window_handling: str
    fano_variance_ddof: int
    minimum_pairs: int
    minimum_count_windows: int
    maximum_fft_segment_samples: int

    def __post_init__(self) -> None:
        """Отвергнуть дрейф любого поля characterization-v1."""
        locked = (
            self.phase_bins == PHASE_BINS
            and self.autocovariance == AUTOCOVARIANCE
            and self.lags_s == LAGS_S
            and self.recurrence_radius_mad == RECURRENCE_RADIUS_MAD
            and self.count_windows_s == COUNT_WINDOWS_S
            and self.count_window_overlap_fraction == COUNT_WINDOW_OVERLAP_FRACTION
            and self.partial_count_window_handling == PARTIAL_COUNT_WINDOW_HANDLING
            and self.fano_variance_ddof == FANO_VARIANCE_DDOF
            and self.minimum_pairs == MINIMUM_PAIRS
            and self.minimum_count_windows == MINIMUM_COUNT_WINDOWS
            and self.maximum_fft_segment_samples == MAXIMUM_FFT_SEGMENT_SAMPLES
        )
        if not locked:
            raise ValueError("F16 declarations do not match the locked recipe")

    @classmethod
    def locked(cls) -> F16Declarations:
        """Вернуть точные значения characterization-v1."""
        return cls(
            phase_bins=PHASE_BINS,
            autocovariance=AUTOCOVARIANCE,
            lags_s=LAGS_S,
            recurrence_radius_mad=RECURRENCE_RADIUS_MAD,
            count_windows_s=COUNT_WINDOWS_S,
            count_window_overlap_fraction=COUNT_WINDOW_OVERLAP_FRACTION,
            partial_count_window_handling=PARTIAL_COUNT_WINDOW_HANDLING,
            fano_variance_ddof=FANO_VARIANCE_DDOF,
            minimum_pairs=MINIMUM_PAIRS,
            minimum_count_windows=MINIMUM_COUNT_WINDOWS,
            maximum_fft_segment_samples=MAXIMUM_FFT_SEGMENT_SAMPLES,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class F16Result:
    """Fixed axes F16, измеренные values, явная availability и support."""

    status: Status
    reason_codes: tuple[str, ...]
    lag_s: Float64Array
    autocorrelation: Float64Array
    pair_count: Int64Array
    lag_available: BoolArray
    recurrence_radius_mad: Float64Array
    recurrence_rate: Float64Array
    count_window_s: Float64Array
    count_window_count: Int64Array
    count_mean: Float64Array
    count_variance: Float64Array
    fano_factor: Float64Array
    count_window_available: BoolArray
    fano_available: BoolArray
    sample_count: int
    qualified_sample_count: int
    analyzed_segment_count: int
    event_count: int

    def __post_init__(self) -> None:
        """Проверить коды, оси, маски и пустые домены отказа."""
        from lnt.characterization.f16_validation import validate_f16_result  # noqa: PLC0415

        validate_f16_result(self)
