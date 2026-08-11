"""Bounded-memory robust detector for transient candidate events."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.events.metrics import EventRun, MetricContext, materialize_event
from lnt.events.models import (
    BaselineFloor,
    EventInventory,
    UnqualifiedGap,
)
from lnt.events.settings import MAD_TO_SIGMA, DetectionSettings

FloatArray = NDArray[np.floating]


@dataclass(slots=True)
class _Run:
    """Mutable bounded accumulator used only while adjacent runs are merged."""

    start: int
    end: int
    peak: int
    peak_value: float
    peak_deviation: float
    peak_sigma: float
    positive: bool
    negative: bool
    excess_energy_sum: float


@dataclass(frozen=True, slots=True, kw_only=True)
class _ScanContext:
    """Inputs and accumulators shared by bounded chunk scans."""

    samples: FloatArray
    settings: DetectionSettings
    baseline: BaselineFloor | None
    runs: list[_Run]
    gaps: list[tuple[int, int]]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Block:
    """Thresholded block arrays with a global sample offset."""

    candidates: NDArray[np.bool_]
    deviation: NDArray[np.float64]
    values: NDArray[np.float64]
    sigma: NDArray[np.float64]
    offset: int


def detect_events(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    settings: DetectionSettings,
    baseline: BaselineFloor | None = None,
) -> EventInventory:
    """Inventories candidates without assigning a physical cause.

    Noise statistics are constant over explicit ``noise_step_samples`` blocks and
    use clipped centred windows. Equal-magnitude peak ties choose the earliest sample.
    """
    _validate_inputs(samples, sample_rate_hz, baseline)
    sample_count = int(samples.size)
    runs: list[_Run] = []
    gaps: list[tuple[int, int]] = []
    scan_context = _ScanContext(
        samples=samples, settings=settings, baseline=baseline, runs=runs, gaps=gaps
    )
    for chunk_start in range(0, sample_count, settings.chunk_samples):
        chunk_end = min(sample_count, chunk_start + settings.chunk_samples)
        _scan_chunk(scan_context, chunk_start, chunk_end)
    merged = _merge_runs(runs, settings.max_gap_samples, gaps)
    metric_context = MetricContext(
        samples=samples, sample_rate_hz=sample_rate_hz, settings=settings
    )
    events = tuple(
        materialize_event(
            EventRun(
                start=run.start,
                end=run.end,
                peak=run.peak,
                peak_value=run.peak_value,
                peak_deviation=run.peak_deviation,
                peak_sigma=run.peak_sigma,
                positive=run.positive,
                negative=run.negative,
                excess_energy_sum=run.excess_energy_sum,
            ),
            metric_context,
        )
        for run in merged
    )
    gap_models = tuple(
        UnqualifiedGap(
            start_sample=start,
            end_sample=end,
            start_time_s=start / sample_rate_hz,
            end_time_s=end / sample_rate_hz,
        )
        for start, end in _merge_intervals(gaps)
    )
    settings_json = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return EventInventory(
        schema_version=1,
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        settings_hash=hashlib.sha256(settings_json.encode("utf-8")).hexdigest(),
        settings=settings,
        baseline_qualification_rule_id=(
            baseline.qualification_rule_id if baseline is not None else None
        ),
        events=events,
        unqualified_gaps=gap_models,
    )


def _validate_inputs(
    samples: FloatArray, sample_rate_hz: float, baseline: BaselineFloor | None
) -> None:
    if samples.ndim != 1 or samples.size == 0:
        raise InputError("кандидаты событий: требуется непустой одномерный ряд")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("кандидаты событий: частота дискретизации должна быть > 0")
    if baseline is not None and (
        baseline.noise_sigma_v.shape != samples.shape or baseline.qualified.shape != samples.shape
    ):
        raise InputError("кандидаты событий: baseline не совпадает с длиной ряда")


def _scan_chunk(context: _ScanContext, chunk_start: int, chunk_end: int) -> None:
    settings = context.settings
    first_block = math.ceil(chunk_start / settings.noise_step_samples) * settings.noise_step_samples
    for start in range(first_block, chunk_end, settings.noise_step_samples):
        low = start
        high = min(start + settings.noise_step_samples, context.samples.size)
        if low >= high:
            continue
        centre = start + (high - start) // 2
        radius = settings.noise_window_samples // 2
        window = np.asarray(
            context.samples[
                max(0, centre - radius) : min(context.samples.size, centre + radius + 1)
            ]
        )
        finite_window = window[np.isfinite(window)]
        if finite_window.size < settings.minimum_noise_samples:
            context.gaps.append((low, high - 1))
            continue
        floor = float(np.median(finite_window))
        sigma = MAD_TO_SIGMA * float(np.median(np.abs(finite_window - floor)))
        if not math.isfinite(sigma) or sigma <= 0.0:
            context.gaps.append((low, high - 1))
            continue
        block = np.asarray(context.samples[low:high], dtype=np.float64)
        qualified = np.isfinite(block)
        sigma_by_sample = np.full(block.size, sigma, dtype=np.float64)
        if context.baseline is not None:
            base_sigma = np.asarray(context.baseline.noise_sigma_v[low:high], dtype=np.float64)
            base_qualified = np.asarray(context.baseline.qualified[low:high], dtype=np.bool_)
            qualified &= base_qualified & np.isfinite(base_sigma) & (base_sigma > 0.0)
            sigma_by_sample = np.maximum(sigma_by_sample, base_sigma)
        _append_false_intervals(qualified, low, context.gaps)
        deviation = block - floor
        candidates = qualified & (np.abs(deviation) >= settings.threshold_sigma * sigma_by_sample)
        _append_runs(
            _Block(
                candidates=candidates,
                deviation=deviation,
                values=block,
                sigma=sigma_by_sample,
                offset=low,
            ),
            context.runs,
        )


def _append_false_intervals(
    mask: NDArray[np.bool_], offset: int, gaps: list[tuple[int, int]]
) -> None:
    _append_intervals(~mask, offset, gaps)


def _append_intervals(mask: NDArray[np.bool_], offset: int, output: list[tuple[int, int]]) -> None:
    padded = np.pad(mask, (1, 1), constant_values=False)
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    output.extend(
        (offset + int(start), offset + int(end) - 1) for start, end in edges.reshape(-1, 2)
    )


def _append_runs(block: _Block, output: list[_Run]) -> None:
    intervals: list[tuple[int, int]] = []
    _append_intervals(block.candidates, 0, intervals)
    for start, end in intervals:
        local = np.abs(block.deviation[start : end + 1])
        peak_local = start + int(np.argmax(local))
        excess = np.maximum(local - block.sigma[start : end + 1], 0.0)
        output.append(
            _Run(
                start=block.offset + start,
                end=block.offset + end,
                peak=block.offset + peak_local,
                peak_value=float(block.values[peak_local]),
                peak_deviation=float(local[peak_local - start]),
                peak_sigma=float(block.sigma[peak_local]),
                positive=bool(np.any(block.deviation[start : end + 1] > 0.0)),
                negative=bool(np.any(block.deviation[start : end + 1] < 0.0)),
                excess_energy_sum=float(np.sum(np.square(excess))),
            )
        )


def _merge_runs(runs: list[_Run], max_gap: int, gaps: list[tuple[int, int]]) -> tuple[_Run, ...]:
    if not runs:
        return ()
    unqualified = _merge_intervals(gaps)
    merged = [runs[0]]
    for current in runs[1:]:
        previous = merged[-1]
        bridge_low, bridge_high = previous.end + 1, current.start - 1
        blocked = any(low <= bridge_high and high >= bridge_low for low, high in unqualified)
        if current.start - previous.end - 1 > max_gap or blocked:
            merged.append(current)
            continue
        if current.peak_deviation > previous.peak_deviation:
            previous.peak = current.peak
            previous.peak_value = current.peak_value
            previous.peak_deviation = current.peak_deviation
            previous.peak_sigma = current.peak_sigma
        previous.end = current.end
        previous.positive |= current.positive
        previous.negative |= current.negative
        previous.excess_energy_sum += current.excess_energy_sum
    return tuple(merged)


def _merge_intervals(intervals: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    if not intervals:
        return ()
    result = [intervals[0]]
    for start, end in intervals[1:]:
        prior_start, prior_end = result[-1]
        if start > prior_end + 1:
            result.append((start, end))
        else:
            result[-1] = (prior_start, max(prior_end, end))
    return tuple(result)
