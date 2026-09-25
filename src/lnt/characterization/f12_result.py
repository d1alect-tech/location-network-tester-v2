"""F12: полный locked surface и опубликованный результат."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f12_contract import (
    ANALYSIS_HIGH_HZ,
    ANALYSIS_LOW_HZ,
    DETREND,
    FALSE_DISCOVERY_RATE,
    MAXIMUM_STORED_BINS,
    MINIMUM_FRAMES,
    MULTIPLE_TESTING,
    NYQUIST_FRACTION_MAX,
    OVERLAP_FRACTION,
    PHASE_BINS,
    SEARCH_ADJUSTMENT,
    SEGMENT_SAMPLES,
    SURROGATE,
    SURROGATE_COUNT,
    SURROGATE_SEED,
    WINDOW,
)

if TYPE_CHECKING:
    from lnt.characterization.records import Status

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True, kw_only=True)
class F12Declarations:
    """Полный locked surface F12 без скрытых численных настроек."""

    phase_bins: int
    segment_samples: tuple[int, ...]
    window: str
    overlap_fraction: float
    detrend: str
    analysis_low_hz: float
    analysis_high_hz: float
    nyquist_fraction_max: float
    minimum_frames: int
    surrogate: str
    surrogate_count: int
    surrogate_seed: int
    search_adjustment: str
    multiple_testing: str
    false_discovery_rate: float
    maximum_stored_bins: int

    def __post_init__(self) -> None:
        """Отвергнуть дрейф любого поля characterization-v2."""
        locked = (
            self.phase_bins == PHASE_BINS
            and self.segment_samples == SEGMENT_SAMPLES
            and self.window == WINDOW
            and self.overlap_fraction == OVERLAP_FRACTION
            and self.detrend == DETREND
            and self.analysis_low_hz == ANALYSIS_LOW_HZ
            and self.analysis_high_hz == ANALYSIS_HIGH_HZ
            and self.nyquist_fraction_max == NYQUIST_FRACTION_MAX
            and self.minimum_frames == MINIMUM_FRAMES
            and self.surrogate == SURROGATE
            and self.surrogate_count == SURROGATE_COUNT
            and self.surrogate_seed == SURROGATE_SEED
            and self.search_adjustment == SEARCH_ADJUSTMENT
            and self.multiple_testing == MULTIPLE_TESTING
            and self.false_discovery_rate == FALSE_DISCOVERY_RATE
            and self.maximum_stored_bins == MAXIMUM_STORED_BINS
        )
        if not locked:
            raise ValueError("F12 declarations do not match the locked recipe")

    @classmethod
    def locked(cls) -> F12Declarations:
        """Вернуть точные значения characterization-v2."""
        return cls(
            phase_bins=PHASE_BINS,
            segment_samples=SEGMENT_SAMPLES,
            window=WINDOW,
            overlap_fraction=OVERLAP_FRACTION,
            detrend=DETREND,
            analysis_low_hz=ANALYSIS_LOW_HZ,
            analysis_high_hz=ANALYSIS_HIGH_HZ,
            nyquist_fraction_max=NYQUIST_FRACTION_MAX,
            minimum_frames=MINIMUM_FRAMES,
            surrogate=SURROGATE,
            surrogate_count=SURROGATE_COUNT,
            surrogate_seed=SURROGATE_SEED,
            search_adjustment=SEARCH_ADJUSTMENT,
            multiple_testing=MULTIPLE_TESTING,
            false_discovery_rate=FALSE_DISCOVERY_RATE,
            maximum_stored_bins=MAXIMUM_STORED_BINS,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class F12Result:
    """Опубликованные F12 scale supports и bounded significant-bin domain."""

    status: Status
    reason_codes: tuple[str, ...]
    segment_samples: Int64Array
    frame_count: Int64Array
    scale_available: BoolArray
    frequencies_hz: Float64Array
    scale_index: Int64Array
    spectral_kurtosis: Float64Array
    adjusted_p_value: Float64Array
    maximum_spectral_kurtosis: float | None
    selected_scale_index: int | None
    selected_band_low_hz: float | None
    selected_band_high_hz: float | None
    sample_count: int
    qualified_sample_count: int
    analyzed_scale_count: int
    candidate_count: int
    significant_bin_count: int
    stored_significant_bin_count: int
    surrogate_count: int

    def __post_init__(self) -> None:
        """Проверить locked vocabulary, scale geometry и availability accounting."""
        from lnt.characterization.f12_validation import validate_f12_result  # noqa: PLC0415

        validate_f12_result(self)
