"""F18: идентификаторы, locked recipe, коды, conventions и границы притязаний."""

from __future__ import annotations

from typing import Final

F18_ID: Final = "f18_bicoherence_triads"
F18_INDEX: Final = 17
METHOD: Final = "declared_normalized_bicoherence_dual_surrogate"

PHASE_BINS: Final = 64
SEGMENT_SAMPLES: Final = 4096
WINDOW: Final = "hann_periodic"
OVERLAP_FRACTION: Final = 0.5
BASE_FREQUENCIES_HZ: Final = (3000.0, 5000.0, 10000.0, 20000.0, 50000.0)
TRIAD_RULE: Final = "all_valid_unordered_base_frequency_pairs"
ANALYSIS_HIGH_HZ: Final = 200000.0
NYQUIST_FRACTION_MAX: Final = 0.45
FREQUENCY_MAPPING: Final = "exact_fft_bins"
MAXIMUM_TRIADS: Final = 4096
PHASE_RANDOMIZED_SURROGATE_COUNT: Final = 99
IAAFT_SURROGATE_COUNT: Final = 99
IAAFT_ITERATIONS: Final = 2
IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE: Final = 1e-6
SURROGATE_SEED: Final = 6022
DUAL_NULL_P_VALUE: Final = "maximum_add_one_p_value"
MULTIPLE_TESTING: Final = "benjamini_hochberg"
FALSE_DISCOVERY_RATE: Final = 0.05
MINIMUM_FRAMES: Final = 32

PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
INSUFFICIENT_FRAMES: Final = "insufficient_frames"
TRIAD_OFF_GRID: Final = "triad_off_grid"
TRIAD_ABOVE_NYQUIST: Final = "triad_above_nyquist"
ZERO_DENOMINATOR: Final = "zero_denominator"
IAAFT_NOT_CONVERGED: Final = "iaaft_not_converged"
NO_SIGNIFICANT_TRIAD: Final = "no_significant_triad"
ARTIFACT_LIMIT: Final = "artifact_limit"
DECLARED_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    INSUFFICIENT_FRAMES,
    TRIAD_OFF_GRID,
    TRIAD_ABOVE_NYQUIST,
    ZERO_DENOMINATOR,
    IAAFT_NOT_CONVERGED,
    NO_SIGNIFICANT_TRIAD,
    ARTIFACT_LIMIT,
)

BICOHERENCE_NAME: Final = "f18_bicoherence_squared"
BIPHASE_NAME: Final = "f18_biphase_rad"
TRIAD_LOW_NAME: Final = "f18_triad_low_hz"
TRIAD_HIGH_NAME: Final = "f18_triad_high_hz"
TRIAD_SUM_NAME: Final = "f18_triad_sum_hz"
FRAME_SUPPORT_NAME: Final = "f18_frame_support"
PHASE_RANDOMIZED_P_NAME: Final = "f18_phase_randomized_p_value"
IAAFT_P_NAME: Final = "f18_iaaft_p_value"
DUAL_P_NAME: Final = "f18_dual_null_p_value"
ADJUSTED_P_NAME: Final = "f18_adjusted_p_value"

# Допуск «exact FFT bins» — относительный, на 9 порядков меньше измеренного
# расстояния до ближайшего off-grid шага (0.256 бина при 48 МГц / 4096).
EXACT_BIN_RELATIVE_TOLERANCE: Final = 1e-9
# Слэк неравенства Коши–Буняковского для float64 сумм: 2^-40 от масштаба.
CAUSCHY_SCHWARZ_SLACK: Final = 2**-40
# Child-stream ключи явного default_rng([seed, pass]); порядок ensemble зафиксирован.
SEED_STREAM_CONVENTION: Final = "default_rng_seed_child_phase_randomized_then_iaaft"

BICOHERENCE_CONVENTION: Final = "squared_normalized_bicoherence_in_zero_one"
BIPHASE_CONVENTION: Final = "angle_of_bispectrum_b_times_x_f1_x_f2_conj_x_f1_plus_f2"
SURROGATE_EXCEEDANCE: Final = "surrogate_bicoherence_squared_strictly_above_observed"
DUAL_NULL_COMBINATION: Final = "maximum_of_two_add_one_p_values"
IAAFT_STEP_ORDER: Final = "rank_remap_then_fourier_magnitude_replacement"
IAAFT_AMPLITUDE_RULE: Final = "rank_remap_over_observed_values_sorted_by_absolute_value"
IAAFT_CONVERGENCE: Final = "relative_rms_magnitude_error_of_replaced_surrogate"
IAAFT_DIVERGENCE_REPORTING: Final = "excluded_surrogate_reported_as_iaaft_not_converged"
BH_SCOPE: Final = "single_step_up_pass_over_every_triad_with_a_reported_p_value"
BIPHASE_AVAILABILITY: Final = "significant_triad_with_nonzero_bispectrum_magnitude"
FRAMED_SUPPORT_CONVENTION: Final = "samples_covered_by_complete_phase_qualified_frames"
TRIAD_CAP_CONVENTION: Final = "maximum_triads_bounds_the_candidate_count_not_the_rule"
SURROGATE_PHASE_MEAN_CONVENTION: Final = (
    "surrogate_is_built_from_the_observed_phase_removed_residual"
)

