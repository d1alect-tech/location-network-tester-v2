"""Полосовые частота событий и доля занятого времени."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from lnt.events.models import EventInventory, QualificationStatus

if TYPE_CHECKING:
    from lnt.features.bands import BandDefinition, BandSet


class EventBandFeatureDict(TypedDict):
    """JSON-safe полосовые event estimands."""

    band: str
    direction: str
    event_count: int
    event_rate_hz: float
    event_rate_unit: str
    duty_cycle: float
    duty_cycle_unit: str
    qualified: bool
    reason_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class EventBandFeature:
    """Частота событий и занятость одной полосы."""

    band: BandDefinition
    event_count: int
    event_rate_hz: float
    duty_cycle: float
    qualified: bool
    reason_code: str | None
    event_rate_unit: str = "events/s"
    duty_cycle_unit: str = "1"

    def to_dict(self) -> EventBandFeatureDict:
        """Сериализует значения, единицы, направление и qualification."""
        return {
            "band": self.band.name,
            "direction": self.band.direction.value,
            "event_count": self.event_count,
            "event_rate_hz": self.event_rate_hz,
            "event_rate_unit": self.event_rate_unit,
            "duty_cycle": self.duty_cycle,
            "duty_cycle_unit": self.duty_cycle_unit,
            "qualified": self.qualified,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EventFeatures:
    """Полный набор event estimands feature schema v1."""

    bands: tuple[EventBandFeature, ...]
    feature_schema_version: int = 1


def compute_event_features(inventory: EventInventory, bands: BandSet) -> EventFeatures:
    """Агрегирует только qualified-кандидаты по имени dominant_band."""
    duration_s = inventory.sample_count / inventory.sample_rate_hz
    metrics: list[EventBandFeature] = []
    for band in bands.bands:
        events = tuple(
            event
            for event in inventory.events
            if event.dominant_band == band.name
            and event.qualification_status is QualificationStatus.QUALIFIED
        )
        occupied_samples = sum(event.end_sample - event.start_sample + 1 for event in events)
        metrics.append(
            EventBandFeature(
                band=band,
                event_count=len(events),
                event_rate_hz=len(events) / duration_s,
                duty_cycle=occupied_samples / inventory.sample_count,
                qualified=not inventory.unqualified_gaps,
                reason_code="unqualified_gaps" if inventory.unqualified_gaps else None,
            )
        )
    return EventFeatures(bands=tuple(metrics))
