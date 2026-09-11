"""Bounded stream of robust transient runs and unqualified gaps."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.events.metrics import EventRun
from lnt.events.models import BaselineFloor, UnqualifiedGap
from lnt.events.settings import MAD_TO_SIGMA, DetectionSettings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

FloatArray = NDArray[np.floating]


@dataclass(slots=True)
class _Run:
    start: int
    end: int
    peak: int
    peak_value: float
    peak_deviation: float
    peak_sigma: float
    positive: bool
    negative: bool
    excess_energy_sum: float


@dataclass(frozen=True, slots=True)
class _Gap:
    start: int
    end: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _ScanContext:
    samples: FloatArray
    settings: DetectionSettings
    baseline: BaselineFloor | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _Block:
    candidates: NDArray[np.bool_]
    deviation: NDArray[np.float64]
    values: NDArray[np.float64]
    sigma: NDArray[np.float64]
    offset: int


@dataclass(slots=True, kw_only=True)
class _Pending:
    sample_rate_hz: float
    max_gap_samples: int
    run: _Run | None = None
    gap: _Gap | None = None

    def accept_run(self, current: _Run) -> Iterator[EventRun | UnqualifiedGap]:
        if self.gap is not None:
            yield _gap_model(self.gap, self.sample_rate_hz)
            self.gap = None
        if self.run is None:
            self.run = current
        elif current.start - self.run.end - 1 <= self.max_gap_samples:
            _merge_run(self.run, current)
        else:
            yield _event_run(self.run)
            self.run = current

    def accept_gap(self, current: _Gap) -> Iterator[EventRun | UnqualifiedGap]:
        if self.run is not None:
            yield _event_run(self.run)
            self.run = None
        if self.gap is None:
            self.gap = current
        elif current.start <= self.gap.end + 1:
            self.gap = _Gap(self.gap.start, max(self.gap.end, current.end))
        else:
            yield _gap_model(self.gap, self.sample_rate_hz)
            self.gap = current

    def flush_safe(self, high: int) -> Iterator[EventRun | UnqualifiedGap]:
        if self.run is not None and high - self.run.end - 1 > self.max_gap_samples:
            yield _event_run(self.run)
            self.run = None
        if self.gap is not None and self.gap.end < high - 1:
            yield _gap_model(self.gap, self.sample_rate_hz)
            self.gap = None

    def finish(self) -> Iterator[EventRun | UnqualifiedGap]:
        if self.run is not None:
            yield _event_run(self.run)
        if self.gap is not None:
            yield _gap_model(self.gap, self.sample_rate_hz)


def stream_event_runs(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    settings: DetectionSettings,
    baseline: BaselineFloor | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> Iterator[EventRun | UnqualifiedGap]:
    """Yield merged fixed-size runs and unqualified gaps in sample order."""
    _checkpoint(checkpoint)
    _validate_inputs(samples, sample_rate_hz, baseline)
    context = _ScanContext(samples=samples, settings=settings, baseline=baseline)
    pending = _Pending(sample_rate_hz=sample_rate_hz, max_gap_samples=settings.max_gap_samples)
    for chunk_start in range(0, int(samples.size), settings.chunk_samples):
        _checkpoint(checkpoint)
        chunk_end = min(int(samples.size), chunk_start + settings.chunk_samples)
        for high, runs, gaps in _scan_chunk(context, chunk_start, chunk_end, checkpoint):
            run_index = gap_index = 0
            while run_index < len(runs) or gap_index < len(gaps):
                take_run = gap_index == len(gaps) or (
                    run_index < len(runs) and runs[run_index].start < gaps[gap_index].start
                )
                if take_run:
                    produced = pending.accept_run(runs[run_index])
                    run_index += 1
                else:
                    produced = pending.accept_gap(gaps[gap_index])
                    gap_index += 1
                yield from _checked(produced, checkpoint)
            yield from _checked(pending.flush_safe(high), checkpoint)
    yield from _checked(pending.finish(), checkpoint)
    _checkpoint(checkpoint)


def _checked(
    items: Iterator[EventRun | UnqualifiedGap], checkpoint: Callable[[], None] | None
) -> Iterator[EventRun | UnqualifiedGap]:
    for item in items:
        yield item
        _checkpoint(checkpoint)


def _checkpoint(checkpoint: Callable[[], None] | None) -> None:
    if checkpoint is not None:
        checkpoint()


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


def _scan_chunk(
    context: _ScanContext,
    chunk_start: int,
    chunk_end: int,
    checkpoint: Callable[[], None] | None,
) -> Iterator[tuple[int, list[_Run], list[_Gap]]]:
    settings = context.settings
    first_block = math.ceil(chunk_start / settings.noise_step_samples) * settings.noise_step_samples
    for start in range(first_block, chunk_end, settings.noise_step_samples):
        _checkpoint(checkpoint)
        high = min(start + settings.noise_step_samples, int(context.samples.size))
        if start < high:
            runs, gaps = _scan_block(context, start, high)
            yield high, runs, gaps


def _scan_block(context: _ScanContext, low: int, high: int) -> tuple[list[_Run], list[_Gap]]:
    settings = context.settings
    centre = low + (high - low) // 2
    radius = settings.noise_window_samples // 2
    window = np.asarray(
        context.samples[max(0, centre - radius) : min(context.samples.size, centre + radius + 1)]
    )
    finite_window = window[np.isfinite(window)]
    if finite_window.size < settings.minimum_noise_samples:
        return [], [_Gap(start=low, end=high - 1)]
    floor = float(np.median(finite_window))
    sigma = MAD_TO_SIGMA * float(np.median(np.abs(finite_window - floor)))
    if not math.isfinite(sigma) or sigma <= 0.0:
        return [], [_Gap(start=low, end=high - 1)]
    values = np.asarray(context.samples[low:high], dtype=np.float64)
    qualified = np.isfinite(values)
    sigma_by_sample = np.full(values.size, sigma, dtype=np.float64)
    if context.baseline is not None:
        base_sigma = np.asarray(context.baseline.noise_sigma_v[low:high], dtype=np.float64)
        base_qualified = np.asarray(context.baseline.qualified[low:high], dtype=np.bool_)
        qualified &= base_qualified & np.isfinite(base_sigma) & (base_sigma > 0.0)
        sigma_by_sample = np.maximum(sigma_by_sample, base_sigma)
    gaps = [_Gap(start, end) for start, end in _intervals(~qualified, low)]
    deviation = values - floor
    candidates = qualified & (np.abs(deviation) >= settings.threshold_sigma * sigma_by_sample)
    runs: list[_Run] = []
    _append_runs(
        _Block(
            candidates=candidates,
            deviation=deviation,
            values=values,
            sigma=sigma_by_sample,
            offset=low,
        ),
        runs,
    )
    return runs, gaps


def _intervals(mask: NDArray[np.bool_], offset: int) -> Iterator[tuple[int, int]]:
    padded = np.pad(mask, (1, 1), constant_values=False)
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return ((offset + int(start), offset + int(end) - 1) for start, end in edges.reshape(-1, 2))


def _append_runs(block: _Block, output: list[_Run]) -> None:
    for start, end in _intervals(block.candidates, 0):
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


def _merge_run(previous: _Run, current: _Run) -> None:
    if current.peak_deviation > previous.peak_deviation:
        previous.peak = current.peak
        previous.peak_value = current.peak_value
        previous.peak_deviation = current.peak_deviation
        previous.peak_sigma = current.peak_sigma
    previous.end = current.end
    previous.positive |= current.positive
    previous.negative |= current.negative
    previous.excess_energy_sum += current.excess_energy_sum


def _event_run(run: _Run) -> EventRun:
    return EventRun(
        start=run.start,
        end=run.end,
        peak=run.peak,
        peak_value=run.peak_value,
        peak_deviation=run.peak_deviation,
        peak_sigma=run.peak_sigma,
        positive=run.positive,
        negative=run.negative,
        excess_energy_sum=run.excess_energy_sum,
    )


def _gap_model(gap: _Gap, sample_rate_hz: float) -> UnqualifiedGap:
    return UnqualifiedGap(
        start_sample=gap.start,
        end_sample=gap.end,
        start_time_s=gap.start / sample_rate_hz,
        end_time_s=gap.end / sample_rate_hz,
    )
