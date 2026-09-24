"""F14: опубликованные объявления, коды и запись результата."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f14_contract import (
    BASELINE_PROBABILITY_NAME,
    CHANNEL_MISSING,
    CHANNELS_NOT_SYNCHRONOUS,
    CLAIM_BOUNDARY,
    DECLARED_CODES,
    EVENT_LIMIT,
    EVENT_PROBABILITY_NAME,
    F14_ID,
    F14_INDEX,
    GAPS_PRESENT,
    INSUFFICIENT_TRIGGERS,
    LAG_SIGN_CONVENTION,
    MEAN_WAVEFORM_NAME,
    METHOD,
    NEAREST_LAG_NAME,
    PHASE_REFERENCE_UNAVAILABLE,
    WINDOW_TRUNCATED,
)

__all__ = [
    "BASELINE_PROBABILITY_NAME",
    "CHANNELS_NOT_SYNCHRONOUS",
    "CHANNEL_MISSING",
    "CLAIM_BOUNDARY",
    "DECLARED_CODES",
    "EVENT_LIMIT",
    "EVENT_PROBABILITY_NAME",
    "F14_ID",
    "F14_INDEX",
    "GAPS_PRESENT",
    "INSUFFICIENT_TRIGGERS",
    "LAG_SIGN_CONVENTION",
    "MEAN_WAVEFORM_NAME",
    "METHOD",
    "NEAREST_LAG_NAME",
    "PHASE_REFERENCE_UNAVAILABLE",
    "WINDOW_TRUNCATED",
    "F14Declarations",
    "F14DirectionResult",
    "F14Result",
]

if TYPE_CHECKING:
    from lnt.characterization.records import Status

_LOCKED_TIE_BREAK: Final = "earlier_target"
_LOCKED_BOUNDARY_HANDLING: Final = "exclude_incomplete_windows"
_LOCKED_PHASE_BINS: Final = 64
_LOCKED_RELATIVE_BINS: Final = 401
_LOCKED_MINIMUM_TRIGGERS: Final = 20
_LOCKED_MAXIMUM_TRIGGERS: Final = 4096
_LOCKED_CYCLE_SHIFTS: Final = tuple(range(1, 33))

type Float64Array = NDArray[np.float64]


@dataclass(frozen=True, slots=True, kw_only=True)
class F14Declarations:
    """Полный tunable surface рецепта F14 без скрытых настроек."""

    trigger_window_low_s: float
    trigger_window_high_s: float
    relative_time_bins: int
    nearest_event_lag_low_s: float
    nearest_event_lag_high_s: float
    nearest_event_tie_break: str
    phase_bins: int
    cycle_shift_offsets: tuple[int, ...]
    minimum_triggers: int
    maximum_triggers_per_direction: int
    boundary_handling: str

    def __post_init__(self) -> None:
        """Проверить locked vocabulary и числовые домены окна, лага и триггеров."""
        if (
            self.nearest_event_tie_break != _LOCKED_TIE_BREAK
            or self.boundary_handling != _LOCKED_BOUNDARY_HANDLING
        ):
            raise ValueError("F14 declarations do not match the locked vocabulary")
        if (
            self.relative_time_bins <= 0
            or self.relative_time_bins % 2 == 0
            or self.phase_bins <= 0
            or self.minimum_triggers <= 0
            or self.maximum_triggers_per_direction < self.minimum_triggers
        ):
            raise ValueError("F14 integer declarations must be positive and bins odd")
        if (
            not math.isfinite(self.trigger_window_low_s)
            or not math.isfinite(self.trigger_window_high_s)
            or not math.isfinite(self.nearest_event_lag_low_s)
            or not math.isfinite(self.nearest_event_lag_high_s)
            or not self.trigger_window_low_s < 0.0 < self.trigger_window_high_s
            or not self.nearest_event_lag_low_s < 0.0 < self.nearest_event_lag_high_s
        ):
            raise ValueError("F14 time declarations must straddle zero")
        if (
            not self.cycle_shift_offsets
            or any(offset <= 0 for offset in self.cycle_shift_offsets)
            or any(
                left >= right
                for left, right in zip(
                    self.cycle_shift_offsets, self.cycle_shift_offsets[1:], strict=False
                )
            )
        ):
            raise ValueError("F14 cycle shift offsets must be positive and increasing")

    @classmethod
    def locked(cls) -> F14Declarations:
        """Вернуть ровно замороженные значения characterization-v1."""
        return cls(
            trigger_window_low_s=-0.02,
            trigger_window_high_s=0.02,
            relative_time_bins=_LOCKED_RELATIVE_BINS,
            nearest_event_lag_low_s=-0.02,
            nearest_event_lag_high_s=0.02,
            nearest_event_tie_break=_LOCKED_TIE_BREAK,
            phase_bins=_LOCKED_PHASE_BINS,
            cycle_shift_offsets=_LOCKED_CYCLE_SHIFTS,
            minimum_triggers=_LOCKED_MINIMUM_TRIGGERS,
            maximum_triggers_per_direction=_LOCKED_MAXIMUM_TRIGGERS,
            boundary_handling=_LOCKED_BOUNDARY_HANDLING,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class F14DirectionResult:
    """Один направленный срез: триггерный канал и канал ответа."""

    trigger_channel: str
    response_channel: str
    total_event_count: int
    qualified_trigger_count: int
    stored_trigger_count: int
    omitted_trigger_count: int
    boundary_trigger_count: int
    gap_crossing_trigger_count: int
    window_truncated_count: int
    mean_waveform_v: Float64Array
    event_probability: Float64Array
    nearest_lag_s: Float64Array
    baseline_probability: Float64Array
    baseline_low: Float64Array
    baseline_high: Float64Array


@dataclass(frozen=True, slots=True, kw_only=True)
class F14Result:
    """Два направления F14, общая относительная сетка и статус доступности."""

    status: Status
    reason_codes: tuple[str, ...]
    relative_time_s: Float64Array
    directions: tuple[F14DirectionResult, F14DirectionResult]
    sample_count: int
    qualified_cycle_count: int

    def __post_init__(self) -> None:
        """Проверить коды, направления, счётчики и пустые домены отказа."""
        from lnt.characterization.f14_validation import validate_f14_result  # noqa: PLC0415

        validate_f14_result(self)
