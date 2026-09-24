"""F14: оркестрация двустороннего событийного анализа каналов."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f14_direction import (
    build_f14_direction,
    empty_f14_direction,
    unavailable_f14_directions,
)
from lnt.characterization.f14_events import (
    add_inventory_reason,
    qualify_triggers,
    replay_inventory,
    target_event_inventory,
)
from lnt.characterization.f14_math import (
    qualified_cycles,
    relative_axis,
    relative_sample_offsets,
)
from lnt.characterization.f14_result import (
    CHANNEL_MISSING,
    CHANNELS_NOT_SYNCHRONOUS,
    EVENT_LIMIT,
    GAPS_PRESENT,
    INSUFFICIENT_TRIGGERS,
    PHASE_REFERENCE_UNAVAILABLE,
    WINDOW_TRUNCATED,
    F14Declarations,
    F14DirectionResult,
    F14Result,
)
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans


def compute_f14_cross_channel_event_association(  # noqa: C901, PLR0911, PLR0912, PLR0913
    *,
    phase: PhaseCycles | None,
    ch1_samples: np.ndarray | None,
    ch1_phase_means: PhaseMeans | None,
    ch1_events: RootEvents | None,
    ch2_samples: np.ndarray | None,
    ch2_phase_means: PhaseMeans | None,
    ch2_events: RootEvents | None,
    declarations: F14Declarations,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F14Result:
    """Считать F14 по двум явным синхронным каналам и их полным replay-инвентарям."""
    if checkpoint is not None:
        checkpoint()
    if (
        phase is None
        or ch1_samples is None
        or ch1_phase_means is None
        or ch1_events is None
        or ch2_samples is None
        or ch2_phase_means is None
        or ch2_events is None
    ):
        return _unavailable((CHANNEL_MISSING,))
    sample_count = _sample_count(phase, ch1_samples, ch2_samples, ch1_events, ch2_events)
    if sample_count is None:
        return _unavailable((CHANNELS_NOT_SYNCHRONOUS,))
    if phase.status is Status.UNAVAILABLE or _no_valid_cycles(phase):
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,))
    reasons: set[str] = set()
    if phase.status is Status.PARTIAL or phase.reason_code in PHASE_ROOT_REASON_CODES:
        reasons.add(GAPS_PRESENT)
    if ch1_phase_means.status is Status.UNAVAILABLE or ch2_phase_means.status is Status.UNAVAILABLE:
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,))
    if ch1_phase_means.status is Status.PARTIAL or ch2_phase_means.status is Status.PARTIAL:
        reasons.add(GAPS_PRESENT)
    if (
        ch1_phase_means.means_v.size != declarations.phase_bins
        or ch2_phase_means.means_v.size != declarations.phase_bins
    ):
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,))
    first_inventory = replay_inventory(ch1_events, checkpoint)
    second_inventory = replay_inventory(ch2_events, checkpoint)
    add_inventory_reason(reasons, first_inventory)
    add_inventory_reason(reasons, second_inventory)
    cycle_starts, cycle_ends = qualified_cycles(phase)
    axis = relative_axis(
        declarations.trigger_window_low_s,
        declarations.trigger_window_high_s,
        declarations.relative_time_bins,
    )
    offsets = relative_sample_offsets(axis, phase.sample_rate_hz)
    directions: list[F14DirectionResult] = []
    direction_inputs = (
        (
            "ch1",
            "ch2",
            first_inventory,
            second_inventory,
            ch2_samples,
            ch2_phase_means,
        ),
        (
            "ch2",
            "ch1",
            second_inventory,
            first_inventory,
            ch1_samples,
            ch1_phase_means,
        ),
    )
    for (
        trigger_channel,
        response_channel,
        trigger_inventory,
        response_inventory,
        response_samples,
        response_means,
    ) in direction_inputs:
        qualified, counts = qualify_triggers(
            trigger_inventory,
            response_inventory,
            response_samples,
            phase,
            response_means,
            declarations,
            offsets,
            resources=resources,
            checkpoint=checkpoint,
        )
        if counts.boundary_count or counts.window_truncated_count:
            reasons.add(WINDOW_TRUNCATED)
        if counts.gap_crossing_count:
            reasons.add(GAPS_PRESENT)
        stored = qualified[: declarations.maximum_triggers_per_direction]
        if len(stored) < declarations.minimum_triggers:
            reasons.add(INSUFFICIENT_TRIGGERS)
        if len(stored) < len(qualified) or trigger_inventory.root_event_limit:
            reasons.add(EVENT_LIMIT)
        target = target_event_inventory(response_inventory, cycle_starts, cycle_ends)
        directions.append(
            build_f14_direction(
                trigger_channel=trigger_channel,
                response_channel=response_channel,
                triggers=stored,
                counts=counts,
                target=target,
                cycle_starts=cycle_starts,
                cycle_ends=cycle_ends,
                offsets=offsets,
                axis=axis,
                declarations=declarations,
                sample_rate_hz=phase.sample_rate_hz,
                checkpoint=checkpoint,
            )
        )
    if INSUFFICIENT_TRIGGERS in reasons:
        return _unavailable_with_directions(tuple(sorted(reasons)), directions, sample_count)
    if PHASE_REFERENCE_UNAVAILABLE in reasons:
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,))
    return F14Result(
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=tuple(sorted(reasons)),
        relative_time_s=axis,
        directions=(directions[0], directions[1]),
        sample_count=sample_count,
        qualified_cycle_count=int(cycle_starts.size),
    )


def _unavailable(codes: tuple[str, ...], *, sample_count: int = 0) -> F14Result:
    """Собрать отказ с пустыми доменами и двумя честными направлениями."""
    directions = tuple(
        empty_f14_direction(trigger, response)
        for trigger, response in (("ch1", "ch2"), ("ch2", "ch1"))
    )
    return F14Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        relative_time_s=np.empty(0, dtype=np.float64),
        directions=(directions[0], directions[1]),
        sample_count=sample_count,
        qualified_cycle_count=0,
    )


def _sample_count(
    phase: PhaseCycles,
    first: np.ndarray,
    second: np.ndarray,
    first_events: RootEvents,
    second_events: RootEvents,
) -> int | None:
    """Проверить общий sample grid и скорость двух каналов."""
    first_array = np.asarray(first)
    second_array = np.asarray(second)
    if first_array.ndim != 1 or second_array.ndim != 1:
        return None
    count = int(first_array.size)
    if (
        int(second_array.size) != count
        or phase.sample_count != count
        or first_events.sample_count != count
        or second_events.sample_count != count
        or not math.isfinite(phase.sample_rate_hz)
        or phase.sample_rate_hz <= 0.0
        or not math.isclose(phase.sample_rate_hz, first_events.sample_rate_hz, abs_tol=1e-12)
        or not math.isclose(phase.sample_rate_hz, second_events.sample_rate_hz, abs_tol=1e-12)
    ):
        return None
    return count


def _no_valid_cycles(phase: PhaseCycles) -> bool:
    """Проверить наличие хотя бы одного полного квалифицированного цикла."""
    starts, _ends = qualified_cycles(phase)
    return starts.size == 0


def _unavailable_with_directions(
    codes: tuple[str, ...], directions: list[F14DirectionResult], sample_count: int
) -> F14Result:
    """Сохранить честные счётчики, но запретить измерения при отказе."""
    cleared = unavailable_f14_directions((directions[0], directions[1]))
    return F14Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        relative_time_s=np.empty(0, dtype=np.float64),
        directions=cleared,
        sample_count=sample_count,
        qualified_cycle_count=0,
    )
