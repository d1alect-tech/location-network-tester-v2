"""F18: контракт входных отсчётов, недоступный результат и вызов checkpoint."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f18_contract import segment_samples_for
from lnt.characterization.f18_frames import SURROGATE_BYTES_PER_SAMPLE
from lnt.characterization.f18_result import F18Result
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits, StftSettings
    from lnt.characterization.f18_result import F18Declarations
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

type Checkpoint = Callable[[], None] | None


def validate_f18_inputs(  # noqa: PLR0913, PLR0917 - полный shared input contract
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
    if segment_samples_for(phase.sample_rate_hz) > int(resources.hard_max_chunk_samples):
        raise ValueError("F18 segment samples exceed the declared resource limit")
    if int(values.size) * SURROGATE_BYTES_PER_SAMPLE > int(resources.max_work_bytes):
        raise ValueError("F18 surrogate source exceeds the declared work budget")
    if float(settings.analysis_low_hz) > min(declarations.base_frequencies_hz):
        raise ValueError("F18 analysis band excludes a declared base frequency")
    return values


def unavailable_f18_result(
    codes: tuple[str, ...], sample_count: int, segment_samples: int, analysis_rate_hz: float
) -> F18Result:
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
        analysis_rate_hz=analysis_rate_hz,
        segment_samples=segment_samples,
        frame_count=0,
        declared_triad_count=0,
        measurable_triad_count=0,
        off_grid_triad_count=0,
        above_nyquist_triad_count=0,
        dropped_triad_count=0,
        iaaft_converged_count=0,
    )


def checkpoint_f18(checkpoint: Checkpoint) -> None:
    """Продвинуть внешний счётчик прогресса, если он передан."""
    if checkpoint is not None:
        checkpoint()
