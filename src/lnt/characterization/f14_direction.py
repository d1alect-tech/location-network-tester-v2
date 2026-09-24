"""F14: сборка направления из квалифицированных триггеров и target replay."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f14_math import event_coverage, nearest_lag, shifted_intervals
from lnt.characterization.f14_result import F14Declarations, F14DirectionResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.characterization.f14_events import QualifiedTrigger, TriggerCounts
    from lnt.characterization.f14_math import TargetEvent


def build_f14_direction(  # noqa: PLR0913 - все поля результата направления
    *,
    trigger_channel: str,
    response_channel: str,
    triggers: tuple[QualifiedTrigger, ...],
    counts: TriggerCounts,
    target: tuple[TargetEvent, ...],
    cycle_starts: np.ndarray,
    cycle_ends: np.ndarray,
    offsets: np.ndarray,
    axis: np.ndarray,
    declarations: F14Declarations,
    sample_rate_hz: float,
    checkpoint: Callable[[], None] | None,
) -> F14DirectionResult:
    """Усреднить waveform, occupancy, nearest lag и cycle-shift baseline."""
    bins = int(axis.size)
    if not triggers:
        return empty_f14_direction(trigger_channel, response_channel, counts)
    intervals = tuple((int(item.start_sample), int(item.end_sample)) for item in target)
    waveform = np.zeros(bins, dtype=np.float64)
    probability = np.zeros(bins, dtype=np.float64)
    lags: list[float] = []
    baseline = np.zeros((len(declarations.cycle_shift_offsets), bins), dtype=np.float64)
    shifted_rows = tuple(
        shifted_intervals(target, cycle_starts, cycle_ends, offset)
        for offset in declarations.cycle_shift_offsets
    )
    for trigger in triggers:
        if checkpoint is not None:
            checkpoint()
        waveform += trigger.waveform_v
        probability += event_coverage(trigger.event.peak_sample, offsets, intervals)
        lag = nearest_lag(
            trigger.event.peak_sample,
            target,
            declarations.nearest_event_lag_low_s,
            declarations.nearest_event_lag_high_s,
            sample_rate_hz,
        )
        if lag is not None:
            lags.append(lag)
        for row, shifted in enumerate(shifted_rows):
            baseline[row] += event_coverage(trigger.event.peak_sample, offsets, shifted)
    count = float(len(triggers))
    waveform /= count
    probability /= count
    baseline /= count
    return F14DirectionResult(
        trigger_channel=trigger_channel,
        response_channel=response_channel,
        total_event_count=counts.total_event_count,
        qualified_trigger_count=counts.qualified_count,
        stored_trigger_count=len(triggers),
        omitted_trigger_count=counts.qualified_count - len(triggers),
        boundary_trigger_count=counts.boundary_count,
        gap_crossing_trigger_count=counts.gap_crossing_count,
        window_truncated_count=counts.window_truncated_count,
        mean_waveform_v=waveform,
        event_probability=probability,
        nearest_lag_s=np.asarray(lags, dtype=np.float64),
        baseline_probability=baseline,
        baseline_low=np.min(baseline, axis=0),
        baseline_high=np.max(baseline, axis=0),
    )


def empty_f14_direction(
    trigger_channel: str,
    response_channel: str,
    counts: TriggerCounts | None = None,
) -> F14DirectionResult:
    """Создать направление с пустыми измерениями и честным исходным учётом."""
    empty = np.empty(0, dtype=np.float64)
    return F14DirectionResult(
        trigger_channel=trigger_channel,
        response_channel=response_channel,
        total_event_count=0 if counts is None else counts.total_event_count,
        qualified_trigger_count=0 if counts is None else counts.qualified_count,
        stored_trigger_count=0,
        omitted_trigger_count=0 if counts is None else counts.qualified_count,
        boundary_trigger_count=0 if counts is None else counts.boundary_count,
        gap_crossing_trigger_count=0 if counts is None else counts.gap_crossing_count,
        window_truncated_count=0 if counts is None else counts.window_truncated_count,
        mean_waveform_v=empty,
        event_probability=empty,
        nearest_lag_s=empty,
        baseline_probability=np.empty((0, 0), dtype=np.float64),
        baseline_low=empty,
        baseline_high=empty,
    )


def unavailable_f14_directions(
    directions: tuple[F14DirectionResult, F14DirectionResult],
) -> tuple[F14DirectionResult, F14DirectionResult]:
    """Удалить измерения, сохранив учёт отказа.

    Правило бандла для UNAVAILABLE: `stored_trigger_count == 0` при
    `omitted_trigger_count == qualified_trigger_count`, все массивы пустые. Так
    информативный учёт остаётся («квалифицировали N триггеров, не сохранили ни
    одного»), а измерительных выходов нет — `FamilyResult` запрещает их при отказе.
    Прежняя версия сохраняла `stored_trigger_count`, из-за чего легитимный отказ
    движка не персистировался: маппер отвергал результат вместо публикации статуса.
    """
    cleared = tuple(
        F14DirectionResult(
            trigger_channel=direction.trigger_channel,
            response_channel=direction.response_channel,
            total_event_count=direction.total_event_count,
            qualified_trigger_count=direction.qualified_trigger_count,
            stored_trigger_count=0,
            omitted_trigger_count=direction.qualified_trigger_count,
            boundary_trigger_count=direction.boundary_trigger_count,
            gap_crossing_trigger_count=direction.gap_crossing_trigger_count,
            window_truncated_count=direction.window_truncated_count,
            mean_waveform_v=np.empty(0, dtype=np.float64),
            event_probability=np.empty(0, dtype=np.float64),
            nearest_lag_s=np.empty(0, dtype=np.float64),
            baseline_probability=np.empty((0, 0), dtype=np.float64),
            baseline_low=np.empty(0, dtype=np.float64),
            baseline_high=np.empty(0, dtype=np.float64),
        )
        for direction in directions
    )
    return (cleared[0], cleared[1])
