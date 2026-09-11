"""Bounded phase-conditioned means and residual slices."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.phase_model import PhaseCycles, PhaseMeans, phase_bins_impl
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import PhaseSettings, ResourceLimits

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]


def compute_phase_means_impl(
    samples: FloatInput,
    phase: PhaseCycles,
    *,
    settings: PhaseSettings,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> PhaseMeans:
    """Accumulate native saved-voltage means without retaining record-sized arrays."""
    if checkpoint is not None:
        checkpoint()
    bin_count = settings.phase_bins
    sums = np.zeros(bin_count, dtype=np.float64)
    counts = np.zeros(bin_count, dtype=np.int64)
    if phase.status is Status.UNAVAILABLE:
        return _result(sums, counts, settings, "phase_reference_unavailable")
    bytes_per_sample = 64
    chunk_samples = min(resources.chunk_samples, resources.max_work_bytes // bytes_per_sample)
    if chunk_samples < 1:
        return _result(sums, counts, settings, "phase_mean_work_budget_too_small")
    for start in range(0, int(samples.size), chunk_samples):
        if checkpoint is not None:
            checkpoint()
        stop = min(int(samples.size), start + chunk_samples)
        values = np.asarray(samples[start:stop], dtype=np.float64)
        indices, valid = phase_bins_impl(phase, start, stop, bin_count)
        valid &= np.isfinite(values)
        sums += np.bincount(indices[valid], weights=values[valid], minlength=bin_count)
        counts += np.bincount(indices[valid], minlength=bin_count)
    return _result(sums, counts, settings, None)


def phase_residual_impl(
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    start_sample: int,
    stop_sample: int,
) -> tuple[Float64Array, BoolArray]:
    """Subtract qualified phase means for one requested sample slice."""
    values = np.asarray(samples[start_sample:stop_sample], dtype=np.float64)
    indices, valid = phase_bins_impl(phase, start_sample, stop_sample, means.means_v.size)
    valid &= np.isfinite(values) & means.valid_bins[indices]
    residual = np.zeros(values.size, dtype=np.float64)
    residual[valid] = values[valid] - means.means_v[indices[valid]]
    return residual, valid


def _result(
    sums: Float64Array,
    counts: Int64Array,
    settings: PhaseSettings,
    reason: str | None,
) -> PhaseMeans:
    valid = counts >= settings.minimum_support_per_bin
    means = np.zeros(sums.size, dtype=np.float64)
    means[valid] = sums[valid] / counts[valid]
    if np.all(valid):
        status, result_reason = Status.AVAILABLE, reason
    else:
        status = Status.PARTIAL if np.any(valid) else Status.UNAVAILABLE
        result_reason = reason or "insuff_phase_support"
    return PhaseMeans(
        means_v=means,
        counts=counts,
        valid_bins=valid,
        status=status,
        reason_code=result_reason,
    )
