"""F12: bounded phase-residual materialization для record-spectrum null."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.phase import phase_residual
from lnt.characterization.phase_model import PhaseMeans
from lnt.characterization.records import Status
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.phase_model import PhaseCycles

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]


def materialize_phase_residual(
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[Float64Array, int]:
    """Собрать полный residual bounded chunks без смены sample grid."""
    sample_count = int(samples.size)
    if sample_count * np.dtype(np.float64).itemsize > resources.max_work_bytes:
        raise InputError("F12 full residual exceeds max_work_bytes")
    capacity = min(
        int(resources.chunk_samples),
        int(resources.hard_max_chunk_samples),
        int(resources.max_work_bytes) // 64,
    )
    if capacity <= 0:
        raise InputError("F12 residual chunk capacity is zero")
    result = np.empty(sample_count, dtype=np.float64)
    qualified = 0
    for start in range(0, sample_count, capacity):
        if checkpoint is not None:
            checkpoint()
        stop = min(sample_count, start + capacity)
        values, valid = phase_residual(samples, phase, means, start, stop, resources=resources)
        result[start:stop] = values
        qualified += int(np.count_nonzero(valid))
    return result, qualified


def zero_phase_means(phase_bins: int) -> PhaseMeans:
    """Создать явное zero-mean root, не меняющий STFT implementation."""
    return PhaseMeans(
        means_v=np.zeros(phase_bins, dtype=np.float64),
        counts=np.ones(phase_bins, dtype=np.int64),
        valid_bins=np.ones(phase_bins, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
