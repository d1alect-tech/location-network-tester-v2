"""Explicit numeric domains for every characterization family field."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.analysis_store.errors import RecipeError

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.analysis_store.characterization_parse import ParameterValue

_F10_MAX_AXIS_VALUES: Final = 32

_POSITIVE_INTS: Final = {
    "f01_phase_cycle": "window_count cycles_per_window maximum_harmonic_order",
    "f02_amplitude_time_shape": "subsample_divisor maximum_events",
    "f03_interharmonic_tracking": (
        "association_tolerance_bins local_median_bin_count minimum_lifetime_windows maximum_tracks"
    ),
    "f04_multicycle_periodicity": "minimum_cycles",
    "f05_phase_conditioned_statistics": "phase_bins minimum_support_per_bin variance_ddof",
    "f06_modulation_trajectories": (
        "filter_order maximum_components_in_band maximum_stored_samples"
    ),
    "f07_comb_sideband_cepstrum": (
        "fft_samples minimum_quefrency_samples window_peak_tolerance_bins"
    ),
    "f08_transient_morphology": (
        "decay_time_minimum_samples maximum_function_evaluations minimum_zero_crossings "
        "maximum_events"
    ),
    "f09_event_ordering": "minimum_event_count maximum_events",
    "f10_threshold_episode_surface": "phase_bins maximum_episodes",
    "f11_conditional_distributions": (
        "phase_bins mode_count cdf_points minimum_support maximum_events"
    ),
    "f12_spectral_kurtosis": "phase_bins minimum_frames surrogate_count maximum_stored_bins",
    "f13_band_envelope_coactivity": (
        "filter_order phase_bins maximum_lag_points minimum_active_samples"
    ),
    "f14_cross_channel_event_association": (
        "relative_time_bins phase_bins minimum_triggers maximum_triggers_per_direction"
    ),
    "f15_interpretable_modes": (
        "cluster_count maximum_swap_passes stability_blocks minimum_windows maximum_labels"
    ),
    "f16_multiscale_memory": (
        "phase_bins fano_variance_ddof minimum_pairs minimum_count_windows "
        "maximum_fft_segment_samples"
    ),
    "f17_cyclic_spectral_coherence": (
        "phase_bins segment_samples surrogate_count minimum_complete_cycles minimum_frames "
        "maximum_stored_cells"
    ),
    "f18_bicoherence_triads": (
        "phase_bins maximum_triads phase_randomized_surrogate_count "
        "iaaft_surrogate_count iaaft_iterations minimum_frames"
    ),
}

_NONNEGATIVE_INTS: Final = {
    "f12_spectral_kurtosis": "surrogate_seed",
    "f17_cyclic_spectral_coherence": "surrogate_seed",
    "f18_bicoherence_triads": "surrogate_seed",
}

_POSITIVE_NUMBERS: Final = {
    "f01_phase_cycle": "window_s",
    "f02_amplitude_time_shape": "minimum_event_snr_db",
    "f03_interharmonic_tracking": "window_s bin_spacing_hz detection_margin_db",
    "f04_multicycle_periodicity": "carrier_minimum_snr_db",
    "f06_modulation_trajectories": (
        "band_low_hz band_high_hz minimum_snr_db phase_increment_max_rad"
    ),
    "f07_comb_sideband_cepstrum": "log_floor_db_below_maximum",
    "f08_transient_morphology": (
        "ringing_frequency_low_hz ringing_frequency_high_hz decay_time_max_s "
        "amplitude_maximum_peak_multiple phase_high_rad minimum_snr_db"
    ),
    "f09_event_ordering": "cluster_gap_s",
    "f13_band_envelope_coactivity": "activity_threshold_mad lag_high_s",
    "f14_cross_channel_event_association": ("trigger_window_high_s nearest_event_lag_high_s"),
    "f15_interpretable_modes": "window_s",
    "f12_spectral_kurtosis": "analysis_low_hz analysis_high_hz",
    "f17_cyclic_spectral_coherence": "analysis_low_hz analysis_high_hz",
    "f18_bicoherence_triads": (
        "analysis_high_hz iaaft_relative_rms_magnitude_tolerance segment_duration_s"
    ),
}

_OPEN_CLOSED_UNIT: Final = {
    "f01_phase_cycle": "phase_resultant_min h1_concentration_ratio_min",
    "f02_amplitude_time_shape": "residual_fraction_max",
    "f04_multicycle_periodicity": "maximum_averaging_fraction_of_record",
    "f06_modulation_trajectories": "envelope_zero_fraction_of_median",
    "f08_transient_morphology": "residual_fraction_max",
    "f12_spectral_kurtosis": "nyquist_fraction_max false_discovery_rate",
    "f13_band_envelope_coactivity": "filter_edge_guard_fraction",
    "f17_cyclic_spectral_coherence": "nyquist_fraction_max false_discovery_rate",
    "f18_bicoherence_triads": "nyquist_fraction_max false_discovery_rate",
}

_OVERLAPS: Final = {
    "f12_spectral_kurtosis": "overlap_fraction",
    "f15_interpretable_modes": "overlap_fraction",
    "f16_multiscale_memory": "count_window_overlap_fraction",
    "f17_cyclic_spectral_coherence": "overlap_fraction",
    "f18_bicoherence_triads": "overlap_fraction",
}

_NEGATIVE_NUMBERS: Final = {
    "f08_transient_morphology": "phase_low_rad",
    "f13_band_envelope_coactivity": "lag_low_s",
    "f14_cross_channel_event_association": ("trigger_window_low_s nearest_event_lag_low_s"),
}

_POSITIVE_INT_LISTS: Final = {
    "f03_interharmonic_tracking": "subharmonic_orders",
    "f04_multicycle_periodicity": "averaging_factors autocorrelation_lags_cycles",
    "f07_comb_sideband_cepstrum": "offset_bins",
    "f12_spectral_kurtosis": "segment_samples",
    "f14_cross_channel_event_association": "cycle_shift_offsets",
}

_POSITIVE_NUMBER_LISTS: Final = {
    "f10_threshold_episode_surface": "threshold_sigma",
    "f16_multiscale_memory": "lags_s recurrence_radius_mad count_windows_s",
    "f17_cyclic_spectral_coherence": "cyclic_frequencies_hz",
    "f18_bicoherence_triads": "base_frequencies_hz",
}

_PROBABILITY_LISTS: Final = {
    "f10_threshold_episode_surface": "quantiles",
    "f11_conditional_distributions": "quantiles",
}


def _number(value: ParameterValue, path: str) -> float:
    if not isinstance(value, int | float):
        raise RecipeError(f"рецепт characterization: {path} должен быть числом")
    return float(value)


def _fields(registry: dict[str, str], family_id: str) -> tuple[str, ...]:
    return tuple(registry.get(family_id, "").split())


def _sequence(family: CharacterizationFamily, name: str) -> tuple[ParameterValue, ...]:
    value = family.value(name)
    if not isinstance(value, tuple) or not value:
        raise RecipeError(f"рецепт characterization: {family.id}.{name} должен быть массивом")
    return value


def validate_numeric_shapes(families: tuple[CharacterizationFamily, ...]) -> None:
    """Validate explicit scalar and list domains declared by every family method."""
    for family in families:
        _validate_scalars(family)
        _validate_lists(family)
    _validate_scientific_bounds(families)


def _validate_scientific_bounds(families: tuple[CharacterizationFamily, ...]) -> None:
    by_id = {family.id: family for family in families}
    f06 = by_id["f06_modulation_trajectories"]
    if _number(f06.value("phase_increment_max_rad"), "F06 phase increment") > math.pi:
        raise RecipeError("рецепт characterization: F06 phase increment превышает pi")
    f10 = by_id["f10_threshold_episode_surface"]
    if any(
        len(_sequence(f10, name)) > _F10_MAX_AXIS_VALUES
        for name in ("threshold_sigma", "minimum_duration_s")
    ):
        raise RecipeError("рецепт characterization: F10 axis превышает 32 значения")


def _validate_scalars(  # noqa: C901 - explicit domains replace fragile name heuristics
    family: CharacterizationFamily,
) -> None:
    """Validate one family's explicit scalar domains."""
    for name in _fields(_POSITIVE_INTS, family.id):
        value = family.value(name)
        if not isinstance(value, int) or value <= 0:
            raise RecipeError(f"рецепт characterization: {family.id}.{name} должен быть > 0")
    for name in _fields(_NONNEGATIVE_INTS, family.id):
        value = family.value(name)
        if not isinstance(value, int) or value < 0:
            raise RecipeError(f"рецепт characterization: {family.id}.{name} должен быть >= 0")
    for name in _fields(_POSITIVE_NUMBERS, family.id):
        if _number(family.value(name), f"{family.id}.{name}") <= 0:
            raise RecipeError(f"рецепт characterization: {family.id}.{name} должен быть > 0")
    for name in _fields(_OPEN_CLOSED_UNIT, family.id):
        value = _number(family.value(name), f"{family.id}.{name}")
        if not 0 < value <= 1:
            raise RecipeError(f"рецепт characterization: {family.id}.{name} вне (0, 1]")
    for name in _fields(_OVERLAPS, family.id):
        value = _number(family.value(name), f"{family.id}.{name}")
        if not 0 <= value < 1:
            raise RecipeError(f"рецепт characterization: {family.id}.{name} вне [0, 1)")
    for name in _fields(_NEGATIVE_NUMBERS, family.id):
        if _number(family.value(name), f"{family.id}.{name}") >= 0:
            raise RecipeError(f"рецепт characterization: {family.id}.{name} должен быть < 0")


def _validate_lists(family: CharacterizationFamily) -> None:
    for name in _fields(_POSITIVE_INT_LISTS, family.id):
        if any(not isinstance(value, int) or value <= 0 for value in _sequence(family, name)):
            raise RecipeError(
                f"рецепт characterization: {family.id}.{name} должен содержать int > 0"
            )
    for name in _fields(_POSITIVE_NUMBER_LISTS, family.id):
        if any(_number(value, f"{family.id}.{name}[]") <= 0 for value in _sequence(family, name)):
            raise RecipeError(f"рецепт characterization: {family.id}.{name} должен содержать > 0")
    for name in _fields(_PROBABILITY_LISTS, family.id):
        if any(
            not 0 < _number(value, f"{family.id}.{name}[]") < 1 for value in _sequence(family, name)
        ):
            raise RecipeError(f"рецепт characterization: {family.id}.{name} вне (0, 1)")
    durations = (
        family.value("minimum_duration_s") if family.id == "f10_threshold_episode_surface" else ()
    )
    if isinstance(durations, tuple) and any(
        _number(value, "F10 duration") < 0 for value in durations
    ):
        raise RecipeError("рецепт characterization: F10 durations должны быть >= 0")
