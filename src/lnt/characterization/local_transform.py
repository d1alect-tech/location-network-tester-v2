"""Bounded local zero-phase SOS and optional Hilbert transforms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy import signal

from lnt.characterization.local_transform_models import (
    TransformChunk,
    TransformSpec,
    required_sos_halo,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from numpy.typing import NDArray

    from lnt.analysis_store.characterization_settings import ResourceLimits

_REAL_WORK_BYTES_PER_SAMPLE = 64
_ANALYTIC_WORK_BYTES_PER_SAMPLE = 128

__all__ = [
    "TransformChunk",
    "TransformSpec",
    "required_sos_halo",
    "stream_local_transform",
]


@dataclass(frozen=True, slots=True)
class _Context:
    samples: NDArray[np.float32] | NDArray[np.float64]
    spec: TransformSpec
    initial_halo: int
    expanded_capacity: int
    chunk_samples: int
    checkpoint: Callable[[], None] | None


def stream_local_transform(
    samples: NDArray[np.float32] | NDArray[np.float64],
    *,
    spec: TransformSpec,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> Iterator[TransformChunk]:
    """Stream bounded local transforms without claiming full-record FFT equivalence.

    Every supported core has real observations on both halo sides. The fixed work
    factors conservatively gate retained inputs, outputs, and transform temporaries;
    they are bounds for this routine, not claims about exact allocator behavior.
    """
    _checkpoint(checkpoint)
    sample_count = int(samples.size)
    if sample_count == 0:
        _checkpoint(checkpoint)
        return

    initial_halo = required_sos_halo(spec.sos)
    accepted_halo = 2 * initial_halo
    bytes_per_sample = (
        _ANALYTIC_WORK_BYTES_PER_SAMPLE if spec.analytic else _REAL_WORK_BYTES_PER_SAMPLE
    )
    expanded_capacity = min(
        resources.hard_max_chunk_samples,
        resources.max_work_bytes // bytes_per_sample,
    )
    core_limit = min(
        resources.chunk_samples,
        expanded_capacity - 2 * spec.analytic_halo_samples - 4 * initial_halo,
    )
    if core_limit <= 0:
        yield from _unavailable_chunks(
            0,
            sample_count,
            resources.chunk_samples,
            accepted_halo,
            "filter_support_too_short",
        )
        _checkpoint(checkpoint)
        return

    context = _Context(
        samples,
        spec,
        initial_halo,
        expanded_capacity,
        resources.chunk_samples,
        checkpoint,
    )
    scan_samples = min(resources.chunk_samples, expanded_capacity)
    for start, stop, finite in _input_spans(samples, scan_samples, checkpoint):
        if not finite:
            yield from _unavailable_chunks(
                start, stop, resources.chunk_samples, 0, "nonfinite_input"
            )
            continue
        yield from _finite_span_chunks(context, start, stop)
    _checkpoint(checkpoint)


def _input_spans(
    samples: NDArray[np.float32] | NDArray[np.float64],
    scan_samples: int,
    checkpoint: Callable[[], None] | None,
) -> Iterator[tuple[int, int, bool]]:
    pending_start = 0
    pending_finite: bool | None = None
    sample_count = int(samples.size)
    for block_start in range(0, sample_count, scan_samples):
        _checkpoint(checkpoint)
        block_stop = min(sample_count, block_start + scan_samples)
        finite = np.isfinite(samples[block_start:block_stop])
        changes = np.flatnonzero(finite[1:] != finite[:-1]) + 1
        for local_start, local_stop in zip(
            np.concatenate((np.array([0]), changes)),
            np.concatenate((changes, np.array([finite.size]))),
            strict=True,
        ):
            segment_finite = bool(finite[int(local_start)])
            segment_start = block_start + int(local_start)
            if pending_finite is None:
                pending_start = segment_start
                pending_finite = segment_finite
            elif segment_finite != pending_finite:
                yield pending_start, segment_start, pending_finite
                pending_start = segment_start
                pending_finite = segment_finite
            if local_stop == finite.size:
                break
    if pending_finite is not None:
        yield pending_start, sample_count, pending_finite


def _finite_span_chunks(
    context: _Context,
    span_start: int,
    span_stop: int,
) -> Iterator[TransformChunk]:
    accepted_halo = context.spec.analytic_halo_samples + 2 * context.initial_halo
    interior_start = span_start + accepted_halo
    interior_stop = span_stop - accepted_halo
    if interior_start >= interior_stop:
        yield from _unavailable_chunks(
            span_start,
            span_stop,
            context.chunk_samples,
            accepted_halo,
            "filter_support_too_short",
        )
        return
    yield from _unavailable_chunks(
        span_start,
        interior_start,
        context.chunk_samples,
        accepted_halo,
        "filter_support_too_short",
    )
    core_start = interior_start
    while core_start < interior_stop:
        core_stop, values, halo, reason = _resolve_core(
            context, core_start, interior_stop, (span_start, span_stop)
        )
        if values is None:
            yield from _unavailable_chunks(
                core_start,
                core_stop,
                context.chunk_samples,
                halo,
                reason or "filter_context_unstable",
            )
        else:
            yield TransformChunk(core_start, core_stop, values, halo, None)
        core_start = core_stop
    yield from _unavailable_chunks(
        interior_stop,
        span_stop,
        context.chunk_samples,
        accepted_halo,
        "filter_support_too_short",
    )


def _resolve_core(
    context: _Context,
    core_start: int,
    interior_stop: int,
    span: tuple[int, int],
) -> tuple[int, NDArray[np.float64] | NDArray[np.complex128] | None, int, str | None]:
    low_halo = context.initial_halo
    while True:
        high_halo = 2 * low_halo
        window_halo = context.spec.analytic_halo_samples
        required_left = span[0] + window_halo + high_halo
        if core_start < required_left:
            return (
                min(interior_stop, required_left),
                None,
                window_halo + high_halo,
                "filter_context_unstable",
            )
        core_capacity = context.expanded_capacity - 2 * window_halo - 2 * high_halo
        core_stop = min(
            interior_stop,
            core_start + context.chunk_samples,
            span[1] - window_halo - high_halo,
            core_start + core_capacity,
        )
        if core_stop <= core_start:
            return (
                interior_stop,
                None,
                window_halo + low_halo,
                "filter_context_unstable",
            )
        core = (core_start, core_stop)
        low_values, _ = _filter_window(context, core, low_halo)
        high_values, raw_scale = _filter_window(context, core, high_halo)
        difference = float(np.max(np.abs(high_values - low_values), initial=0.0))
        high_scale = float(np.max(np.abs(high_values), initial=0.0))
        if difference <= max(1e-3 * high_scale, 1e-9 * raw_scale):
            values = _finish_transform(context, high_values)
            return core_stop, values, window_halo + high_halo, None
        low_halo = high_halo


def _filter_window(
    context: _Context,
    core: tuple[int, int],
    sos_halo: int,
) -> tuple[NDArray[np.float64], float]:
    _checkpoint(context.checkpoint)
    core_start, core_stop = core
    window_halo = context.spec.analytic_halo_samples
    expanded_start = core_start - window_halo - sos_halo
    expanded_stop = core_stop + window_halo + sos_halo
    block = np.array(context.samples[expanded_start:expanded_stop], dtype=np.float64, copy=True)
    raw_scale = float(np.max(np.abs(block), initial=0.0))
    if context.spec.detrend:
        block -= float(np.mean(block))
    filtered = np.asarray(signal.sosfiltfilt(context.spec.sos, block), dtype=np.float64)
    return filtered[sos_halo : filtered.size - sos_halo].copy(), raw_scale


def _finish_transform(
    context: _Context, filtered_window: NDArray[np.float64]
) -> NDArray[np.float64] | NDArray[np.complex128]:
    halo = context.spec.analytic_halo_samples
    if not context.spec.analytic:
        return filtered_window
    _checkpoint(context.checkpoint)
    analytic = np.asarray(signal.hilbert(filtered_window), dtype=np.complex128)
    return analytic[halo : analytic.size - halo].copy() if halo else analytic


def _unavailable_chunks(
    start: int,
    stop: int,
    chunk_samples: int,
    halo_samples: int,
    reason_code: str,
) -> Iterator[TransformChunk]:
    for chunk_start in range(start, stop, chunk_samples):
        yield TransformChunk(
            chunk_start,
            min(stop, chunk_start + chunk_samples),
            None,
            halo_samples,
            reason_code,
        )


def _checkpoint(checkpoint: Callable[[], None] | None) -> None:
    if checkpoint is not None:
        checkpoint()
