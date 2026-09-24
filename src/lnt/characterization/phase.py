"""Measured CH2 cycle phase and bounded phase-conditioned operations."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.characterization.local_transform import (
    TransformSpec,
    required_sos_halo,
    stream_local_transform,
)
from lnt.characterization.phase_model import (
    CycleBuilder,
    PhaseBudgetExceededError,
    PhaseCycles,
    PhaseMeans,
    phase_bins_impl,
)
from lnt.characterization.phase_stats import (
    compute_phase_means_impl,
    phase_residual_impl,
)
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import PhaseSettings, ResourceLimits

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]

_FILTER_ORDER = 4
_FILTER_CUTOFF_HZ = 200.0
_RETAINED_BYTES_PER_CYCLE = 192

# Полный набор кодов, которыми фазовый корень сообщает о себе. Экспортируется,
# чтобы семейства с собственным объявленным словарём (F13 —
# `phase_reference_unavailable`) нормализовали их по одному источнику истины,
# а не держали свой список в вызывающем слое.
PHASE_ROOT_REASON_CODES: Final = frozenset(
    {
        "no_sync_reference",
        "grid_unstable",
        "insufficient_phase_support",
        "phase_transform_work_budget_too_small",
        "phase_cycle_work_budget_too_small",
        "phase_cycle_work_budget_exceeded",
    }
)

__all__ = [
    "PHASE_ROOT_REASON_CODES",
    "PhaseCycles",
    "PhaseMeans",
    "compute_phase_cycles",
    "compute_phase_means",
    "phase_bins",
    "phase_residual",
]


def compute_phase_cycles(
    ch2: FloatInput | None,
    *,
    sample_rate_hz: float,
    settings: PhaseSettings,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> PhaseCycles:
    """Filter CH2 locally and retain qualified successive rising-crossing pairs."""
    if checkpoint is not None:
        checkpoint()
    sample_count = 0 if ch2 is None else int(ch2.size)
    if ch2 is None:
        return _empty_cycles(sample_rate_hz, sample_count, "no_sync_reference")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 2.0 * _FILTER_CUTOFF_HZ:
        return _empty_cycles(sample_rate_hz, sample_count, "phase_reference_unavailable")
    transform_work_bytes = resources.max_work_bytes // 2
    maximum_cycles = transform_work_bytes // _RETAINED_BYTES_PER_CYCLE
    if maximum_cycles < 1:
        return _empty_cycles(sample_rate_hz, sample_count, "phase_cycle_work_budget_too_small")
    sos = np.asarray(
        signal.butter(
            _FILTER_ORDER,
            _FILTER_CUTOFF_HZ,
            btype="lowpass",
            fs=sample_rate_hz,
            output="sos",
        ),
        dtype=np.float64,
    )
    try:
        required_halo = required_sos_halo(sos)
        halo_failed = False
    except ValueError:
        required_halo = resources.hard_max_chunk_samples
        halo_failed = True
    transform_capacity = min(
        resources.hard_max_chunk_samples,
        transform_work_bytes // 64,
    )
    if transform_capacity <= 4 * required_halo:
        reason = (
            "phase_reference_unavailable"
            if halo_failed
            else "phase_transform_work_budget_too_small"
        )
        return _empty_cycles(sample_rate_hz, sample_count, reason)
    spec = TransformSpec(sos=sos, analytic=False, detrend=False)
    builder = CycleBuilder(sample_rate_hz, settings, maximum_cycles)
    transform_resources = replace(resources, max_work_bytes=transform_work_bytes)

    try:
        for chunk in stream_local_transform(
            ch2, spec=spec, resources=transform_resources, checkpoint=checkpoint
        ):
            if checkpoint is not None:
                checkpoint()
            builder.consume(chunk)
    except PhaseBudgetExceededError:
        return _empty_cycles(sample_rate_hz, sample_count, "phase_cycle_work_budget_exceeded")

    return _phase_result(
        sample_rate_hz,
        sample_count,
        builder,
    )


def phase_bins(
    phase: PhaseCycles, start_sample: int, stop_sample: int, bin_count: int
) -> tuple[Int64Array, BoolArray]:
    """Return phase-bin indices and validity for one requested sample slice."""
    return phase_bins_impl(phase, start_sample, stop_sample, bin_count)


def compute_phase_means(
    samples: FloatInput,
    phase: PhaseCycles,
    *,
    settings: PhaseSettings,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> PhaseMeans:
    """Accumulate native saved-voltage means by fixed-size bin summaries."""
    return compute_phase_means_impl(
        samples, phase, settings=settings, resources=resources, checkpoint=checkpoint
    )


def phase_residual(  # noqa: PLR0913
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    start_sample: int,
    stop_sample: int,
    *,
    resources: ResourceLimits,
) -> tuple[Float64Array, BoolArray]:
    """Subtract qualified phase means for one requested sample slice."""
    return phase_residual_impl(
        samples, phase, means, start_sample, stop_sample, resources=resources
    )


def _phase_result(
    rate: float,
    count: int,
    builder: CycleBuilder,
) -> PhaseCycles:
    start_array = np.asarray(builder.starts, dtype=np.float64)
    end_array = np.asarray(builder.ends, dtype=np.float64)
    valid_array = np.asarray(builder.validity, dtype=np.bool_)
    accepted = bool(np.any(valid_array))
    if not accepted:
        if builder.starts:
            reason = "grid_unstable"
        elif builder.crossing_count:
            reason = "insufficient_phase_support"
        else:
            reason = "phase_reference_unavailable"
        status = Status.UNAVAILABLE
    elif builder.support_broken or not np.all(valid_array):
        reason = "insufficient_phase_support" if builder.support_broken else "grid_unstable"
        status = Status.PARTIAL
    else:
        reason = None
        status = Status.AVAILABLE
    return PhaseCycles(
        sample_rate_hz=rate,
        sample_count=count,
        cycle_start_samples=start_array,
        cycle_end_samples=end_array,
        cycle_valid=valid_array,
        status=status,
        reason_code=reason,
    )


def _empty_cycles(rate: float, count: int, reason: str) -> PhaseCycles:
    return PhaseCycles(
        sample_rate_hz=rate,
        sample_count=count,
        cycle_start_samples=np.empty(0, dtype=np.float64),
        cycle_end_samples=np.empty(0, dtype=np.float64),
        cycle_valid=np.empty(0, dtype=np.bool_),
        status=Status.UNAVAILABLE,
        reason_code=reason,
    )
