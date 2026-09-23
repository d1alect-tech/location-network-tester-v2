"""F09 typed_transition_and_waiting_time_inventory поверх общего инвентаря событий."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization import f09_result as codes
from lnt.characterization.f09_result import (
    EVENT_TYPE_SEPARATOR,
    F09Result,
    Transition,
    _Accounting,
    _assembled,
    _Sequence,
    _unavailable,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvent, RootEvents
    from lnt.events.models import UnqualifiedGap

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

METHOD: Final = codes.METHOD
_LOCKED_TYPE_FIELDS: Final = ("polarity", "dominant_band")
_LOCKED_DEAD_TIME_HANDLING: Final = "exclude_intervals"
_LOCKED_GAP_HANDLING: Final = "exclude_waiting_intervals"

__all__ = ["METHOD", "F09Result", "compute_f09_event_ordering"]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Gates:
    """Разобранные и проверенные объявленные гейты рецепта."""

    fields: tuple[str, ...]
    cluster_gap_s: float
    minimum_event_count: int
    maximum_events: int


def compute_f09_event_ordering(  # noqa: PLR0913 - объявленные гейты рецепта
    inventory: RootEvents,
    *,
    event_type_fields: Sequence[str],
    cluster_gap_s: float,
    minimum_event_count: int,
    dead_time_handling: str,
    gap_handling: str,
    maximum_events: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F09Result:
    """Типовая последовательность, переходы, ожидания и кластеры одной записи.

    Вход это готовый инвентарь ``RootEvents`` (спека:443): детектор не вызывается
    повторно, пиковые времена берутся как есть и сортируются. Метка типа строится
    из залоченных ``event_type_fields`` через ``|`` (F09-3). ``dt`` публикуется
    сырым (F09-6), объявленный ``cluster_gap_s`` только режет поток на кластеры
    (F09-7), серии считаются по полярности (F09-8). Пропуски, мёртвое время и
    границы публикуются явно (F09-9, F09-10), а ``inference`` объявляет тезис
    спеки:456-459: циклы одной записи не независимые повторы.
    """
    if checkpoint is not None:
        checkpoint()
    gates = _gates(
        event_type_fields,
        cluster_gap_s,
        minimum_event_count,
        maximum_events,
        dead_time_handling,
        gap_handling,
    )
    # Объявленный бюджет не расходуется: работа O(E log E) сортировка плюс O(E)
    # накопление (спека `method-notes-families-1-9.md:464`), ограничивать нечего.
    _ = resources
    ordered = _ordered(inventory)
    kept = ordered[: gates.maximum_events]
    counts = _accounting(ordered, len(kept), inventory)
    dead_time_s = float(inventory.settings.dead_time_s)
    if counts.sample_count < gates.minimum_event_count or not kept:
        # Предусловие спеки:456-457: на горстке событий инвентарь порядка не строится.
        return _unavailable(
            _codes(counts, codes.INSUFFICIENT_EVENTS),
            event_type_fields=gates.fields,
            dead_time_s=dead_time_s,
            counts=counts,
            observation_count=0,
        )
    sequence = _accumulate(kept, inventory.gaps, gates.cluster_gap_s)
    extra = _codes(
        counts,
        codes.SINGLE_CYCLE_RECORD if sequence.cluster_sizes.size == 1 else None,
        codes.GAPS_PRESENT if sequence.excluded_count else None,
    )
    return _assembled(
        sequence,
        counts,
        event_type_fields=gates.fields,
        reason_codes=extra,
        dead_time_s=dead_time_s,
        start_s=float(kept[0].peak_time_s),
        end_s=float(kept[-1].peak_time_s),
    )


def _accumulate(
    kept: list[RootEvent],
    gaps: tuple[UnqualifiedGap, ...],
    gap_s: float,
) -> _Sequence:
    """Единственный проход по событиям: ``O(E)`` накопление (спека:464).

    Переходы ``n_ij`` считаются по соседним меткам, интервал публикуется сырым,
    если он не пересекает сохранённый ``unqualified_gap`` и не перепрыгивает
    границу сегмента таймлайна (спека:449-451). Сохранены только префиксы
    ``gaps``, поэтому вытесненный пропуск остаётся виден через границу сегмента,
    которая рвёт интервал точнее любого времени. Кластер рвётся на исключённом
    интервале или на интервале строго больше объявленного порога (F09-7).
    """
    labels = [_label(kept[0])]
    seen: dict[tuple[str, str], int] = {}
    dt: list[float] = []
    runs: list[int] = []
    sizes: list[int] = []
    starts: list[float] = []
    spreads: list[float] = []
    run = 1
    size = 1
    first = last = float(kept[0].peak_time_s)
    excluded = 0
    for previous, current in pairwise(kept):
        label = _label(current)
        pair = (labels[-1], label)
        seen[pair] = seen.get(pair, 0) + 1
        labels.append(label)
        if previous.polarity == current.polarity:
            run += 1
        else:
            runs.append(run)
            run = 1
        start = float(previous.peak_time_s)
        stop = float(current.peak_time_s)
        crossing = int(previous.timeline_segment) != int(current.timeline_segment) or any(
            start < float(gap.end_time_s) and float(gap.start_time_s) < stop for gap in gaps
        )
        if crossing:
            excluded += 1
        if crossing or stop - last > gap_s:
            sizes.append(size)
            starts.append(first)
            spreads.append(last - first)
            size = 0
            first = stop
        size += 1
        last = stop
        if not crossing:
            dt.append(stop - start)
    runs.append(run)
    sizes.append(size)
    starts.append(first)
    spreads.append(last - first)
    return _Sequence(
        labels=tuple(labels),
        transitions=tuple(
            Transition(source=source, target=target, count=count)
            for (source, target), count in seen.items()
        ),
        dt_s=np.asarray(dt, dtype=np.float64),
        polarity_run_lengths=np.asarray(runs, dtype=np.int64),
        cluster_sizes=np.asarray(sizes, dtype=np.int64),
        cluster_start_s=np.asarray(starts, dtype=np.float64),
        cluster_spread_s=np.asarray(spreads, dtype=np.float64),
        excluded_count=excluded,
    )


def _gates(  # noqa: PLR0913, PLR0917 - гейты читаются поимённо, без скрытого контекста
    event_type_fields: Sequence[str],
    cluster_gap_s: float,
    minimum_event_count: int,
    maximum_events: int,
    dead_time_handling: str,
    gap_handling: str,
) -> _Gates:
    """Проверить числа и залоченные правила: незалоченное движком не поддерживается."""
    gap_s = float(cluster_gap_s)
    if not math.isfinite(gap_s) or gap_s <= 0.0:
        raise ValueError("cluster_gap_s must be positive and finite")
    minimum = int(minimum_event_count)
    if minimum <= 0:
        raise ValueError("minimum_event_count must be positive")
    limit = int(maximum_events)
    if limit <= 0:
        raise ValueError("maximum_events must be positive")
    fields = tuple(event_type_fields)
    if fields != _LOCKED_TYPE_FIELDS:
        raise ValueError("event_type_fields must be the declared polarity and dominant_band")
    if dead_time_handling != _LOCKED_DEAD_TIME_HANDLING:
        raise ValueError("dead_time_handling must be exclude_intervals")
    if gap_handling != _LOCKED_GAP_HANDLING:
        raise ValueError("gap_handling must be exclude_waiting_intervals")
    return _Gates(
        fields=fields,
        cluster_gap_s=gap_s,
        minimum_event_count=minimum,
        maximum_events=limit,
    )


def _accounting(ordered: list[RootEvent], kept: int, inventory: RootEvents) -> _Accounting:
    """Полный счёт принятых событий записи плюс счётчики отказов и пропусков корня."""
    accepted = int(inventory.accepted_count)
    return _Accounting(
        sample_count=accepted,
        observation_count=kept,
        omitted_event_count=accepted - kept,
        candidate_count=int(inventory.candidate_count),
        dead_time_rejected_count=int(inventory.dead_time_rejected_count),
        dead_time_omitted_count=int(inventory.omitted_exclusion_count),
        gap_count=int(inventory.gap_count),
        omitted_gap_count=int(inventory.omitted_gap_count),
        boundary_event_count=sum(1 for event in ordered if bool(event.boundary)),
        unclassified_band_count=sum(1 for event in ordered if event.dominant_band is None),
    )


def _ordered(inventory: RootEvents) -> list[RootEvent]:
    """События по пиковому времени с тай-брейком по номеру (спека:443-444)."""
    rate = float(inventory.sample_rate_hz)
    dead_time_s = float(inventory.settings.dead_time_s)
    if not math.isfinite(rate) or rate <= 0.0:
        raise ValueError("sample rate must be positive and finite")
    if not math.isfinite(dead_time_s) or dead_time_s <= 0.0:
        raise ValueError("dead_time_s must be positive and finite")
    accepted = int(inventory.accepted_count)
    if accepted < len(inventory.events) or accepted < 0 or int(inventory.sample_count) <= 0:
        raise ValueError("root event inventory is inconsistent")
    events = list(inventory.events)
    if any(not math.isfinite(float(event.peak_time_s)) for event in events):
        raise ValueError("event peak times must be finite")
    events.sort(key=lambda event: (float(event.peak_time_s), int(event.ordinal)))
    return events


def _label(event: RootEvent) -> str:
    """Метка типа: объявленные поля через ``|``; нет полосы — объявленная причина."""
    band = event.dominant_band
    if band is None:
        band = event.dominant_band_reason_code
    return EVENT_TYPE_SEPARATOR.join((str(event.polarity.value), band or "unavailable"))


def _codes(counts: _Accounting, *extra: str | None) -> tuple[str, ...]:
    """Объявленный порядок кодов: счётчики корня плюс явные флаги этого прогона."""
    raw: set[str] = {code for code in extra if code is not None}
    if counts.dead_time_rejected_count > 0 or counts.dead_time_omitted_count > 0:
        raw.add(codes.DEAD_TIME_OVERLAP)
    if counts.gap_count > 0 or counts.omitted_gap_count > 0:
        raw.add(codes.GAPS_PRESENT)
    return tuple(code for code in codes.DECLARED_CODES if code in raw)
