"""F17: идентификаторы, locked recipe, коды и границы притязаний."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

F17_ID: Final = "f17_cyclic_spectral_coherence"
F17_INDEX: Final = 16
METHOD: Final = "phase_residual_declared_alpha_cycle_permutation_coherence"
METHOD_VERSION: Final = 1

PHASE_BINS: Final = 64
CYCLIC_FREQUENCIES_HZ: Final = (50.0, 100.0, 150.0, 200.0)
SEGMENT_SAMPLES: Final = 4_096
WINDOW: Final = "hann_periodic"
OVERLAP_FRACTION: Final = 0.5
ANALYSIS_LOW_HZ: Final = 3_000.0
ANALYSIS_HIGH_HZ: Final = 200_000.0
NYQUIST_FRACTION_MAX: Final = 0.45
FREQUENCY_MAPPING: Final = "exact_symmetric_fft_bins"
SURROGATE: Final = "complete_cycle_fisher_yates_permutation"
SURROGATE_COUNT: Final = 199
SURROGATE_SEED: Final = 6_022
MULTIPLE_TESTING: Final = "benjamini_hochberg"
FALSE_DISCOVERY_RATE: Final = 0.05
MINIMUM_COMPLETE_CYCLES: Final = 40
MINIMUM_FRAMES: Final = 32
MAXIMUM_STORED_CELLS: Final = 4_096

PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
INSUFFICIENT_CYCLES: Final = "insufficient_cycles"
INSUFFICIENT_FRAMES: Final = "insufficient_frames"
CYCLIC_FREQUENCY_OFF_GRID: Final = "cyclic_frequency_off_grid"
ZERO_DENOMINATOR: Final = "zero_denominator"
NO_SIGNIFICANT_CELL: Final = "no_significant_cell"
ARTIFACT_LIMIT: Final = "artifact_limit"
DECLARED_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    INSUFFICIENT_CYCLES,
    INSUFFICIENT_FRAMES,
    CYCLIC_FREQUENCY_OFF_GRID,
    ZERO_DENOMINATOR,
    NO_SIGNIFICANT_CELL,
    ARTIFACT_LIMIT,
)

FREQUENCY_NAME: Final = "f17_frequency_hz"
CYCLIC_FREQUENCY_NAME: Final = "f17_cyclic_frequency_hz"
CYCLIC_SPECTRUM_NAME: Final = "f17_cyclic_spectrum_v2"
COHERENCE_NAME: Final = "f17_coherence"
RAW_P_VALUE_NAME: Final = "f17_raw_p_value"
BH_P_VALUE_NAME: Final = "f17_bh_p_value"
SEGMENT_SUPPORT_NAME: Final = "f17_segment_support"

CYCLE_CONCATENATION_CONVENTION: Final = "ceil_cycle_boundaries_half_open_qualified_blocks"
NULL_PERMUTATION_CONVENTION: Final = "ch1_complete_cycles_against_fixed_ch2_fisher_yates"
CHANNEL_PRODUCT_CONVENTION: Final = "ch1_upper_times_conjugate_ch2_lower"
CLAIM_BOUNDARY: Final = (
    "cycle-permutation p-values are record diagnostics, not independent-replicate "
    "confidence intervals; cyclic coherence is a descriptive within-record association "
    "and does not prove source, nonlinearity, causality, or practical utility; no "
    "calibration, IEC 61000-4-30 compliance, GUM-conformant uncertainty, population "
    "inference, or causation is established; unavailable is never fabricated"
)

SPEC_GAPS: Final = (
    (
        "F17-1: the declared cyclic frequencies are off grid at every rate this project "
        "can produce, so the family is UNAVAILABLE on every real record by construction "
        "and reports cyclic_frequency_off_grid. "
        "exact_symmetric_fft_bins places BOTH sidebands at f +/- alpha/2, so with "
        "segment_samples = 4096 the bin spacing fs/4096 must divide alpha/2, not alpha. "
        "The binding alpha is 50 Hz, which requires alpha * 2048 / fs to be integral, that "
        "is fs must divide 102400 = 2^12 * 5^2. Measured alpha/(2*step) values: at "
        "fs=500 kHz (step 122.0703 Hz) 0.2048/0.4096/0.6144/0.8192 -> 0 of 4; at 8 kHz "
        "(1.9531 Hz) 12.8/25.6/38.4/51.2 -> 0 of 4; at 60 kHz (14.6484 Hz) "
        "1.7067/3.4133/5.12/6.8267 -> 0 of 4; at 204.8 kHz (50 Hz) 0.5/1/1.5/2 -> only 2 "
        "of 4, because round(0.5) = 0 is rejected and 1.5 is not integral; at 102.4 kHz "
        "(25 Hz) 1/2/3/4 -> 4 of 4, the highest valid rate. Decisive constraint: "
        "acquire_validation._rate_code accepts ONLY integer 1..15 MHz for a hardware "
        "capture, and no integer-megahertz rate divides 102400, because k * 10^6 = "
        "k * 2^6 * 5^6 would require 5^6 | 5^2. F17 therefore cannot produce a measurement "
        "on any hardware record at any supported rate; 500 kHz, 8 kHz and 60 kHz are "
        "simulation-only rates and fail as well. The unit tests run at 102.4 kHz, the "
        "maximum exact-grid rate, which no capture path in this project produces. The "
        "locked alphas, segment length and mapping were not retuned: rounding to the "
        "nearest bin would fabricate a cyclic frequency the record does not contain, and "
        "interpolating the cyclic spectrum is a different estimator than the declared one."
    ),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class F17Declarations:
    """Полный locked surface F17 без скрытых числовых настроек."""

    phase_bins: int
    cyclic_frequencies_hz: tuple[float, ...]
    segment_samples: int
    window: str
    overlap_fraction: float
    analysis_low_hz: float
    analysis_high_hz: float
    nyquist_fraction_max: float
    frequency_mapping: str
    surrogate: str
    surrogate_count: int
    surrogate_seed: int
    multiple_testing: str
    false_discovery_rate: float
    minimum_complete_cycles: int
    minimum_frames: int
    maximum_stored_cells: int

    def __post_init__(self) -> None:
        """Отвергнуть дрейф любого поля characterization-v1."""
        locked = (
            self.phase_bins == PHASE_BINS
            and self.cyclic_frequencies_hz == CYCLIC_FREQUENCIES_HZ
            and self.segment_samples == SEGMENT_SAMPLES
            and self.window == WINDOW
            and self.overlap_fraction == OVERLAP_FRACTION
            and self.analysis_low_hz == ANALYSIS_LOW_HZ
            and self.analysis_high_hz == ANALYSIS_HIGH_HZ
            and self.nyquist_fraction_max == NYQUIST_FRACTION_MAX
            and self.frequency_mapping == FREQUENCY_MAPPING
            and self.surrogate == SURROGATE
            and self.surrogate_count == SURROGATE_COUNT
            and self.surrogate_seed == SURROGATE_SEED
            and self.multiple_testing == MULTIPLE_TESTING
            and self.false_discovery_rate == FALSE_DISCOVERY_RATE
            and self.minimum_complete_cycles == MINIMUM_COMPLETE_CYCLES
            and self.minimum_frames == MINIMUM_FRAMES
            and self.maximum_stored_cells == MAXIMUM_STORED_CELLS
        )
        if not locked:
            raise ValueError("F17 declarations do not match the locked recipe")
        if (
            not math.isfinite(self.false_discovery_rate)
            or not 0.0 < self.false_discovery_rate <= 1.0
            or self.minimum_complete_cycles <= 0
            or self.minimum_frames <= 0
            or self.maximum_stored_cells <= 0
        ):
            raise ValueError("F17 numeric declarations are outside their domains")

    @classmethod
    def locked(cls) -> F17Declarations:
        """Вернуть точные значения characterization-v1."""
        return cls(
            phase_bins=PHASE_BINS,
            cyclic_frequencies_hz=CYCLIC_FREQUENCIES_HZ,
            segment_samples=SEGMENT_SAMPLES,
            window=WINDOW,
            overlap_fraction=OVERLAP_FRACTION,
            analysis_low_hz=ANALYSIS_LOW_HZ,
            analysis_high_hz=ANALYSIS_HIGH_HZ,
            nyquist_fraction_max=NYQUIST_FRACTION_MAX,
            frequency_mapping=FREQUENCY_MAPPING,
            surrogate=SURROGATE,
            surrogate_count=SURROGATE_COUNT,
            surrogate_seed=SURROGATE_SEED,
            multiple_testing=MULTIPLE_TESTING,
            false_discovery_rate=FALSE_DISCOVERY_RATE,
            minimum_complete_cycles=MINIMUM_COMPLETE_CYCLES,
            minimum_frames=MINIMUM_FRAMES,
            maximum_stored_cells=MAXIMUM_STORED_CELLS,
        )