SPEC_GAPS: Final = (
    (
        "F18-1: the declared IAAFT convergence check has exactly two readings and neither "
        "makes iaaft_not_converged informative. Checking the spectrum right after the "
        "amplitude rank remap never reaches the declared 1e-6 relative RMS magnitude error: "
        "measured plateaus at 0.655 for Gaussian residuals and 1.020 for a record-like "
        "residual, which is the phase-only random-phase null level, so every surrogate would "
        "be excluded and the conservative null would be empty on every record. Checking the "
        "finished surrogate instead is exact by construction (3.4e-16) because the declared "
        "step order ends in Fourier magnitude replacement, which makes the check a no-op. "
        "This engine runs the declared 2 iterations without an early exit, keeps the "
        "declared 1e-6 tolerance as the acceptance test of the produced surrogate, and "
        "excludes a surrogate that fails it. The locked values were not retuned."
    ),
    (
        "F18-2: the declared 99+99 surrogate counts put the add-one p floor at 1/100 = 0.01, "
        "while one Benjamini-Hochberg pass with q=0.05 over the 15 declared triads only "
        "declares p=0.01 significant from rank 3 upward (threshold i*q/m = 0.01 at i=3). A "
        "family can therefore only report a significant triad if at least three triads reach "
        "the floor under both nulls, and the adjusted p-value of exactly three such triads "
        "lands on 0.05000000000000001 > q in float64. Significance is taken from the step-up "
        "decision rule, which is stable there; the locked counts and q were not retuned."
    ),
    (
        "F18-3: the declared add-one exceedance comparison is not specified. With >= a "
        "record built from exact-bin sinusoids is never significant: b2 saturates at 1.0 for "
        "the observation and for every phase-randomized surrogate, because a random constant "
        "phase per component still cancels in X(f1)X(f2)conj(X(f1+f2)) across frames. "
        "Measured on the locked fixture, 64-66 of 99 surrogates were counted as exceedances "
        "purely on the tie, giving p = 0.65..0.67 and a permanently no_significant_triad "
        "family. This engine therefore uses the strict comparison "
        "surrogate_b2 > observed_b2, the standard definition for a continuous statistic; the "
        "add-one numerator is unchanged."
    ),
    (
        "F18-4: bicoherence is bounded by 1, and a record whose triad components are "
        "frame-coherent saturates it. Measured at fs=1.024 MHz with a 1 percent noise floor "
        "over the same coupled carrier set: observed b2 = 0.999999, the phase-randomized "
        "surrogates also reach 1.0, roughly half of 99 surrogates exceed on round-off, and "
        "0 of 15 declared triads pass Benjamini-Hochberg (PARTIAL, no_significant_triad) at "
        "both 65 and 249 frames. The dual null therefore has no resolution at saturation and "
        "a triad-saturated record is honestly reported as not significant rather than "
        "significant; the estimate is usable only where the triad is not saturated. Locked "
        "counts, q and estimator were not retuned."
    ),
    (
        "F18-5: the declared base frequencies are off grid at every capture rate this "
        "project actually uses, so the family is UNAVAILABLE there by construction. At "
        "fs=500 kHz - the canonical rate of nine E2E-reduced tests - the 4096-sample step "
        "is 122.0703 Hz and the bases land at bins 24.576, 40.96, 81.92, 163.84 and 409.6, "
        "so 0 of the 15 declared triads are measurable and the family reports "
        "triad_off_grid. At the 48 MHz device maximum the step is 11718.75 Hz and 3000 Hz "
        "lands at bin 0.256, again 0 of 15. At fs=8 kHz the Nyquist clamp gives "
        "effective_high = min(200000, 0.45 * 8000) = 3600 Hz, below the smallest triad sum "
        "of 6000 Hz, so all 15 triads report triad_above_nyquist instead. Exact grids exist "
        "only where fs/4096 divides the 1000 Hz gcd of the bases, that is fs = 4096000/k: "
        "1.024 MHz, 512 kHz and 256 kHz carry all 5 bases and all 15 triads, while "
        "204.8 kHz and 102.4 kHz clamp the highest sums. Decisive constraint: "
        "acquire_validation._rate_code accepts ONLY integer 1..15 MHz for a hardware "
        "capture, and no integer-megahertz rate divides 4096000 = 2^15 * 5^3, because "
        "k * 10^6 = k * 2^6 * 5^6 would require 5^6 | 5^3. F18 therefore cannot produce a "
        "measurement on any hardware record at any supported rate; 500 kHz and 8 kHz are "
        "simulation-only rates. The locked bases, segment length "
        "and exact_fft_bins mapping were not retuned: rounding an off-grid frequency to the "
        "nearest bin would fabricate a component the record does not contain."
    ),
)

CLAIM_BOUNDARY: Final = (
    "squared normalized bicoherence in one record is a descriptive phase-coupling "
    "statistic under two declared within-session surrogate nulls; no calibration, "
    "IEC 61000-4-30 compliance, GUM-conformant uncertainty, physical mechanism, "
    "coupling path, source identity, primary-side behavior, practical utility, or "
    "causation is established; unavailable is never fabricated"
)
