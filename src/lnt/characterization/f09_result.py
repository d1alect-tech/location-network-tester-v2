"""F09 typed_transition_and_waiting_time_inventory: замороженный результат и коды."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.records import Inference, Status

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

METHOD: Final = "typed_transition_and_waiting_time_inventory"

INSUFFICIENT_EVENTS: Final = "insufficient_events"
DEAD_TIME_OVERLAP: Final = "dead_time_overlap"
SINGLE_CYCLE_RECORD: Final = "single_cycle_record"
GAPS_PRESENT: Final = "gaps_present"

DECLARED_CODES: Final = (
    INSUFFICIENT_EVENTS,
    DEAD_TIME_OVERLAP,
    SINGLE_CYCLE_RECORD,
    GAPS_PRESENT,
)

INDEPENDENT_REPEATS_THESIS: Final = (
    "циклы внутри одной записи не являются независимыми повторами: "
    "p-value и доверительные интервалы из одних циклов не публикуются, "
    "независимые оценки требуют целых независимых захватов"
)

BOUNDARY_HANDLING: Final = "boundary_flag_only_not_dropped"
EVENT_TYPE_SEPARATOR: Final = "|"

__all__ = [
    "BOUNDARY_HANDLING",
    "DEAD_TIME_OVERLAP",
    "DECLARED_CODES",
    "EVENT_TYPE_SEPARATOR",
    "GAPS_PRESENT",
    "INDEPENDENT_REPEATS_THESIS",
    "INSUFFICIENT_EVENTS",
    "METHOD",
    "SINGLE_CYCLE_RECORD",
    "F09Result",
    "Transition",
    "_Accounting",
    "_Sequence",
    "_assembled",
    "_unavailable",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Accounting:
    """Честный учёт поддержки: счёт принятых событий, отказы и пропуски инвентаря."""

    sample_count: int
    observation_count: int
    omitted_event_count: int
    candidate_count: int
    dead_time_rejected_count: int
    dead_time_omitted_count: int
    gap_count: int
    omitted_gap_count: int
    boundary_event_count: int
    unclassified_band_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _Sequence:
    """Итог одного прохода по отсортированным событиям."""

    labels: tuple[str, ...]
    transitions: tuple[Transition, ...]
    dt_s: Float64Array
    polarity_run_lengths: Int64Array
    cluster_sizes: Int64Array
    cluster_start_s: Float64Array
    cluster_spread_s: Float64Array
    excluded_count: int


def _assembled(  # noqa: PLR0913 - сборка результата: ряды, учёт и гейты читаются явно
    sequence: _Sequence,
    counts: _Accounting,
    *,
    event_type_fields: tuple[str, ...],
    reason_codes: tuple[str, ...],
    dead_time_s: float,
    start_s: float,
    end_s: float,
) -> F09Result:
    """Собрать доступный результат из готовых рядов прохода и честного учёта."""
    return F09Result(
        status=Status.PARTIAL if reason_codes else Status.AVAILABLE,
        reason_codes=reason_codes,
        event_type_fields=event_type_fields,
        event_labels=sequence.labels,
        transitions=sequence.transitions,
        dt_s=sequence.dt_s,
        polarity_run_lengths=sequence.polarity_run_lengths,
        cluster_start_s=sequence.cluster_start_s,
        cluster_spread_s=sequence.cluster_spread_s,
        cluster_sizes=sequence.cluster_sizes,
        cluster_count=int(sequence.cluster_sizes.size),
        excluded_waiting_interval_count=sequence.excluded_count,
        omitted_event_count=counts.omitted_event_count,
        boundary_event_count=counts.boundary_event_count,
        unclassified_band_count=counts.unclassified_band_count,
        dead_time_s=dead_time_s,
        dead_time_rejected_count=counts.dead_time_rejected_count,
        dead_time_omitted_count=counts.dead_time_omitted_count,
        gap_count=counts.gap_count,
        omitted_gap_count=counts.omitted_gap_count,
        candidate_count=counts.candidate_count,
        boundary_handling=BOUNDARY_HANDLING,
        inference=Inference(),
        sample_count=counts.sample_count,
        observation_count=counts.observation_count,
        missing_count=counts.sample_count - counts.observation_count,
        stored_count=counts.observation_count,
        start_s=start_s,
        end_s=end_s,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Transition:
    """Один ненулевой переход между метками соседних событий."""

    source: str
    target: str
    count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class F09Result:
    """Ограниченный результат F09: переходы, ожидания, кластеры и счётчики учёта."""

    status: Status
    reason_codes: tuple[str, ...]
    event_type_fields: tuple[str, ...]
    event_labels: tuple[str, ...]
    transitions: tuple[Transition, ...]
    dt_s: Float64Array
    polarity_run_lengths: Int64Array
    cluster_start_s: Float64Array
    cluster_spread_s: Float64Array
    cluster_sizes: Int64Array
    cluster_count: int
    excluded_waiting_interval_count: int
    omitted_event_count: int
    boundary_event_count: int
    unclassified_band_count: int
    dead_time_s: float
    dead_time_rejected_count: int
    dead_time_omitted_count: int
    gap_count: int
    omitted_gap_count: int
    candidate_count: int
    boundary_handling: str
    inference: Inference
    sample_count: int
    observation_count: int
    missing_count: int
    stored_count: int
    start_s: float | None
    end_s: float | None


def _unavailable(
    codes: tuple[str, ...],
    *,
    event_type_fields: tuple[str, ...],
    dead_time_s: float,
    counts: _Accounting,
    observation_count: int,
) -> F09Result:
    """Отказ без выдуманных значений: пустые ряды, None вместо интервалов."""
    total = counts.sample_count
    return F09Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        event_type_fields=event_type_fields,
        event_labels=(),
        transitions=(),
        dt_s=np.empty(0, dtype=np.float64),
        polarity_run_lengths=np.empty(0, dtype=np.int64),
        cluster_start_s=np.empty(0, dtype=np.float64),
        cluster_spread_s=np.empty(0, dtype=np.float64),
        cluster_sizes=np.empty(0, dtype=np.int64),
        cluster_count=0,
        excluded_waiting_interval_count=0,
        omitted_event_count=counts.omitted_event_count,
        boundary_event_count=counts.boundary_event_count,
        unclassified_band_count=counts.unclassified_band_count,
        dead_time_s=dead_time_s,
        dead_time_rejected_count=counts.dead_time_rejected_count,
        dead_time_omitted_count=counts.dead_time_omitted_count,
        gap_count=counts.gap_count,
        omitted_gap_count=counts.omitted_gap_count,
        candidate_count=counts.candidate_count,
        boundary_handling=BOUNDARY_HANDLING,
        inference=Inference(),
        sample_count=total,
        observation_count=observation_count,
        missing_count=total - observation_count,
        stored_count=observation_count,
        start_s=None,
        end_s=None,
    )
