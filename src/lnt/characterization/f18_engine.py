"""F18: оркестрация triad grid, dual surrogate null и одного BH-прохода."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f18_contract import (
    IAAFT_NOT_CONVERGED,
    IAAFT_SURROGATE_COUNT,
    INSUFFICIENT_FRAMES,
    NO_SIGNIFICANT_TRIAD,
    PHASE_RANDOMIZED_SURROGATE_COUNT,
    PHASE_REFERENCE_UNAVAILABLE,
    ZERO_DENOMINATOR,
)
from lnt.characterization.f18_frames import (
    SURROGATE_BYTES_PER_SAMPLE,
    observed_residual,
    triad_coefficients,
    zero_phase_means,
)
from lnt.characterization.f18_math import triad_bicoherence
from lnt.characterization.f18_nulls import F18NullPlan, run_both_nulls
from lnt.characterization.f18_result import F18Declarations, F18Result
from lnt.characterization.f18_significance import (
    add_one_p_value,
    benjamini_hochberg,
    dual_null_p_value,
)
from lnt.characterization.f18_triads import build_triad_grid, grid_reason_codes
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

    from lnt.analysis_store.characterization_settings import ResourceLimits, StftSettings
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

type Float64Array = NDArray[np.float64]
type BoolArray = NDArray[np.bool_]
type Checkpoint = Callable[[], None] | None


def compute_f18_bicoherence_triads(  # noqa: PLR0913, PLR0917 - полный вход F18
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    declarations: F18Declarations,
    settings: StftSettings,
    resources: ResourceLimits,
    checkpoint: Checkpoint = None,
) -> F18Result:
    """Посчитать F18 из одного shared framing-пути и двух declared surrogate null."""
    _checkpoint(checkpoint)
    values = _validate_inputs(samples, phase, means, declarations, settings, resources)
    if phase.status is Status.UNAVAILABLE or means.status is Status.UNAVAILABLE:
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,), len(values))
    effective = replace(
        settings,
        segment_samples=declarations.segment_samples,
        overlap_fraction=declarations.overlap_fraction,
        analysis_high_hz=declarations.analysis_high_hz,
        nyquist_fraction_max=declarations.nyquist_fraction_max,
    )
    grid = build_triad_grid(
        declarations.base_frequencies_hz,
        segment_samples=declarations.segment_samples,
        sample_rate_hz=phase.sample_rate_hz,
        analysis_low_hz=settings.analysis_low_hz,
        analysis_high_hz=declarations.analysis_high_hz,
        nyquist_fraction_max=declarations.nyquist_fraction_max,
        maximum_triads=declarations.maximum_triads,
    )
    reasons = grid_reason_codes(grid)
    measurable = grid.measurable
    if not bool(np.any(measurable)):
        return _unavailable(tuple(sorted(reasons)), len(values))
    rows = grid.rows[measurable]
    coefficients = triad_coefficients(
        values,
        phase,
        means,
        sample_rate_hz=phase.sample_rate_hz,
        settings=effective,
        resources=resources,
        distinct_bins=grid.distinct_bins,
        checkpoint=checkpoint,
    )
    frame_count = int(coefficients.shape[1])
    if frame_count < declarations.minimum_frames:
        reasons.add(INSUFFICIENT_FRAMES)
        return _unavailable(tuple(sorted(reasons)), len(values))
    observed = triad_bicoherence(coefficients, rows)
    # Наблюдение считается по measurable-подмножеству, а публикуется всегда в
    # declared-домене. Маска доступности поэтому собирается scatter'ом, а не
    # пересечением: на частично измеримой сетке длины (declared, measurable)
    # расходятся, и пересечение падает ValueError. Неизмеримая триада заведомо
    # недоступна, так что за пределами measurable маска равна False, а не NaN.
    available = np.zeros(measurable.size, dtype=np.bool_)
    available[measurable] = np.isfinite(observed.bicoherence_squared)
    if not bool(np.any(available)):
        reasons.add(ZERO_DENOMINATOR)
        return _unavailable(tuple(sorted(reasons)), len(values))
    phase_counter, iaaft_counter, converged = run_both_nulls(
        F18NullPlan(
            residual=observed_residual(
                values, phase, means, resources=resources, checkpoint=checkpoint
            ),
            phase=phase,
            means=zero_phase_means(means),
            declarations=declarations,
            settings=effective,
            resources=resources,
            sample_rate_hz=phase.sample_rate_hz,
            distinct_bins=grid.distinct_bins,
            rows=rows,
            observed=observed.bicoherence_squared,
        ),
        checkpoint,
    )
    if converged == 0:
        reasons.add(IAAFT_NOT_CONVERGED)
        return _unavailable(tuple(sorted(reasons)), len(values))
    phase_p = _to_domain(
        add_one_p_value(phase_counter.exceedance, PHASE_RANDOMIZED_SURROGATE_COUNT), measurable
    )
    iaaft_p = _to_domain(
        add_one_p_value(iaaft_counter.exceedance, IAAFT_SURROGATE_COUNT), measurable
    )
    dual = dual_null_p_value(phase_p, iaaft_p)
    adjusted, significant = _decision(dual, available, declarations.false_discovery_rate)
    if converged < IAAFT_SURROGATE_COUNT:
        reasons.add(IAAFT_NOT_CONVERGED)
    if not bool(np.any(significant)):
        reasons.add(NO_SIGNIFICANT_TRIAD)
    biphase = _to_domain(np.angle(observed.bispectrum), measurable)
    hop = round(declarations.segment_samples * (1.0 - declarations.overlap_fraction))
    return F18Result(
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=tuple(sorted(reasons)),
        triad_low_hz=grid.low_hz,
        triad_high_hz=grid.high_hz,
        triad_sum_hz=grid.sum_hz,
        bicoherence_squared=_to_domain(observed.bicoherence_squared, measurable),
        biphase_rad=np.where(significant, biphase, np.nan),
        phase_randomized_p_value=phase_p,
        iaaft_p_value=iaaft_p,
        dual_null_p_value=dual,
        adjusted_p_value=adjusted,
        triad_available=available,
        significant=significant,
        frame_support=np.full(grid.declared_count, frame_count, dtype=np.int64),
        sample_count=len(values),
        qualified_sample_count=(frame_count - 1) * hop + declarations.segment_samples,
        frame_count=frame_count,
        declared_triad_count=grid.declared_count,
        measurable_triad_count=int(np.count_nonzero(measurable)),
        off_grid_triad_count=grid.off_grid_count,
        above_nyquist_triad_count=grid.above_nyquist_count,
        dropped_triad_count=grid.dropped_count,
        iaaft_converged_count=converged,
    )


def _to_domain(values: Float64Array, measurable: BoolArray) -> Float64Array:
    """Развернуть измеренное с measurable-подмножества в declared triad-домен."""
    published = np.full(measurable.size, np.nan, dtype=np.float64)
    published[measurable] = values
    return published


def _decision(
    dual: Float64Array, available: BoolArray, false_discovery_rate: float
) -> tuple[Float64Array, BoolArray]:
    """Один BH-проход по всем triad с опубликованным p-value."""
    adjusted = np.full(dual.size, np.nan, dtype=np.float64)
    significant = np.zeros(dual.size, dtype=np.bool_)
    values, flags = benjamini_hochberg(dual[available], false_discovery_rate)
    adjusted[available] = values
    significant[available] = flags
    return adjusted, significant


def _validate_inputs(  # noqa: PLR0913, PLR0917 - полный shared input contract
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    declarations: F18Declarations,
    settings: StftSettings,
    resources: ResourceLimits,
) -> np.ndarray:
    """Сверить finite channel, phase root, phase bins, полосу и resource limits."""
    values = np.asarray(samples)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("F18 samples must be one finite vector")
    if (
        phase.sample_count != int(values.size)
        or not math.isfinite(phase.sample_rate_hz)
        or phase.sample_rate_hz <= 0.0
    ):
        raise ValueError("F18 roots do not share the measured sample grid")
    shape = (declarations.phase_bins,)
    if (
        means.means_v.shape != shape
        or means.counts.shape != shape
        or means.valid_bins.shape != shape
        or not np.all(np.isfinite(means.means_v))
    ):
        raise ValueError("F18 phase means do not match locked phase bins")
    if max(declarations.phase_randomized_surrogate_count, declarations.iaaft_surrogate_count) > int(
        resources.max_surrogates
    ):
        raise ValueError("F18 surrogate counts exceed the declared resource limit")
    if int(declarations.segment_samples) > int(resources.hard_max_chunk_samples):
        raise ValueError("F18 segment samples exceed the declared resource limit")
    if int(values.size) * SURROGATE_BYTES_PER_SAMPLE > int(resources.max_work_bytes):
        raise ValueError("F18 surrogate source exceeds the declared work budget")
    if float(settings.analysis_low_hz) > min(declarations.base_frequencies_hz):
        raise ValueError("F18 analysis band excludes a declared base frequency")
    return values


def _unavailable(codes: tuple[str, ...], sample_count: int) -> F18Result:
    """Собрать UNAVAILABLE без осей, zero-filled arrays или выдуманных measurements."""
    empty_float = np.empty(0, dtype=np.float64)
    empty_int = np.empty(0, dtype=np.int64)
    empty_bool = np.empty(0, dtype=np.bool_)
    return F18Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        triad_low_hz=empty_float,
        triad_high_hz=empty_float,
        triad_sum_hz=empty_float,
        bicoherence_squared=empty_float,
        biphase_rad=empty_float,
        phase_randomized_p_value=empty_float,
        iaaft_p_value=empty_float,
        dual_null_p_value=empty_float,
        adjusted_p_value=empty_float,
        triad_available=empty_bool,
        significant=empty_bool,
        frame_support=empty_int,
        sample_count=sample_count,
        qualified_sample_count=0,
        frame_count=0,
        declared_triad_count=0,
        measurable_triad_count=0,
        off_grid_triad_count=0,
        above_nyquist_triad_count=0,
        dropped_triad_count=0,
        iaaft_converged_count=0,
    )


def _checkpoint(checkpoint: Checkpoint) -> None:
    if checkpoint is not None:
        checkpoint()
