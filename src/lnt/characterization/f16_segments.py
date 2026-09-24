"""F16: qualified spans, full gap replay и bounded residual segments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.event_models import TaggedGap
from lnt.characterization.phase_stats import phase_residual_impl

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
type Span = tuple[int, int]

_RESIDUAL_BYTES_PER_SAMPLE = 64


@dataclass(frozen=True, slots=True, kw_only=True)
class QualifiedSupport:
    """Continuous phase-qualified spans без root-event gaps."""

    spans: tuple[Span, ...]
    phase_gap: bool


def replay_gaps(
    inventory: RootEvents,
    sample_count: int,
    checkpoint: Callable[[], None] | None,
) -> tuple[Span, ...]:
    """Прочитать full replay и сохранить только реальные unqualified gaps."""
    raw = [
        (int(item.gap.start_sample), int(item.gap.end_sample))
        for item in inventory.replay(checkpoint)
        if isinstance(item, TaggedGap)
    ]
    if len(raw) != int(inventory.gap_count):
        raise ValueError("F16 full replay gap count differs from the event inventory")
    return _normalize_gaps(raw, sample_count)


def qualified_spans(  # noqa: PLR0913, PLR0917 - все явные входы shared phase root
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    gaps: tuple[Span, ...],
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None,
) -> QualifiedSupport:
    """Найти finite phase-qualified spans, исключая root gaps без stitching."""
    capacity = _capacity(resources)
    spans: list[Span] = []
    current_start: int | None = None
    current_stop = 0
    phase_gap = False
    gap_index = 0
    for start in range(0, int(phase.sample_count), capacity):
        if checkpoint is not None:
            checkpoint()
        stop = min(int(phase.sample_count), start + capacity)
        _, valid = phase_residual_impl(samples, phase, means, start, stop, resources=resources)
        phase_gap |= not bool(np.all(valid))
        blocked, gap_index = _blocked(gaps, start, stop, gap_index)
        qualified = valid & ~blocked
        bounds = np.flatnonzero(
            np.diff(np.concatenate((np.asarray([False]), qualified, np.asarray([False]))))
        )
        for low, high in bounds.reshape(-1, 2).tolist():
            absolute_low, absolute_high = start + int(low), start + int(high)
            if current_start is not None and current_stop == absolute_low:
                current_stop = absolute_high
            else:
                if current_start is not None:
                    spans.append((current_start, current_stop))
                current_start, current_stop = absolute_low, absolute_high
    if current_start is not None:
        spans.append((current_start, current_stop))
    return QualifiedSupport(spans=tuple(spans), phase_gap=phase_gap)


def analyzed_segments(spans: tuple[Span, ...], maximum_samples: int) -> Iterator[tuple[int, int]]:
    """Разбить qualified spans на nonoverlap bounded FFT inputs."""
    for start, stop in spans:
        for segment_start in range(start, stop, int(maximum_samples)):
            yield segment_start, min(stop, segment_start + int(maximum_samples))


def residual_segment(  # noqa: PLR0913, PLR0917 - полный bounded residual input
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    start: int,
    stop: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None,
) -> Float64Array:
    """Материализовать один bounded segment из того же phase residual root."""
    result = np.empty(stop - start, dtype=np.float64)
    capacity = _capacity(resources)
    for chunk_start in range(start, stop, capacity):
        if checkpoint is not None:
            checkpoint()
        chunk_stop = min(stop, chunk_start + capacity)
        residual, valid = phase_residual_impl(
            samples, phase, means, chunk_start, chunk_stop, resources=resources
        )
        if not bool(np.all(valid)):
            raise ValueError("F16 qualified segment changed during residual replay")
        result[chunk_start - start : chunk_stop - start] = residual
    return result


def _capacity(resources: ResourceLimits) -> int:
    capacity = min(
        int(resources.chunk_samples),
        int(resources.hard_max_chunk_samples),
        int(resources.max_work_bytes) // _RESIDUAL_BYTES_PER_SAMPLE,
    )
    if capacity <= 0:
        raise ValueError("F16 resource limits leave no residual capacity")
    return capacity


def _normalize_gaps(gaps: list[Span], sample_count: int) -> tuple[Span, ...]:
    clipped = sorted(
        (max(0, start), min(sample_count - 1, stop))
        for start, stop in gaps
        if start < sample_count and stop >= 0
    )
    merged: list[Span] = []
    for start, stop in clipped:
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, stop))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
    return tuple(merged)


def _blocked(
    gaps: tuple[Span, ...], start: int, stop: int, cursor: int
) -> tuple[NDArray[np.bool_], int]:
    blocked = np.zeros(stop - start, dtype=np.bool_)
    while cursor < len(gaps) and gaps[cursor][1] < start:
        cursor += 1
    probe = cursor
    while probe < len(gaps) and gaps[probe][0] < stop:
        gap_start, gap_stop = gaps[probe]
        low = max(gap_start, start) - start
        high = min(gap_stop, stop - 1) - start
        blocked[low : high + 1] = True
        if gap_stop >= stop - 1:
            break
        probe += 1
    return blocked, probe
