"""Locked enum and dependency values for characterization families."""

from typing import Final

type LockedValue = str | int | float | tuple[str | float, ...]

LOCKED_VALUES: Final[dict[str, dict[str, LockedValue]]] = {
    "f01_phase_cycle": {
        "resampled_samples_rule": "round_window_s_times_sample_rate_hz",
        "interpolation": "linear",
    },
    "f02_amplitude_time_shape": {
        "template_family_id": "f01_phase_cycle",
        "template_field": "x_template_v",
        "coarse_delay_method": "fft_cross_correlation",
        "delay_refinement": "parabolic",
    },
    "f03_interharmonic_tracking": {"gap_interpolation": "none"},
    "f04_multicycle_periodicity": {
        "base_interval": "one_cycle",
        "maximum_averaging_fraction_of_record": 1 / 3,
        "carrier_source_family_id": "f06_modulation_trajectories",
    },
    "f05_phase_conditioned_statistics": {
        "event_source": "root_events",
        "circular_average": "unit_vector",
    },
    "f06_modulation_trajectories": {
        "filter": "butterworth_sos",
        "filter_phase": "zero",
        "detrend": "constant",
        "instantaneous_frequency_difference": "central",
    },
    "f07_comb_sideband_cepstrum": {
        "windows": ("hann", "blackman"),
        "spacing_crosscheck": "magnitude_spectrum_autocorrelation",
    },
    "f08_transient_morphology": {"baseline": "linear_detrend"},
    "f09_event_ordering": {
        "event_type_fields": ("polarity", "dominant_band"),
        "dead_time_handling": "exclude_intervals",
        "gap_handling": "exclude_waiting_intervals",
    },
    "f10_threshold_episode_surface": {
        "scale": "mad_times_1.4826",
        "threshold_sigma": (3.0, 5.0, 8.0, 12.0),
        "edge_episode_handling": "occupancy_only_truncated",
    },
    "f11_conditional_distributions": {
        "band_interval_rule": "left_closed_right_open_last_closed",
        "mode_source_family_id": "f15_interpretable_modes",
        "mode_conditioning_rule": "event_peak_window_nearest_canonical_medoid",
        "mode_distance_tie_break": "lowest_canonical_mode_label",
        "quantities": (
            "absolute_peak_v",
            "duration_s",
            "dominant_frequency_hz",
            "v2_s",
            "polarity_counts",
        ),
        "quantile_method": "linear",
        "cdf_points": 129,
    },
    "f12_spectral_kurtosis": {
        "window": "hann_periodic",
        "detrend": "constant",
        "surrogate": "fft_phase_randomized",
        "search_adjustment": "surrogate_global_maximum",
        "multiple_testing": "benjamini_hochberg",
    },
    "f13_band_envelope_coactivity": {
        "filter": "butterworth_sos",
        "filter_phase": "zero",
        "lag_tie_break": "minimum_absolute_then_negative",
    },
    "f14_cross_channel_event_association": {
        "nearest_event_tie_break": "earlier_target",
        "boundary_handling": "exclude_incomplete_windows",
    },
    "f15_interpretable_modes": {
        "features": (
            "rms_v",
            "crest_factor",
            "band_3000_10000_rms_v",
            "band_10000_50000_rms_v",
            "band_50000_200000_rms_v",
            "event_count",
            "f10_occupancy_5mad",
        ),
        "standardization": "median_mad",
        "distance": "euclidean",
        "initialization": "pam_build",
        "optimization": "pam_swap",
        "tie_break": "lowest_window_index",
        "label_order": "medoid_rms_then_index",
        "stability_metric": "adjusted_rand_index",
        "subsampling": "even_floor_index",
    },
    "f16_multiscale_memory": {
        "autocovariance": "unbiased_fft_linear",
        "partial_count_window_handling": "discard",
    },
    "f17_cyclic_spectral_coherence": {
        "window": "hann_periodic",
        "frequency_mapping": "exact_symmetric_fft_bins",
        "surrogate": "complete_cycle_fisher_yates_permutation",
        "multiple_testing": "benjamini_hochberg",
    },
    "f18_bicoherence_triads": {
        "window": "hann_periodic",
        "triad_rule": "all_valid_unordered_base_frequency_pairs",
        "frequency_mapping": "exact_fft_bins",
        "dual_null_p_value": "maximum_add_one_p_value",
        "multiple_testing": "benjamini_hochberg",
    },
}
