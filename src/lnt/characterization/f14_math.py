"""F14: относительная сетка, окна, фазовые циклы и baseline-сдвиги."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.phase_stats import phase_residual_impl

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvent
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type EventInterval = tuple[int, int]


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetEvent:
    """Событие с егоQualified cycle index для nearest и baseline."""

    start_sample: int
    end_sample: int
    peak_sample: int
    ordinal: int
    cycle_index: int


def relative_axis(low_s: float, high_s: float, bins: int) -> Float64Array:
    """Вернуть равномерную ось центров относительных временных бинов."""
    return np.linspace(float(low_s), float(high_s), int(bins), dtype=np.float64)


def relative_sample_offsets(axis: Float64Array, sample_rate_hz: float) -> Int64Array:
    """Перевести относительную ось в ближайшие целые отсчёты."""
    return np.rint(np.asarray(axis, dtype=np.float64) * float(sample_rate_hz)).astype(np.int64)


def window_bounds(trigger_peak: int, offsets: Int64Array) -> tuple[int, int]:
    """Вернуть полуоткрытый диапазон окна, включая оба конца оси."""
    positions = np.asarray(offsets, dtype=np.int64)
    if positions.ndim != 1 or positions.size == 0:
        raise ValueError("F14 window offsets must be a nonempty vector")
    return int(trigger_peak + int(positions[0])), int(trigger_peak + int(positions[-1]) + 1)


def qualified_cycles(phase: PhaseCycles) -> tuple[Float64Array, Float64Array]:
    """Оставить только конечные квалифицированные циклы с положительной длиной."""
    starts = np.asarray(phase.cycle_start_samples, dtype=np.float64)
    ends = np.asarray(phase.cycle_end_samples, dtype=np.float64)
    valid = np.asarray(phase.cycle_valid, dtype=np.bool_)
    if starts.shape != ends.shape or valid.shape != starts.shape:
        raise ValueError("F14 phase cycle arrays do not share one shape")
    keep = valid & np.isfinite(starts) & np.isfinite(ends) & (ends > starts)
    return starts[keep], ends[keep]


def target_events(
    events: Sequence[RootEvent], starts: Float64Array, ends: Float64Array
) -> list[TargetEvent]:
    """Оставить события, чей пик лежит в квалифицированном цикле."""
    peaks = np.asarray([event.peak_sample for event in events], dtype=np.int64)
    indices = np.searchsorted(starts, peaks, side="right") - 1
    result: list[TargetEvent] = []
    for event, index in zip(events, indices.tolist(), strict=True):
        if index < 0 or index >= starts.size:
            continue
        peak = int(event.peak_sample)
        if int(starts[index]) <= peak < int(ends[index]):
            result.append(
                TargetEvent(
                    start_sample=int(event.start_sample),
                    end_sample=int(event.end_sample),
                    peak_sample=int(event.peak_sample),
                    ordinal=int(event.ordinal),
                    cycle_index=int(index),
                )
            )
    return result


def event_coverage(
    trigger_peak: int,
    offsets: Int64Array,
    intervals: Sequence[EventInterval],
) -> NDArray[np.bool_]:
    """Пометить биты, центр которых занят хотя бы одним target event."""
    positions = int(trigger_peak) + np.asarray(offsets, dtype=np.int64)
    covered = np.zeros(positions.size, dtype=np.bool_)
    for start, end in intervals:
        covered |= (positions >= int(start)) & (positions <= int(end))
    return covered


def nearest_lag(
    trigger_peak: int,
    events: Sequence[TargetEvent],
    low_s: float,
    high_s: float,
    sample_rate_hz: float,
) -> float | None:
    """Выбрать ближайший target; положительный lag означает target после trigger."""
    candidates: list[tuple[int, int, int, int]] = []
    for event in events:
        lag = int(event.peak_sample) - int(trigger_peak)
        if round(low_s * sample_rate_hz) <= lag <= round(high_s * sample_rate_hz):
            candidates.append((abs(lag), lag, int(event.peak_sample), int(event.ordinal)))
    if not candidates:
        return None
    return float(min(candidates)[1]) / float(sample_rate_hz)


def shifted_intervals(
    events: Sequence[TargetEvent],
    starts: Float64Array,
    ends: Float64Array,
    offset: int,
) -> list[EventInterval]:
    """Сдвинуть событие на целое число циклов, сохраняя фазу и его span."""
    if starts.size == 0 or offset <= 0:
        return []
    result: list[EventInterval] = []
    for event in events:
        source = int(event.cycle_index)
        if source < 0 or source >= starts.size:
            continue
        destination = (source + int(offset)) % int(starts.size)
        source_start = float(starts[source])
        source_length = float(ends[source] - starts[source])
        destination_start = float(starts[destination])
        destination_length = float(ends[destination] - starts[destination])
        scale = destination_length / source_length
        start = round(destination_start + (event.start_sample - source_start) * scale)
        stop = round(destination_start + (event.end_sample - source_start) * scale)
        if start < int(destination_start) or stop >= int(ends[destination]) or stop < start:
            continue
        result.append((start, stop))
    return result


def sample_waveform(  # noqa: PLR0913
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    trigger_peak: int,
    offsets: Int64Array,
    *,
    resources: ResourceLimits,
) -> Float64Array | None:
    """Снять phase residual в центрах бинов; любой неполный support исключает trigger."""
    start, stop = window_bounds(trigger_peak, offsets)
    if start < 0 or stop > phase.sample_count:
        return None
    capacity = min(int(resources.hard_max_chunk_samples), int(resources.max_work_bytes) // 64)
    if capacity <= 0:
        raise ValueError("F14 resource limits leave no residual capacity")
    unique, inverse = np.unique(np.asarray(offsets, dtype=np.int64), return_inverse=True)
    absolute = int(trigger_peak) + unique
    values = np.empty(unique.size, dtype=np.float64)
    for chunk_start in range(start, stop, capacity):
        chunk_stop = min(stop, chunk_start + capacity)
        residual, valid = phase_residual_impl(
            samples, phase, means, chunk_start, chunk_stop, resources=resources
        )
        if not bool(np.all(valid)):
            return None
        selected = (absolute >= chunk_start) & (absolute < chunk_stop)
        if bool(np.any(selected)):
            values[selected] = residual[absolute[selected] - chunk_start]
    return values[inverse]
