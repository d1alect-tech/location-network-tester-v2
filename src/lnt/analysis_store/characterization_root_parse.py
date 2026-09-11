"""Parse the four typed root setting groups in recipe schema 2."""

from lnt.analysis_store.characterization_parse import group, integer, number, string
from lnt.analysis_store.characterization_settings import (
    CharacterizationEventSettings,
    PhaseSettings,
    ResourceLimits,
    StftSettings,
)
from lnt.context.json_codec import JsonValue


def parse_resources(value: JsonValue) -> ResourceLimits:
    """Parse bounded resource settings."""
    raw = group(
        value,
        "resource_limits",
        (
            "chunk_samples",
            "hard_max_chunk_samples",
            "max_work_bytes",
            "max_artifact_bytes",
            "max_stored_trajectories",
            "max_surrogates",
            "deterministic_seed",
        ),
    )
    return ResourceLimits(
        chunk_samples=integer(raw["chunk_samples"], "resource_limits.chunk_samples"),
        hard_max_chunk_samples=integer(
            raw["hard_max_chunk_samples"], "resource_limits.hard_max_chunk_samples"
        ),
        max_work_bytes=integer(raw["max_work_bytes"], "resource_limits.max_work_bytes"),
        max_artifact_bytes=integer(raw["max_artifact_bytes"], "resource_limits.max_artifact_bytes"),
        max_stored_trajectories=integer(
            raw["max_stored_trajectories"], "resource_limits.max_stored_trajectories"
        ),
        max_surrogates=integer(raw["max_surrogates"], "resource_limits.max_surrogates"),
        deterministic_seed=integer(raw["deterministic_seed"], "resource_limits.deterministic_seed"),
    )


def parse_phase(value: JsonValue) -> PhaseSettings:
    """Parse phase reference settings."""
    raw = group(
        value,
        "phase",
        (
            "reference_channel",
            "reference_event",
            "grid_frequency_low_hz",
            "grid_frequency_high_hz",
            "phase_bins",
            "minimum_support_per_bin",
        ),
    )
    return PhaseSettings(
        reference_channel=string(raw["reference_channel"], "phase.reference_channel"),
        reference_event=string(raw["reference_event"], "phase.reference_event"),
        grid_frequency_low_hz=number(raw["grid_frequency_low_hz"], "phase.grid_frequency_low_hz"),
        grid_frequency_high_hz=number(
            raw["grid_frequency_high_hz"], "phase.grid_frequency_high_hz"
        ),
        phase_bins=integer(raw["phase_bins"], "phase.phase_bins"),
        minimum_support_per_bin=integer(
            raw["minimum_support_per_bin"], "phase.minimum_support_per_bin"
        ),
    )


def parse_stft(value: JsonValue) -> StftSettings:
    """Parse shared STFT settings."""
    raw = group(
        value,
        "stft",
        (
            "window",
            "segment_samples",
            "overlap_fraction",
            "detrend",
            "analysis_low_hz",
            "analysis_high_hz",
            "nyquist_fraction_max",
        ),
    )
    return StftSettings(
        window=string(raw["window"], "stft.window"),
        segment_samples=integer(raw["segment_samples"], "stft.segment_samples"),
        overlap_fraction=number(raw["overlap_fraction"], "stft.overlap_fraction"),
        detrend=string(raw["detrend"], "stft.detrend"),
        analysis_low_hz=number(raw["analysis_low_hz"], "stft.analysis_low_hz"),
        analysis_high_hz=number(raw["analysis_high_hz"], "stft.analysis_high_hz"),
        nyquist_fraction_max=number(raw["nyquist_fraction_max"], "stft.nyquist_fraction_max"),
    )


def parse_events(value: JsonValue) -> CharacterizationEventSettings:
    """Parse shared event settings."""
    raw = group(
        value,
        "events",
        (
            "detector",
            "threshold_sigma",
            "minimum_snr_db",
            "dead_time_s",
            "dead_time_handling",
            "clipping_fraction_of_range",
            "maximum_events",
            "gap_handling",
        ),
    )
    return CharacterizationEventSettings(
        detector=string(raw["detector"], "events.detector"),
        threshold_sigma=number(raw["threshold_sigma"], "events.threshold_sigma"),
        minimum_snr_db=number(raw["minimum_snr_db"], "events.minimum_snr_db"),
        dead_time_s=number(raw["dead_time_s"], "events.dead_time_s"),
        dead_time_handling=string(raw["dead_time_handling"], "events.dead_time_handling"),
        clipping_fraction_of_range=number(
            raw["clipping_fraction_of_range"], "events.clipping_fraction_of_range"
        ),
        maximum_events=integer(raw["maximum_events"], "events.maximum_events"),
        gap_handling=string(raw["gap_handling"], "events.gap_handling"),
    )
