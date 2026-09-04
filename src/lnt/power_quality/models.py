"""Типизированные события качества напряжения и JSON-безопасные формы payload."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from lnt.power_quality.settings import PowerQualitySettings, PowerQualitySettingsDict


class EventKind(StrEnum):
    """Род зарегистрированного отклонения среднеквадратичного напряжения."""

    SAG = "sag"
    SWELL = "swell"
    DROPOUT = "dropout"


class Tolerance(StrEnum):
    """Вердикт события относительно огибающей ITIC 2000/SEMI-F47."""

    IN_TOLERANCE = "in_tolerance"
    OUT_OF_TOLERANCE = "out_of_tolerance"
    UNAVAILABLE = "unavailable"


class IticRegion(StrEnum):
    """Область кривой ITIC, в которую попало событие по глубине и длительности."""

    DROPOUT = "dropout"
    SAG = "sag"
    SWELL = "swell"
    STEADY = "steady"


class RvcDirection(StrEnum):
    """Направление ступени быстрого изменения напряжения."""

    UP = "up"
    DOWN = "down"


class VoltageEventDict(TypedDict):
    """JSON-safe payload события отклонения напряжения."""

    start_time_s: float
    end_time_s: float
    duration_s: float
    kind: str
    depth_pct: float
    nominal_rms_v: float
    verdict: str
    itic_region: str


class RvcEventDict(TypedDict):
    """JSON-safe payload ступени быстрого изменения напряжения."""

    step_time_s: float
    delta_pct: float
    direction: str
    sustained_cycles: int


class HalfCycleSummaryDict(TypedDict):
    """JSON-safe сводка ряда полупериодных RMS."""

    count: int
    nominal_rms_v: float
    min: float
    max: float


class PowerQualityInventoryDict(TypedDict):
    """JSON-safe полный инвентарь качества питания."""

    schema_version: int
    settings_hash: str
    settings: PowerQualitySettingsDict
    half_cycle_rms_summary: HalfCycleSummaryDict
    events: list[VoltageEventDict]
    rvc_events: list[RvcEventDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class VoltageEvent:
    """Отклонение напряжения: это наблюдение, а не причинный вывод."""

    start_time_s: float
    end_time_s: float
    duration_s: float
    kind: EventKind
    depth_pct: float
    nominal_rms_v: float
    verdict: Tolerance
    itic_region: IticRegion

    def to_dict(self) -> VoltageEventDict:
        """Сериализует событие в JSON-безопасные примитивы."""
        return {
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "duration_s": self.duration_s,
            "kind": self.kind.value,
            "depth_pct": self.depth_pct,
            "nominal_rms_v": self.nominal_rms_v,
            "verdict": self.verdict.value,
            "itic_region": self.itic_region.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RvcEvent:
    """Ступень быстрого изменения напряжения между соседними полупериодами."""

    step_time_s: float
    delta_pct: float
    direction: RvcDirection
    sustained_cycles: int

    def to_dict(self) -> RvcEventDict:
        """Сериализует ступень в JSON-безопасные примитивы."""
        return {
            "step_time_s": self.step_time_s,
            "delta_pct": self.delta_pct,
            "direction": self.direction.value,
            "sustained_cycles": self.sustained_cycles,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PowerQualityInventory:
    """Детерминированный инвентарь событий качества питания записи."""

    schema_version: int
    settings_hash: str
    settings: PowerQualitySettings
    half_cycle_rms_summary: HalfCycleSummaryDict
    events: tuple[VoltageEvent, ...]
    rvc_events: tuple[RvcEvent, ...]

    def to_dict(self) -> PowerQualityInventoryDict:
        """Сериализует воспроизводимый инвентарь целиком."""
        return {
            "schema_version": self.schema_version,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "half_cycle_rms_summary": self.half_cycle_rms_summary,
            "events": [event.to_dict() for event in self.events],
            "rvc_events": [step.to_dict() for step in self.rvc_events],
        }
