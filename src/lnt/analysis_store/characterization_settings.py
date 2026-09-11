"""Frozen root settings for characterization recipe schema 2."""

from dataclasses import dataclass

from lnt.analysis_store.errors import RecipeError

HARD_MAX_CHUNK_SAMPLES = 1_048_576
HARD_MAX_WORK_BYTES = 268_435_456
HARD_MAX_ARTIFACT_BYTES = 67_108_864
HARD_MAX_STORED_ITEMS = 4096
HARD_MAX_SURROGATES = 199


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceLimits:
    """Bounded processing and persistence limits."""

    chunk_samples: int
    hard_max_chunk_samples: int
    max_work_bytes: int
    max_artifact_bytes: int
    max_stored_trajectories: int
    max_surrogates: int
    deterministic_seed: int

    def __post_init__(self) -> None:
        """Reject nonpositive values and values above hard process caps."""
        values = (
            self.chunk_samples,
            self.hard_max_chunk_samples,
            self.max_work_bytes,
            self.max_artifact_bytes,
            self.max_stored_trajectories,
            self.max_surrogates,
        )
        if any(value <= 0 for value in values) or self.deterministic_seed < 0:
            raise RecipeError("рецепт characterization: resource_limits должны быть положительными")
        if (
            self.chunk_samples > self.hard_max_chunk_samples
            or self.hard_max_chunk_samples > HARD_MAX_CHUNK_SAMPLES
            or self.max_work_bytes > HARD_MAX_WORK_BYTES
            or self.max_artifact_bytes > HARD_MAX_ARTIFACT_BYTES
            or self.max_stored_trajectories > HARD_MAX_STORED_ITEMS
            or self.max_surrogates > HARD_MAX_SURROGATES
        ):
            raise RecipeError("рецепт characterization: превышен жёсткий лимит ресурсов")


@dataclass(frozen=True, slots=True, kw_only=True)
class PhaseSettings:
    """Measured CH2 phase reference and support grid."""

    reference_channel: str
    reference_event: str
    grid_frequency_low_hz: float
    grid_frequency_high_hz: float
    phase_bins: int
    minimum_support_per_bin: int

    def __post_init__(self) -> None:
        """Require the sole supported phase reference and a valid grid."""
        if self.reference_channel != "ch2" or self.reference_event != "rising_zero_crossing":
            raise RecipeError("рецепт characterization: некорректная фазовая опора")
        if (
            self.grid_frequency_low_hz <= 0
            or self.grid_frequency_high_hz <= self.grid_frequency_low_hz
            or self.phase_bins <= 0
            or self.minimum_support_per_bin <= 0
        ):
            raise RecipeError("рецепт characterization: некорректная фазовая сетка")


@dataclass(frozen=True, slots=True, kw_only=True)
class StftSettings:
    """Shared STFT method and analysis band."""

    window: str
    segment_samples: int
    overlap_fraction: float
    detrend: str
    analysis_low_hz: float
    analysis_high_hz: float
    nyquist_fraction_max: float

    def __post_init__(self) -> None:
        """Require the locked transform method and valid geometry."""
        if self.window != "hann_periodic" or self.detrend != "constant":
            raise RecipeError("рецепт characterization: некорректный STFT method")
        if (
            self.segment_samples <= 0
            or self.analysis_low_hz < 0
            or self.analysis_high_hz <= self.analysis_low_hz
            or not 0 <= self.overlap_fraction < 1
            or not 0 < self.nyquist_fraction_max < 1 / 2
        ):
            raise RecipeError("рецепт characterization: некорректная STFT сетка")


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationEventSettings:
    """Shared event inventory method and limits."""

    detector: str
    threshold_sigma: float
    minimum_snr_db: float
    dead_time_s: float
    dead_time_handling: str
    clipping_fraction_of_range: float
    maximum_events: int
    gap_handling: str

    def __post_init__(self) -> None:
        """Require the existing event inventory and bounded settings."""
        if (
            self.detector != "existing_event_inventory"
            or self.dead_time_handling != "exclude_intervals"
            or self.gap_handling != "exclude_crossing_intervals"
        ):
            raise RecipeError("рецепт characterization: некорректный event method")
        if (
            self.threshold_sigma <= 0
            or self.minimum_snr_db <= 0
            or self.dead_time_s <= 0
            or not 0 < self.clipping_fraction_of_range <= 1
            or self.maximum_events <= 0
        ):
            raise RecipeError("рецепт characterization: некорректные event limits")
