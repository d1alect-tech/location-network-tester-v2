"""F14: replay корневых событий и квалификация полных trigger-окон."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.event_models import TaggedEvent, TaggedGap
from lnt.characterization.f14_math import (
    EventInterval,
    TargetEvent,
    sample_waveform,
    target_events,
    window_bounds,
)
from lnt.characterization.phase import phase_bins

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvent, RootEvents
    from lnt.characterization.f14_math import Float64Array, Int64Array
    from lnt.characterization.f14_result import F14Declarations
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans


@dataclass(frozen=True, slots=True, kw_only=True)
class F14Inventory:
    """Полный replay одного канала и его интервалы недопустимого support."""

    events: tuple[RootEvent, ...]
    gaps: tuple[EventInterval, ...]
    total_event_count: int
    root_event_limit: bool
    root_gap_limit: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class QualifiedTrigger:
    """Триггер с уже извлечённой фазовой формой канала ответа."""

    event: RootEvent
    waveform_v: Float64Array


@dataclass(frozen=True, slots=True, kw_only=True)
class TriggerCounts:
    """Счётчики отказов до применения капа и минимума."""

    total_event_count: int
    boundary_count: int
    gap_crossing_count: int
    window_truncated_count: int
    qualified_count: int


def replay_inventory(inventory: RootEvents, checkpoint: Callable[[], None] | None) -> F14Inventory:
    """Прочитать полный replay, не используя усечённый сохранённый префикс."""
    events: list[RootEvent] = []
    gaps: list[EventInterval] = []
    for item in inventory.replay(checkpoint):
        if isinstance(item, TaggedEvent):
            events.append(item.event)
        elif isinstance(item, TaggedGap):
            gaps.append((int(item.gap.start_sample), int(item.gap.end_sample)))
        else:
            gaps.append((int(item.exclusion.start_sample), int(item.exclusion.end_sample)))
    replayed_count = len(events)
    return F14Inventory(
        events=tuple(events),
        gaps=tuple(gaps),
        total_event_count=max(replayed_count, int(inventory.accepted_count)),
        root_event_limit=(
            int(inventory.accepted_count) > replayed_count or int(inventory.omitted_count) > 0
        ),
        root_gap_limit=(
            int(inventory.omitted_gap_count) > 0 or int(inventory.omitted_exclusion_count) > 0
        ),
    )


def qualify_triggers(  # noqa: PLR0913, PLR0917
    trigger_inventory: F14Inventory,
    response_inventory: F14Inventory,
    response_samples: np.ndarray,
    phase: PhaseCycles,
    response_means: PhaseMeans,
    declarations: F14Declarations,
    offsets: Int64Array,
    *,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None,
) -> tuple[tuple[QualifiedTrigger, ...], TriggerCounts]:
    """Оставить только события с полным окном без границы и gap."""
    qualified: list[QualifiedTrigger] = []
    boundary = gaps = truncated = 0
    for event in sorted(
        trigger_inventory.events, key=lambda item: (int(item.peak_sample), int(item.ordinal))
    ):
        if checkpoint is not None:
            checkpoint()
        if event.boundary:
            boundary += 1
            continue
        start, stop = window_bounds(int(event.peak_sample), offsets)
        if start < 0 or stop > int(response_samples.size):
            truncated += 1
            continue
        if _crosses(start, stop, trigger_inventory.gaps) or _crosses(
            start, stop, response_inventory.gaps
        ):
            gaps += 1
            continue
        _, valid = phase_bins(phase, start, stop, declarations.phase_bins)
        if not bool(np.all(valid)):
            gaps += 1
            continue
        waveform = sample_waveform(
            response_samples,
            phase,
            response_means,
            int(event.peak_sample),
            offsets,
            resources=resources,
        )
        if waveform is None:
            gaps += 1
            continue
        qualified.append(QualifiedTrigger(event=event, waveform_v=waveform))
    return tuple(qualified), TriggerCounts(
        total_event_count=trigger_inventory.total_event_count,
        boundary_count=boundary,
        gap_crossing_count=gaps,
        window_truncated_count=truncated,
        qualified_count=len(qualified),
    )


def target_event_inventory(
    inventory: F14Inventory, starts: np.ndarray, ends: np.ndarray
) -> tuple[TargetEvent, ...]:
    """Получить полный target replay, привязанный к квалифицированным циклам."""
    return tuple(target_events(inventory.events, starts, ends))


def add_inventory_reason(reasons: set[str], inventory: F14Inventory) -> None:
    """Сохранить только объявленный F14 код для корневого support."""
    if inventory.root_event_limit:
        reasons.add("event_limit")
    if inventory.gaps or inventory.root_gap_limit:
        reasons.add("gaps_present")


def _crosses(start: int, stop: int, intervals: tuple[EventInterval, ...]) -> bool:
    """Проверить пересечение полуоткрытого окна сinclusive gap-интервалом."""
    return any(low < stop and start <= high for low, high in intervals)
