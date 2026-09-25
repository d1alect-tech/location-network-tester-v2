"""Контракт и границы притязаний F12."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from lnt.characterization.f12_contract import (
    ANALYSIS_HIGH_HZ,
    ANALYSIS_LOW_HZ,
    BH_SCOPE,
    CAP_STORAGE_CONVENTION,
    CLAIM_BOUNDARY,
    DECLARED_CODES,
    F12_ID,
    F12_INDEX,
    FALSE_DISCOVERY_RATE,
    FRAME_COUNT_NAME,
    FREQUENCY_AXIS_NAME,
    MAXIMUM_STORED_BINS,
    MAXIMUM_TIE_BREAK,
    METHOD,
    MINIMUM_FRAMES,
    NYQUIST_FRACTION_MAX,
    OVERLAP_FRACTION,
    PHASE_BINS,
    SEARCH_ADJUSTMENT,
    SEGMENT_SAMPLES,
    SURROGATE,
    SURROGATE_COUNT,
    SURROGATE_PHASE_MEAN_CONVENTION,
    SURROGATE_SEED,
    WINDOW,
)
from lnt.characterization.f12_result import F12Declarations, F12Result
from lnt.characterization.records import Status


def test_f12_locked_contract_matches_authoritative_recipe() -> None:
    """Recipe, locked values и запреты притязаний совпадают дословно."""
    declarations = F12Declarations.locked()

    assert F12_ID == "f12_spectral_kurtosis"
    assert F12_INDEX == 11
    assert METHOD == "antoni_multiscale_stft_max_search_surrogate"
    assert PHASE_BINS == 64
    assert SEGMENT_SAMPLES == (256, 1024, 4096, 16384)
    assert WINDOW == "hann_periodic"
    assert OVERLAP_FRACTION == 0.5
    assert ANALYSIS_LOW_HZ == 3000.0
    assert ANALYSIS_HIGH_HZ == 200000.0
    assert NYQUIST_FRACTION_MAX == 0.45
    assert MINIMUM_FRAMES == 32
    assert SURROGATE == "fft_phase_randomized"
    assert SURROGATE_COUNT == 199
    assert SURROGATE_SEED == 6022
    assert SEARCH_ADJUSTMENT == "surrogate_global_maximum"
    assert FALSE_DISCOVERY_RATE == 0.05
    assert MAXIMUM_STORED_BINS == 4096
    assert DECLARED_CODES == (
        "phase_reference_unavailable",
        "scale_unsupported",
        "insufficient_frames",
        "zero_power",
        "no_significant_bin",
        "clipped",
        "artifact_limit",
    )
    assert declarations.segment_samples == SEGMENT_SAMPLES
    assert declarations.surrogate_seed == SURROGATE_SEED
    assert FREQUENCY_AXIS_NAME.endswith("_hz")
    assert FRAME_COUNT_NAME == "f12_frame_count"
    assert BH_SCOPE == "one_family_wide_finite_candidate_list"
    assert CAP_STORAGE_CONVENTION == "selected_band_maximum_first_then_scale_frequency"
    assert MAXIMUM_TIE_BREAK == "lowest_scale_then_lowest_frequency"
    assert SURROGATE_PHASE_MEAN_CONVENTION == (
        "phase_residual_fft_then_stft_without_second_phase_mean_removal"
    )
    assert "not a global APD kurtosis" in CLAIM_BOUNDARY
    assert "no calibration" in CLAIM_BOUNDARY
    assert "IEC 61000-4-30 compliance" in CLAIM_BOUNDARY
    assert "GUM-conformant" in CLAIM_BOUNDARY
    assert "unavailable is never fabricated" in CLAIM_BOUNDARY


def test_unavailable_f12_result_keeps_every_measurement_domain_empty() -> None:
    """UNAVAILABLE сохраняет record count, но не публикует нули или выдуманные axes."""
    result = F12Result(
        status=Status.UNAVAILABLE,
        reason_codes=("phase_reference_unavailable",),
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
        sample_count=12_345,
        qualified_sample_count=0,
        analyzed_scale_count=0,
        candidate_count=0,
        significant_bin_count=0,
        stored_significant_bin_count=0,
        surrogate_count=0,
    )

    assert result.status is Status.UNAVAILABLE
    assert all(
        array.size == 0
        for array in (
            result.segment_samples,
            result.frame_count,
            result.scale_available,
            result.frequencies_hz,
            result.scale_index,
            result.spectral_kurtosis,
            result.adjusted_p_value,
        )
    )
    assert result.maximum_spectral_kurtosis is None
    assert result.qualified_sample_count == 0


def test_f12_declarations_reject_recipe_drift() -> None:
    """Locked surface нельзя silently подменить count, seed или scale."""
    with pytest.raises(ValueError, match="locked recipe"):
        replace(F12Declarations.locked(), surrogate_seed=6023)
    with pytest.raises(ValueError, match="locked recipe"):
        replace(F12Declarations.locked(), segment_samples=(256, 1024, 4096))
