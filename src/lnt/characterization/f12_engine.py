"""F12: orchestration четырёх STFT scales, surrogate maximum и global BH."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f12_candidates import observed_candidates
from lnt.characterization.f12_contract import (
    ARTIFACT_LIMIT,
    CLIPPED,
    NO_SIGNIFICANT_BIN,
    PHASE_REFERENCE_UNAVAILABLE,
    ZERO_POWER,
)
from lnt.characterization.f12_inference import infer_f12_candidates
from lnt.characterization.f12_input import materialize_phase_residual
from lnt.characterization.f12_math import declared_phase_reason
from lnt.characterization.f12_result import F12Result
from lnt.characterization.f12_scales import observe_scale
from lnt.characterization.f12_surrogates import surrogate_global_maxima
from lnt.characterization.f16_segments import longest_qualified_span
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.clipping import ClippingBounds
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.f12_result import F12Declarations
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans


def compute_f12_spectral_kurtosis(  # noqa: C901, PLR0911, PLR0913, PLR0917 - declared F12 QC branches
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    clipping: ClippingBounds,
    inventory: RootEvents,
    declarations: F12Declarations,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F12Result:
    """Считать declared F12 из longest phase-qualified span записи.

    ``sample_count`` публикует полную длину записи, ``qualified_sample_count`` —
    длину span, по которому на самом деле считалось. Оба отказа до выбора span
    оценивают клиппинг и корень фазы на полной записи.
    """
    if checkpoint is not None:
        checkpoint()
    values = _validate_inputs(samples, phase, means, inventory, declarations, resources)
    record_samples = int(values.size)
    if phase.status is Status.UNAVAILABLE or means.status is Status.UNAVAILABLE:
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,), record_samples)
    if phase.reason_code in PHASE_ROOT_REASON_CODES or means.reason_code in PHASE_ROOT_REASON_CODES:
        reason = declared_phase_reason(phase.reason_code or means.reason_code or "")
        return _unavailable((reason,), record_samples)
    if clipping.classify(values) is not False:
        return _unavailable((CLIPPED,), record_samples)
    span = longest_qualified_span(values, phase, means, inventory, resources, checkpoint)
    if span is None:
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,), record_samples)
    (start, stop), phase = span
    values = values[start:stop]
    residual, qualified = materialize_phase_residual(values, phase, means, resources, checkpoint)
    if qualified != values.size:
        return _unavailable((PHASE_REFERENCE_UNAVAILABLE,), record_samples)
    if not np.any(residual * residual > 0.0):
        return _unavailable((ZERO_POWER,), record_samples)
    scales = tuple(
        observe_scale(
            values,
            phase,
            means,
            segment_samples=segment,
            declarations=declarations,
            resources=resources,
            checkpoint=checkpoint,
        )
        for segment in declarations.segment_samples
    )
    if not any(scale.reason_code is None for scale in scales):
        reasons = tuple(sorted({scale.reason_code for scale in scales if scale.reason_code}))
        return _unavailable(reasons, record_samples)
    candidates = observed_candidates(scales)
    if candidates.spectral_kurtosis.size == 0:
        return _unavailable((ZERO_POWER,), record_samples)
    magnitudes = np.abs(np.fft.rfft(residual))
    null_maxima = surrogate_global_maxima(
        residual,
        magnitudes,
        scales,
        declarations=declarations,
        phase=phase,
        resources=resources,
        checkpoint=checkpoint,
    )
    if not np.all(np.isfinite(null_maxima)):
        return _unavailable((ZERO_POWER,), record_samples)
    inference = infer_f12_candidates(
        candidates,
        null_maxima,
        false_discovery_rate=declarations.false_discovery_rate,
        maximum_stored_bins=declarations.maximum_stored_bins,
    )
    reasons = {scale.reason_code for scale in scales if scale.reason_code is not None}
    if inference.significant_count == 0:
        reasons.add(NO_SIGNIFICANT_BIN)
    if inference.significant_count > declarations.maximum_stored_bins:
        reasons.add(ARTIFACT_LIMIT)
    stored = inference.stored_indices
    return F12Result(
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=tuple(sorted(reasons)),
        segment_samples=np.asarray(declarations.segment_samples, dtype=np.int64),
        frame_count=np.asarray([scale.frame_count for scale in scales], dtype=np.int64),
        scale_available=np.asarray([scale.reason_code is None for scale in scales], dtype=np.bool_),
        frequencies_hz=candidates.frequencies_hz[stored].copy(),
        scale_index=candidates.scale_index[stored].copy(),
        spectral_kurtosis=candidates.spectral_kurtosis[stored].copy(),
        adjusted_p_value=inference.adjusted_p_value.copy(),
        maximum_spectral_kurtosis=float(candidates.spectral_kurtosis[inference.maximum_index]),
        selected_scale_index=inference.selected_scale_index,
        selected_band_low_hz=inference.selected_band_low_hz,
        selected_band_high_hz=inference.selected_band_high_hz,
        sample_count=record_samples,
        qualified_sample_count=values.size,
        analyzed_scale_count=sum(scale.reason_code is None for scale in scales),
        candidate_count=candidates.spectral_kurtosis.size,
        significant_bin_count=inference.significant_count,
        stored_significant_bin_count=stored.size,
        surrogate_count=null_maxima.size,
    )


def _validate_inputs(  # noqa: PLR0913, PLR0917 - полный shared input contract
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    inventory: RootEvents,
    declarations: F12Declarations,
    resources: ResourceLimits,
) -> np.ndarray:
    values = np.asarray(samples)
    shape = (declarations.phase_bins,)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("F12 samples must be one finite vector")
    if (
        phase.sample_count != values.size
        or inventory.sample_count != values.size
        or not math.isfinite(phase.sample_rate_hz)
        or phase.sample_rate_hz <= 0.0
        or means.means_v.shape != shape
        or means.counts.shape != shape
        or means.valid_bins.shape != shape
        or not np.all(np.isfinite(means.means_v))
    ):
        raise ValueError("F12 phase roots do not match the measured grid")
    if (
        declarations.surrogate_count > resources.max_surrogates
        or declarations.surrogate_seed != resources.deterministic_seed
        or declarations.maximum_stored_bins > resources.max_stored_trajectories
        or max(declarations.segment_samples) > resources.hard_max_chunk_samples
    ):
        raise ValueError("F12 declarations exceed ResourceLimits")
    return values


def _unavailable(codes: tuple[str, ...], sample_count: int) -> F12Result:
    """Собрать UNAVAILABLE без axes, measurements или support claims."""
    return F12Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        segment_samples=np.empty(0, dtype=np.int64),
        frame_count=np.empty(0, dtype=np.int64),
        scale_available=np.empty(0, dtype=np.bool_),
        frequencies_hz=np.empty(0, dtype=np.float64),
        scale_index=np.empty(0, dtype=np.int64),
        spectral_kurtosis=np.empty(0, dtype=np.float64),
        adjusted_p_value=np.empty(0, dtype=np.float64),
        maximum_spectral_kurtosis=None,
        selected_scale_index=None,
        selected_band_low_hz=None,
        selected_band_high_hz=None,
        sample_count=sample_count,
        qualified_sample_count=0,
        analyzed_scale_count=0,
        candidate_count=0,
        significant_bin_count=0,
        stored_significant_bin_count=0,
        surrogate_count=0,
    )
