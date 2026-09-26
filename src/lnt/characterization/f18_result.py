"""F18: locked declarations и published bicoherence record."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f18_contract import (
    ANALYSIS_HIGH_HZ,
    BASE_FREQUENCIES_HZ,
    DUAL_NULL_P_VALUE,
    FALSE_DISCOVERY_RATE,
    FREQUENCY_MAPPING,
    IAAFT_ITERATIONS,
    IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE,
    IAAFT_SURROGATE_COUNT,
    MAXIMUM_TRIADS,
    MINIMUM_FRAMES,
    MULTIPLE_TESTING,
    NYQUIST_FRACTION_MAX,
    OVERLAP_FRACTION,
    PHASE_BINS,
    PHASE_RANDOMIZED_SURROGATE_COUNT,
    SEGMENT_DURATION_S,
    SURROGATE_SEED,
    TRIAD_RULE,
    WINDOW,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.characterization.records import Status

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]

# Полный locked surface выписан литералом ДО класса: сравнение с ним не зависит от
# `locked()` и поэтому работает уже на первом вызове `__post_init__`.
_LOCKED: Final[tuple[object, ...]] = (
    PHASE_BINS,
    SEGMENT_DURATION_S,
    WINDOW,
    OVERLAP_FRACTION,
    BASE_FREQUENCIES_HZ,
    TRIAD_RULE,
    ANALYSIS_HIGH_HZ,
    NYQUIST_FRACTION_MAX,
    FREQUENCY_MAPPING,
    MAXIMUM_TRIADS,
    PHASE_RANDOMIZED_SURROGATE_COUNT,
    IAAFT_SURROGATE_COUNT,
    IAAFT_ITERATIONS,
    IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE,
    SURROGATE_SEED,
    DUAL_NULL_P_VALUE,
    MULTIPLE_TESTING,
    FALSE_DISCOVERY_RATE,
    MINIMUM_FRAMES,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class F18Declarations:
    """Полный locked surface F18 без скрытых численных настроек."""

    phase_bins: int
    segment_duration_s: float
    window: str
    overlap_fraction: float
    base_frequencies_hz: tuple[float, ...]
    triad_rule: str
    analysis_high_hz: float
    nyquist_fraction_max: float
    frequency_mapping: str
    maximum_triads: int
    phase_randomized_surrogate_count: int
    iaaft_surrogate_count: int
    iaaft_iterations: int
    iaaft_relative_rms_magnitude_tolerance: float
    surrogate_seed: int
    dual_null_p_value: str
    multiple_testing: str
    false_discovery_rate: float
    minimum_frames: int

    def __post_init__(self) -> None:
        """Отвергнуть дрейф любого поля characterization-v1."""
        if self.locked_values() != _LOCKED:
            raise ValueError("F18 declarations do not match the locked recipe")

    @classmethod
    def locked(cls) -> F18Declarations:
        """Вернуть точные значения characterization-v1."""
        return cls(
            phase_bins=PHASE_BINS,
            segment_duration_s=SEGMENT_DURATION_S,
            window=WINDOW,
            overlap_fraction=OVERLAP_FRACTION,
            base_frequencies_hz=BASE_FREQUENCIES_HZ,
            triad_rule=TRIAD_RULE,
            analysis_high_hz=ANALYSIS_HIGH_HZ,
            nyquist_fraction_max=NYQUIST_FRACTION_MAX,
            frequency_mapping=FREQUENCY_MAPPING,
            maximum_triads=MAXIMUM_TRIADS,
            phase_randomized_surrogate_count=PHASE_RANDOMIZED_SURROGATE_COUNT,
            iaaft_surrogate_count=IAAFT_SURROGATE_COUNT,
            iaaft_iterations=IAAFT_ITERATIONS,
            iaaft_relative_rms_magnitude_tolerance=IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE,
            surrogate_seed=SURROGATE_SEED,
            dual_null_p_value=DUAL_NULL_P_VALUE,
            multiple_testing=MULTIPLE_TESTING,
            false_discovery_rate=FALSE_DISCOVERY_RATE,
            minimum_frames=MINIMUM_FRAMES,
        )

    def locked_values(self) -> tuple[object, ...]:
        """Снимок всего declared surface для побайтового сравнения с locked."""
        return (
            self.phase_bins,
            self.segment_duration_s,
            self.window,
            self.overlap_fraction,
            self.base_frequencies_hz,
            self.triad_rule,
            self.analysis_high_hz,
            self.nyquist_fraction_max,
            self.frequency_mapping,
            self.maximum_triads,
            self.phase_randomized_surrogate_count,
            self.iaaft_surrogate_count,
            self.iaaft_iterations,
            self.iaaft_relative_rms_magnitude_tolerance,
            self.surrogate_seed,
            self.dual_null_p_value,
            self.multiple_testing,
            self.false_discovery_rate,
            self.minimum_frames,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class F18Result:
    """Fixed triad domain F18, измеренные values, явная availability и support."""

    status: Status
    reason_codes: tuple[str, ...]
    triad_low_hz: Float64Array
    triad_high_hz: Float64Array
    triad_sum_hz: Float64Array
    bicoherence_squared: Float64Array
    biphase_rad: Float64Array
    phase_randomized_p_value: Float64Array
    iaaft_p_value: Float64Array
    dual_null_p_value: Float64Array
    adjusted_p_value: Float64Array
    triad_available: BoolArray
    significant: BoolArray
    frame_support: Int64Array
    sample_count: int
    qualified_sample_count: int
    # Выведено движком из объявленной длительности и ИЗМЕРЕННОЙ частоты: recipe
    # объявляет длительность, поэтому число отсчётов не может быть locked-константой.
    segment_samples: int
    frame_count: int
    declared_triad_count: int
    measurable_triad_count: int
    off_grid_triad_count: int
    above_nyquist_triad_count: int
    dropped_triad_count: int
    iaaft_converged_count: int

    def __post_init__(self) -> None:
        """Проверить коды, triad domain, маски и пустые домены отказа."""
        from lnt.characterization.f18_validation import validate_f18_result  # noqa: PLC0415

        validate_f18_result(self)
