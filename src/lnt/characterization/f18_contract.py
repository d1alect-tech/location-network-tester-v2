"""F18: идентификаторы, locked recipe, коды, conventions и границы притязаний."""

from __future__ import annotations

import math
from typing import Final

F18_ID: Final = "f18_bicoherence_triads"
F18_INDEX: Final = 17
METHOD: Final = "declared_normalized_bicoherence_dual_surrogate"

PHASE_BINS: Final = 64
# Сегмент объявлен ДЛИТЕЛЬНОСТЬЮ, а не числом отсчётов: число отсчётов зависит от
# частоты захвата, поэтому объявить его в recipe невозможно — locked_declarations()
# отвергает любое расхождение, а locked() отдаёт константы времени импорта.
# Выведенные отсчёты публикует движок, см. segment_samples_for.
SEGMENT_DURATION_S: Final = 0.001
# Объявленная частота анализа F18. Запись выше неё приводится вниз ЦЕЛЫМ числом
# отсчётов на отсчёт: нецелое отношение запрещено (см. comparability.normalization,
# rule_id bicoherence_analysis_rate_decimation_v1), потому что дробный ресемплинг
# меняет статистику и не выводится из измеренной частоты однозначно. Объявление
# обязано быть константой: locked_declarations() отвергает rate-зависимое поле.
ANALYSIS_RATE_HZ: Final = 1_000_000.0
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


def segment_samples_for(sample_rate_hz: float) -> int:
    """Вывести длину сегмента в отсчётах из объявленной длительности и частоты.

    Единственный источник истины для обеих форм: движок зовёт его на своей
    частоте, тесты — на своих, поэтому объявленная 1 мс и фактический сегмент
    расходятся только если разошлась формула, а не какое-то из двух мест.
    """
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("F18 segment needs a positive sample rate")
    return round(SEGMENT_DURATION_S * sample_rate_hz)


def analysis_factor_for(sample_rate_hz: float) -> int:
    """Вывести целочисленный фактор приведения записи к объявленной частоте анализа.

    Единственный источник истины для формы «во сколько раз приведено»: движок зовёт
    его на ИЗМЕРЕННОЙ частоте захвата до перепривязки корня фазы, тесты — на своих.
    ``max(1, …)`` обязателен именно здесь: частота ниже объявленной даёт
    ``round(< 1) == 0``, а ОБЪЯВЛЕННЫЙ фактор обязан быть не меньше единицы, иначе
    его читатель (сверка нормализации, тест, деление) получил бы несуществующее
    приведение. Второй слой защиты — ранний возврат в f18_decimation, который не
    отдаёт нулевой фактор ресемплеру вовсе.
    """
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("F18 analysis factor needs a positive sample rate")
    factor = round(sample_rate_hz / ANALYSIS_RATE_HZ)
    return max(1, int(factor))


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
        "F18-5: the declared segment used to be a fixed 4096 SAMPLES, so the "
        "exact_fft_bins step was fs/4096 and the family was UNAVAILABLE at every rate this "
        "project actually uses. Measured: at fs=500 kHz the step was 122.0703125 Hz and the "
        "five bases landed at bins 24.576, 40.96, 81.92, 163.84 and 409.6, so 0 of the 15 "
        "declared triads were measurable and the family reported triad_off_grid; at the 48 MHz "
        "device maximum the step was 11718.75 Hz and 3000 Hz landed at bin 0.256, again 0 of "
        "15. Decisive constraint: acquire_validation._rate_code accepts ONLY integer 1..15 MHz "
        "for a hardware capture, and no integer-megahertz rate divides 4096000 = 2^15 * 5^3, so "
        "F18 could not produce a measurement on any hardware record. The defect was the FORM "
        "of the declaration, not the bases: the segment is now declared as a duration, "
        "segment_duration_s = 0.001, and the engine derives segment_samples = round(0.001 * fs) "
        "from the measured rate, so the step is 1000 Hz — the 1000 Hz gcd of the five declared "
        "bases — at every rate whose 1 ms segment divides it exactly. Measured after the fix: "
        "500 kHz (500 samples), 512 kHz (512), 1 MHz (1000), 1.024 MHz (1024) and 8 MHz (8000) "
        "all carry 5 of 5 bases at bins 3, 5, 10, 20 and 50 and measure 15 of 15 triads. The "
        "1 ms rounding is not a universal fix and is not claimed as one: where the 1 ms "
        "segment does not divide the rate, the step leaves the lattice and the family still "
        "reports triad_off_grid honestly — at 204.8 kHz the step is 999.0244 Hz and 3000 Hz "
        "lands at bin 3.0029 (14 off grid, 1 above Nyquist), at 819.2 kHz it is 1000.2442 Hz "
        "and 3000 Hz lands at bin 2.9993, all 15 off grid. At fs=8 kHz the Nyquist clamp gives "
        "effective_high = min(200000, 0.45 * 8000) = 3600 Hz, below the smallest triad sum of "
        "6000 Hz, so all 15 triads report triad_above_nyquist. The locked bases, the 1 ms "
        "duration and the exact_fft_bins mapping were not retuned: rounding an off-grid "
        "frequency to the nearest bin would fabricate a component the record does not contain."
    ),
    (
        "F18-6: the IAAFT iteration does not converge; it is repeated resampling from a stationary "
        "distribution of the map, not a refinement. The meaningful error measure (the spectrum "
        "taken right after the amplitude rank remap) is flat at about 1.35 from iteration 1 to "
        "iteration 200, and max|delta| stays O(1) on every iteration, so no iteration is closer "
        "than the one before it. The implemented convergence check is a no-op: produced_err is "
        "about 3e-16 on every iteration, because the declared step order "
        "rank_remap_then_fourier_magnitude_replacement ends in a Fourier magnitude replacement, "
        "so the produced surrogate has exactly the observed spectrum by construction, which F18-1 "
        "already admits. Empirically the mean null b2 is identical to 4 decimal places at 1, 2, "
        "10 and 100 iterations, and the p-values differ only within Monte-Carlo noise, so the "
        "published statistic does not move: the add-one p floor 1/100 = 0.01 is set by the "
        "declared 99+99 surrogate counts, not by the iteration count. Measured, the IAAFT null is "
        "nearly indistinguishable from the phase-randomized null (correlation 1.000, per-triad "
        "ratios 0.97-2.3), and NEITHER null reproduces the observed amplitude distribution: "
        "maximum deviation 3.3e-2 at max|x| = 0.807, about 4 percent, where a converged IAAFT "
        "would be about 0. IAAFT's defining property, the exact amplitude distribution, is "
        "therefore never achieved, and the declared dual null is in practice two near-duplicate "
        "nulls. The engine keeps the declared 2 iterations, the declared 1e-6 tolerance, the "
        "declared 99+99 surrogate counts and the iaaft_not_converged reporting: the published "
        "statistic is not declared invalid, only the iteration's claimed convergence is "
        "withdrawn."
    ),
)

CLAIM_BOUNDARY: Final = (
    "squared normalized bicoherence in one record is a descriptive phase-coupling "
    "statistic under two declared within-session surrogate nulls; no calibration, "
    "IEC 61000-4-30 compliance, GUM-conformant uncertainty, physical mechanism, "
    "coupling path, source identity, primary-side behavior, practical utility, or "
    "causation is established; unavailable is never fabricated"
)
