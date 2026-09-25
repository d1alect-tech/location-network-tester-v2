"""F12: идентификаторы, locked recipe, коды и границы притязаний."""

from __future__ import annotations

from typing import Final

F12_ID: Final = "f12_spectral_kurtosis"
F12_INDEX: Final = 11
METHOD: Final = "antoni_multiscale_stft_max_search_surrogate"

PHASE_BINS: Final = 64
SEGMENT_SAMPLES: Final = (256, 1024, 4096, 16384)
WINDOW: Final = "hann_periodic"
OVERLAP_FRACTION: Final = 0.5
DETREND: Final = "constant"
ANALYSIS_LOW_HZ: Final = 3000.0
ANALYSIS_HIGH_HZ: Final = 200_000.0
NYQUIST_FRACTION_MAX: Final = 0.45
MINIMUM_FRAMES: Final = 32
SURROGATE: Final = "fft_phase_randomized"
SURROGATE_COUNT: Final = 199
SURROGATE_SEED: Final = 6022
SEARCH_ADJUSTMENT: Final = "surrogate_global_maximum"
MULTIPLE_TESTING: Final = "benjamini_hochberg"
FALSE_DISCOVERY_RATE: Final = 0.05
MAXIMUM_STORED_BINS: Final = 4096

PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
SCALE_UNSUPPORTED: Final = "scale_unsupported"
INSUFFICIENT_FRAMES: Final = "insufficient_frames"
ZERO_POWER: Final = "zero_power"
NO_SIGNIFICANT_BIN: Final = "no_significant_bin"
CLIPPED: Final = "clipped"
ARTIFACT_LIMIT: Final = "artifact_limit"
DECLARED_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_UNSUPPORTED,
    INSUFFICIENT_FRAMES,
    ZERO_POWER,
    NO_SIGNIFICANT_BIN,
    CLIPPED,
    ARTIFACT_LIMIT,
)

SPECTRAL_KURTOSIS_NAME: Final = "f12_spectral_kurtosis"
ADJUSTED_P_VALUE_NAME: Final = "f12_adjusted_p_value"
MAXIMUM_SPECTRAL_KURTOSIS_NAME: Final = "f12_maximum_spectral_kurtosis"
FREQUENCY_AXIS_NAME: Final = "f12_frequency_hz"
SELECTED_BAND_LOW_NAME: Final = "f12_selected_band_low_hz"
SELECTED_BAND_HIGH_NAME: Final = "f12_selected_band_high_hz"
FRAME_COUNT_NAME: Final = "f12_frame_count"
SCALE_INDEX_NAME: Final = "f12_scale_index"
SURROGATE_SUPPORT_NAME: Final = "f12_surrogate_support"
WINDOW_SUPPORT_NAME: Final = "f12_window_support"

BH_SCOPE: Final = "one_family_wide_finite_candidate_list"
MAXIMUM_TIE_BREAK: Final = "lowest_scale_then_lowest_frequency"
SELECTED_BAND_CONVENTION: Final = "contiguous_significant_bins_in_maximum_scale"
CAP_STORAGE_CONVENTION: Final = "selected_band_maximum_first_then_scale_frequency"
NULL_SCOPE: Final = "one_record_magnitude_spectrum_then_all_declared_stft_scales"
SURROGATE_PHASE_MEAN_CONVENTION: Final = (
    "phase_residual_fft_then_stft_without_second_phase_mean_removal"
)
RANDOM_PHASE_CONVENTION: Final = "strictly_positive_non_nyquist_bins_uniform_0_2pi"
CONJUGATE_SYMMETRY_CONVENTION: Final = "real_inverse_rfft_endpoint_phases_preserved"
CLAIM_BOUNDARY: Final = (
    "within-session phase-randomized null diagnostic corrected for the declared maximum "
    "search; spectral kurtosis is a declared-scale statistic, not a global APD kurtosis; "
    "no calibration, confidence interval, IEC 61000-4-30 compliance, GUM-conformant "
    "uncertainty, source identification, physical nonlinearity, practical utility, or "
    "causation is established; unavailable is never fabricated"
)
