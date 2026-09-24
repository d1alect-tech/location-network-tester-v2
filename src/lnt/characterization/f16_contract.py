"""F16: идентификаторы, locked recipe, коды и границы притязаний."""

from __future__ import annotations

from typing import Final

F16_ID: Final = "f16_multiscale_memory"
F16_INDEX: Final = 15
METHOD: Final = "fft_acf_declared_recurrence_nonoverlap_fano"

PHASE_BINS: Final = 64
AUTOCOVARIANCE: Final = "unbiased_fft_linear"
LAGS_S: Final = (0.0001, 0.001, 0.01, 0.02, 0.1, 0.5)
RECURRENCE_RADIUS_MAD: Final = (0.5, 1.0, 2.0)
COUNT_WINDOWS_S: Final = (0.02, 0.1, 0.5, 1.0)
COUNT_WINDOW_OVERLAP_FRACTION: Final = 0.0
PARTIAL_COUNT_WINDOW_HANDLING: Final = "discard"
FANO_VARIANCE_DDOF: Final = 1
MINIMUM_PAIRS: Final = 100
MINIMUM_COUNT_WINDOWS: Final = 10
MAXIMUM_FFT_SEGMENT_SAMPLES: Final = 1_048_576

PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
SCALE_ZERO: Final = "scale_zero"
LAG_ABOVE_SUPPORT: Final = "lag_above_support"
INSUFFICIENT_PAIRS: Final = "insufficient_pairs"
INSUFFICIENT_COUNT_WINDOWS: Final = "insufficient_count_windows"
ZERO_EVENT_RATE: Final = "zero_event_rate"
GAPS_PRESENT: Final = "gaps_present"
DECLARED_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
    LAG_ABOVE_SUPPORT,
    INSUFFICIENT_PAIRS,
    INSUFFICIENT_COUNT_WINDOWS,
    ZERO_EVENT_RATE,
    GAPS_PRESENT,
)

AUTOCORRELATION_NAME: Final = "f16_normalized_autocorrelation"
RECURRENCE_RATE_NAME: Final = "f16_recurrence_rate"
COUNT_MEAN_NAME: Final = "f16_count_mean"
COUNT_VARIANCE_NAME: Final = "f16_count_variance"
FANO_FACTOR_NAME: Final = "f16_fano_factor"

LAG_SAMPLE_CONVENTION: Final = "nearest_integer"
MAD_CONVENTION: Final = "population_median_absolute_deviation_per_analyzed_segment"
ACF_AGGREGATION: Final = "pair_weighted_unbiased_linear_covariance"
ANALYZED_SEGMENT_CONVENTION: Final = "gaps_then_nonoverlap_maximum_fft_input"
COUNT_WINDOW_CONVENTION: Final = "global_sample_zero_nonoverlap_discard_partial"
CLAIM_BOUNDARY: Final = (
    "finite-record descriptive summaries at declared lags and windows; no calibration, "
    "IEC 61000-4-30 compliance, GUM-conformant uncertainty, long memory, stationarity, "
    "physical mechanism, population behavior, or causation is established; unavailable "
    "is never fabricated"
)
