"""Locked family shape and method identifiers for recipe schema 2."""

# ruff: noqa: ISC003 - explicit joins avoid basedpyright implicit-concatenation errors

from typing import Final


def _family(method: str, fields: str) -> tuple[str, tuple[str, ...]]:
    return method, tuple(fields.split())


FAMILY_FIELDS: Final = {
    "f01_phase_cycle": _family(
        "synchronous_relative_harmonic_dft",
        "window_s window_count cycles_per_window maximum_harmonic_order "
        + "resampled_samples_rule interpolation phase_resultant_min h1_concentration_ratio_min",
    ),
    "f02_amplitude_time_shape": _family(
        "template_gain_delay_least_squares",
        "template_family_id template_field coarse_delay_method delay_refinement "
        + "subsample_divisor minimum_event_snr_db residual_fraction_max maximum_events",
    ),
    "f03_interharmonic_tracking": _family(
        "synchronous_bin_nearest_neighbor_tracks",
        "window_s bin_spacing_hz association_tolerance_bins detection_margin_db "
        + "local_median_bin_count minimum_lifetime_windows subharmonic_orders "
        + "gap_interpolation maximum_tracks",
    ),
    "f04_multicycle_periodicity": _family(
        "overlapping_allan_deviation_and_cycle_autocorrelation",
        "base_interval averaging_factors maximum_averaging_fraction_of_record minimum_cycles "
        + "carrier_source_family_id carrier_minimum_snr_db autocorrelation_lags_cycles",
    ),
    "f05_phase_conditioned_statistics": _family(
        "uniform_phase_bin_moments",
        "phase_bins minimum_support_per_bin variance_ddof event_source circular_average",
    ),
    "f06_modulation_trajectories": _family(
        "butterworth_hilbert_analytic_trajectory",
        "band_low_hz band_high_hz filter filter_order filter_phase detrend minimum_snr_db "
        + "maximum_components_in_band instantaneous_frequency_difference phase_increment_max_rad "
        + "envelope_zero_fraction_of_median maximum_stored_samples",
    ),
    "f07_comb_sideband_cepstrum": _family(
        "two_window_real_cepstrum_and_sideband_symmetry",
        "fft_samples windows log_floor_db_below_maximum minimum_quefrency_samples offset_bins "
        + "spacing_crosscheck window_peak_tolerance_bins",
    ),
    "f08_transient_morphology": _family(
        "bounded_single_damped_sinusoid_fit",
        "baseline ringing_frequency_low_hz ringing_frequency_high_hz decay_time_minimum_samples "
        + "decay_time_max_s amplitude_maximum_peak_multiple phase_low_rad phase_high_rad "
        + "maximum_function_evaluations minimum_snr_db residual_fraction_max "
        + "minimum_zero_crossings maximum_events",
    ),
    "f09_event_ordering": _family(
        "typed_transition_and_waiting_time_inventory",
        "event_type_fields cluster_gap_s minimum_event_count dead_time_handling gap_handling "
        + "maximum_events",
    ),
    "f10_threshold_episode_surface": _family(
        "phase_residual_threshold_duration_v2s_surface",
        "phase_bins scale threshold_sigma minimum_duration_s quantiles edge_episode_handling "
        + "maximum_episodes",
    ),
    "f11_conditional_distributions": _family(
        "fixed_phase_band_f15_mode_empirical_distributions",
        "phase_bins bands_hz band_interval_rule mode_source_family_id mode_conditioning_rule "
        + "mode_count mode_distance_tie_break quantities quantiles quantile_method cdf_points "
        + "minimum_support maximum_events",
    ),
    "f12_spectral_kurtosis": _family(
        "antoni_multiscale_stft_max_search_surrogate",
        "phase_bins segment_samples window overlap_fraction detrend analysis_low_hz "
        + "analysis_high_hz nyquist_fraction_max minimum_frames surrogate surrogate_count "
        + "surrogate_seed search_adjustment multiple_testing false_discovery_rate "
        + "maximum_stored_bins",
    ),
    "f13_band_envelope_coactivity": _family(
        "phase_residual_hilbert_envelope_coactivity",
        "bands_hz filter filter_order filter_phase filter_edge_guard_fraction phase_bins "
        + "activity_threshold_mad lag_low_s lag_high_s maximum_lag_points lag_tie_break "
        + "minimum_active_samples",
    ),
    "f14_cross_channel_event_association": _family(
        "bidirectional_event_triggered_cross_channel_association",
        "trigger_window_low_s trigger_window_high_s relative_time_bins nearest_event_lag_low_s "
        + "nearest_event_lag_high_s nearest_event_tie_break phase_bins cycle_shift_offsets "
        + "minimum_triggers maximum_triggers_per_direction boundary_handling",
    ),
    "f15_interpretable_modes": _family(
        "deterministic_pam_fixed_k_medoids",
        "window_s overlap_fraction features standardization distance cluster_count "
        + "initialization optimization maximum_swap_passes tie_break label_order stability_blocks "
        + "stability_metric minimum_windows maximum_labels subsampling",
    ),
    "f16_multiscale_memory": _family(
        "fft_acf_declared_recurrence_nonoverlap_fano",
        "phase_bins autocovariance lags_s recurrence_radius_mad count_windows_s "
        + "count_window_overlap_fraction partial_count_window_handling fano_variance_ddof "
        + "minimum_pairs minimum_count_windows maximum_fft_segment_samples",
    ),
    "f17_cyclic_spectral_coherence": _family(
        "phase_residual_declared_alpha_cycle_permutation_coherence",
        "phase_bins cyclic_frequencies_hz segment_samples window overlap_fraction "
        + "analysis_low_hz analysis_high_hz nyquist_fraction_max frequency_mapping surrogate "
        + "surrogate_count surrogate_seed multiple_testing false_discovery_rate "
        + "minimum_complete_cycles minimum_frames maximum_stored_cells",
    ),
    "f18_bicoherence_triads": _family(
        "declared_normalized_bicoherence_dual_surrogate",
        "phase_bins segment_samples window overlap_fraction base_frequencies_hz triad_rule "
        + "analysis_high_hz nyquist_fraction_max frequency_mapping maximum_triads "
        + "phase_randomized_surrogate_count iaaft_surrogate_count iaaft_iterations "
        + "iaaft_relative_rms_magnitude_tolerance surrogate_seed dual_null_p_value "
        + "multiple_testing false_discovery_rate minimum_frames",
    ),
}

FAMILY_IDS: Final = tuple(FAMILY_FIELDS)
