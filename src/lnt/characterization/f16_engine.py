"""F16: оркестрация ACF, declared-lag recurrence и nonoverlap Fano."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.event_models import TaggedEvent
from lnt.characterization.f16_contract import (
    GAPS_PRESENT,
    INSUFFICIENT_COUNT_WINDOWS,
    INSUFFICIENT_PAIRS,
    LAG_ABOVE_SUPPORT,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
    ZERO_EVENT_RATE,
)
from lnt.characterization.f16_math import (
    F16CountAccumulator,
    F16MemoryAccumulator,
    F16ScaleZeroError,
    declared_lag_samples,
)
from lnt.characterization.f16_result import F16Declarations, F16Result
from lnt.characterization.f16_segments import (
    analyzed_segments,
    qualified_spans,
    replay_gaps,
    residual_segment,
)
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans


def compute_f16_multiscale_memory(  # noqa: C901, PLR0912, PLR0913, PLR0917 - полный вход F16
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    inventory: RootEvents,
    declarations: F16Declarations,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F16Result:
    """Считать F16 из готовых phase, MAD и full event replay без случайных чисел."""
    if checkpoint is not None:
        checkpoint()
    values = _validate_inputs(samples, phase, means, inventory, declarations, resources)
    if phase.status is Status.UNAVAILABLE or means.status is Status.UNAVAILABLE:
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,), len(values), inventory.accepted_count)
    reasons: set[str] = set()
    if phase.status is Status.PARTIAL or means.status is Status.PARTIAL:
        reasons.add(GAPS_PRESENT)
    if phase.reason_code in PHASE_ROOT_REASON_CODES:
        reasons.add(GAPS_PRESENT)
    if inventory.status is Status.UNAVAILABLE:
        reasons.add(ZERO_EVENT_RATE)
    gaps = replay_gaps(inventory, len(values), checkpoint)
    if gaps:
        reasons.add(GAPS_PRESENT)
    support = qualified_spans(samples, phase, means, gaps, resources, checkpoint)
    if support.phase_gap:
        reasons.add(GAPS_PRESENT)
    if not support.spans:
        codes = {PHASE_REFERENCE_UNAVAILABLE, *reasons}
        return _unavailable(tuple(sorted(codes)), len(values), inventory.accepted_count)
    accumulator = F16MemoryAccumulator.empty(
        declared_lag_samples(declarations.lags_s, phase.sample_rate_hz),
        np.asarray(declarations.recurrence_radius_mad, dtype=np.float64),
    )
    try:
        for start, stop in analyzed_segments(
            support.spans, declarations.maximum_fft_segment_samples
        ):
            residual = residual_segment(samples, phase, means, start, stop, resources, checkpoint)
            accumulator.add(residual)
        autocorrelation = accumulator.autocorrelation()
    except F16ScaleZeroError:
        reasons.add(SCALE_ZERO)
        return _unavailable(tuple(sorted(reasons)), len(values), inventory.accepted_count)
    counts = F16CountAccumulator.empty(
        declarations.count_windows_s, phase.sample_rate_hz, support.spans
    )
    observed_events = 0
    for item in inventory.replay(checkpoint):
        if isinstance(item, TaggedEvent):
            counts.add_peak(int(item.event.peak_sample))
            observed_events += 1
    if observed_events != int(inventory.accepted_count):
        raise ValueError("F16 full replay event count differs from the event inventory")
    summary = counts.summary(declarations.minimum_count_windows)
    lag_available = accumulator.pair_count >= declarations.minimum_pairs
    autocorrelation[~lag_available] = np.nan
    recurrence_rate = accumulator.recurrence_rate()
    recurrence_rate[~lag_available] = np.nan
    _add_support_reasons(
        reasons,
        accumulator.pair_count,
        counts.count_window,
        summary.mean,
        declarations,
    )
    if not bool(np.any(accumulator.pair_count >= declarations.minimum_pairs)) and not bool(
        np.any(summary.available)
    ):
        return _unavailable(tuple(sorted(reasons)), len(values), observed_events)
    return F16Result(
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=tuple(sorted(reasons)),
        lag_s=np.asarray(declarations.lags_s, dtype=np.float64),
        autocorrelation=autocorrelation,
        pair_count=accumulator.pair_count.copy(),
        lag_available=lag_available,
        recurrence_radius_mad=np.asarray(declarations.recurrence_radius_mad, dtype=np.float64),
        recurrence_rate=recurrence_rate,
        count_window_s=np.asarray(declarations.count_windows_s, dtype=np.float64),
        count_window_count=counts.count_window.copy(),
        count_mean=summary.mean,
        count_variance=summary.variance,
        fano_factor=summary.fano_factor,
        count_window_available=summary.available,
        fano_available=summary.fano_available,
        sample_count=len(values),
        qualified_sample_count=accumulator.sample_count,
        analyzed_segment_count=accumulator.segment_count,
        event_count=observed_events,
    )


def _validate_inputs(  # noqa: PLR0913, PLR0917 - полный shared input contract
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    inventory: RootEvents,
    declarations: F16Declarations,
    resources: ResourceLimits,
) -> np.ndarray:
    """Сверить finite channel, phase root, event grid и locked FFT cap."""
    values = np.asarray(samples)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("F16 samples must be one finite vector")
    if (
        phase.sample_count != values.size
        or not math.isfinite(phase.sample_rate_hz)
        or phase.sample_rate_hz <= 0.0
        or inventory.sample_count != values.size
        or not math.isclose(phase.sample_rate_hz, inventory.sample_rate_hz, abs_tol=1e-12)
        or declarations.maximum_fft_segment_samples > resources.hard_max_chunk_samples
    ):
        raise ValueError("F16 roots do not share the measured sample grid")
    shape = (declarations.phase_bins,)
    if (
        means.means_v.shape != shape
        or means.counts.shape != shape
        or means.valid_bins.shape != shape
        or not np.all(np.isfinite(means.means_v))
    ):
        raise ValueError("F16 phase means do not match locked phase bins")
    return values


def _add_support_reasons(
    reasons: set[str],
    pair_count: np.ndarray,
    window_count: np.ndarray,
    mean: np.ndarray,
    declarations: F16Declarations,
) -> None:
    """Добавить exact codes только для structurally sparse declared scales."""
    if bool(np.any(pair_count == 0)):
        reasons.add(LAG_ABOVE_SUPPORT)
    if bool(np.any((pair_count > 0) & (pair_count < declarations.minimum_pairs))):
        reasons.add(INSUFFICIENT_PAIRS)
    if bool(np.any(window_count < declarations.minimum_count_windows)):
        reasons.add(INSUFFICIENT_COUNT_WINDOWS)
    finite_mean = np.isfinite(mean)
    if bool(np.any(finite_mean & (mean == 0.0))):
        reasons.add(ZERO_EVENT_RATE)


def _unavailable(codes: tuple[str, ...], sample_count: int, event_count: int) -> F16Result:
    """Собрать UNAVAILABLE без осей, zero-filled arrays или выдуманных measurements."""
    empty_float = np.empty(0, dtype=np.float64)
    empty_int = np.empty(0, dtype=np.int64)
    empty_bool = np.empty(0, dtype=np.bool_)
    return F16Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        lag_s=empty_float,
        autocorrelation=empty_float,
        pair_count=empty_int,
        lag_available=empty_bool,
        recurrence_radius_mad=empty_float,
        recurrence_rate=empty_float,
        count_window_s=empty_float,
        count_window_count=empty_int,
        count_mean=empty_float,
        count_variance=empty_float,
        fano_factor=empty_float,
        count_window_available=empty_bool,
        fano_available=empty_bool,
        sample_count=sample_count,
        qualified_sample_count=0,
        analyzed_segment_count=0,
        event_count=max(0, event_count),
    )
