"""Аналитические тесты F15 deterministic_pam_fixed_k_medoids."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.bands import ResolvedBand
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.event_models import RootEvents, RootEventSettings, RootTimelineItem
from lnt.characterization.f10_result import F10Result
from lnt.characterization.f15_bands import band_window_rms_v
from lnt.characterization.f15_features import even_floor_indices, f10_occupancy_5mad
from lnt.characterization.f15_modes import compute_f15_modes, fit_f15_pam
from lnt.characterization.f15_pam import (
    adjusted_rand_index,
    pam_build_indices,
    pam_swap_indices,
)
from lnt.characterization.f15_result import (
    DECLARED_CODES,
    EMPTY_CLUSTER,
    FEATURE_NAMES,
    FEATURE_SCALE_ZERO,
    INSUFFICIENT_WINDOWS,
    LABEL_LIMIT,
    METHOD,
    STABILITY_BLOCK_TOO_SHORT,
    F15Result,
    F15Settings,
)
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status
from lnt.features.bands import BandDefinition, EstimandDirection, FrequencyUnit

if TYPE_CHECKING:
    from collections.abc import Iterator


def _four_mode_features() -> tuple[np.ndarray, np.ndarray]:
    """160 аналитических точек: четыре облака выше минимума в 80 окон."""
    centers = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            [6.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
            [9.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        ],
        dtype=np.float64,
    )
    order = np.asarray([2, 0, 3, 1] * 40, dtype=np.int64)
    return centers[order], np.arange(order.size, dtype=np.int64)


def _f10_with_scale(scale: float | None) -> F10Result:
    empty_float = np.empty(0, dtype=np.float64)
    empty_int = np.empty(0, dtype=np.int64)
    return F10Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        scale=scale,
        threshold_sigma=empty_float,
        minimum_duration_s=empty_float,
        quantiles=empty_float,
        occupancy=empty_float,
        episode_count=empty_int,
        total_v2_s=empty_float,
        retained_samples=empty_int,
        truncated_samples=empty_int,
        qualified_samples=empty_int,
        qualified_cycles=0,
        duration_quantile_s=empty_float,
        episode_quantile_v2_s=empty_float,
        quantile_valid=np.empty(0, dtype=np.bool_),
        episodes=(),
        sample_count=4,
        observation_count=4,
        missing_count=0,
        episode_total=0,
        truncated_episode_total=0,
        stored_count=0,
        omitted_count=0,
    )


def _empty_inventory(sample_count: int = 4) -> RootEvents:
    settings = RootEventSettings(
        recipe_sha256="test",
        detector="existing_event_inventory",
        noise_window_samples=2048,
        noise_step_samples=1024,
        minimum_noise_samples=1024,
        threshold_sigma=6.0,
        max_gap_samples=4,
        minimum_event_samples=2,
        minimum_snr_db=12.0,
        minimum_snr_ratio=3.9810717055349722,
        dead_time_s=0.001,
        dead_time_samples=10,
        chunk_samples=4096,
        fft_max_samples=4096,
        clipping_low_v=None,
        clipping_high_v=None,
        clipping_reason_code="not_applicable",
        dead_time_handling="exclude_intervals",
        gap_handling="exclude_crossing_intervals",
    )

    def replay(_: object) -> Iterator[RootTimelineItem]:
        return iter(())

    return RootEvents(
        sample_rate_hz=10.0,
        sample_count=sample_count,
        events=(),
        gaps=(),
        exclusions=(),
        candidate_count=0,
        snr_rejected_count=0,
        accepted_count=0,
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=0,
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=replay,
    )


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=4096,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4096,
        max_surrogates=19,
        deterministic_seed=6022,
    )


def test_missing_f10_scale_is_feature_unavailable() -> None:
    samples = np.asarray([0.0, 1.0, -1.0, 0.0], dtype=np.float64)
    phase = PhaseCycles(
        sample_rate_hz=10.0,
        sample_count=4,
        cycle_start_samples=np.asarray([0.0]),
        cycle_end_samples=np.asarray([4.0]),
        cycle_valid=np.asarray([True], dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
    means = PhaseMeans(
        means_v=np.zeros(1, dtype=np.float64),
        counts=np.asarray([4], dtype=np.int64),
        valid_bins=np.asarray([True], dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )

    result = compute_f15_modes(
        samples,
        phase,
        means,
        _f10_with_scale(None),
        _empty_inventory(),
        (),
        sample_rate_hz=10.0,
        band_filter_order=4,
        settings=F15Settings.locked(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("feature_unavailable",)


def test_even_floor_index_selection_matches_locked_formula() -> None:
    assert tuple(even_floor_indices(10, 4)) == (0, 2, 5, 7)
    assert tuple(even_floor_indices(3, 8)) == (0, 1, 2)


def test_analytic_band_rms_recovers_unity_gain_tone() -> None:
    sample_rate_hz = 128_000.0
    times = np.arange(131_072, dtype=np.float64) / sample_rate_hz
    samples = np.cos(2.0 * np.pi * 24_000.0 * times)
    requested = BandDefinition(
        name="band_0002",
        low=10_000.0,
        high=50_000.0,
        unit=FrequencyUnit.HZ,
        direction=EstimandDirection.DESCRIPTIVE,
    )
    band = ResolvedBand(requested=requested, effective=requested, reason_code=None)

    values = band_window_rms_v(
        samples,
        band,
        np.asarray([25, 26], dtype=np.int64),
        2_560,
        sample_rate_hz=sample_rate_hz,
        filter_order=4,
        resources=_resources(),
    )

    assert values == pytest.approx(np.ones(2), rel=2e-3)


def test_f10_occupancy_uses_passed_scale_and_inclusive_five_sigma_threshold() -> None:
    samples = np.asarray([-1.0, -0.5, 0.5, 1.0], dtype=np.float64)
    phase = PhaseCycles(
        sample_rate_hz=10.0,
        sample_count=4,
        cycle_start_samples=np.asarray([0.0]),
        cycle_end_samples=np.asarray([4.0]),
        cycle_valid=np.asarray([True], dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
    means = PhaseMeans(
        means_v=np.zeros(1, dtype=np.float64),
        counts=np.asarray([4], dtype=np.int64),
        valid_bins=np.asarray([True], dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )

    occupancy = f10_occupancy_5mad(
        samples,
        phase,
        means,
        _f10_with_scale(0.1),
        0,
        4,
        resources=_resources(),
    )

    # Порог равен 0.5, сравнение включительное: подходят все четыре отсчёта.
    assert occupancy == 1.0


def test_locked_f15_settings_and_reason_vocabulary_match_spec() -> None:
    settings = F15Settings.locked()

    assert METHOD == "deterministic_pam_fixed_k_medoids"
    assert settings.window_s == 0.02
    assert settings.overlap_fraction == 0.0
    assert settings.features == FEATURE_NAMES
    assert settings.cluster_count == 4
    assert settings.maximum_swap_passes == 100
    assert settings.stability_blocks == 8
    assert settings.minimum_windows == 80
    assert settings.maximum_labels == 4096
    assert DECLARED_CODES == (
        "empty_cluster",
        "feature_scale_zero",
        "feature_unavailable",
        "insufficient_windows",
        "label_limit",
        "stability_block_too_short",
    )


def test_four_separated_clouds_recover_canonical_medoids() -> None:
    features, indices = _four_mode_features()
    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert np.all(np.ptp(features, axis=0) > 0.0)
    assert 0 <= result.swap_passes <= 100
    assert tuple(result.medoid_indices) == (1, 3, 0, 2)
    assert tuple(result.medoid_rms_v) == (0.0, 3.0, 6.0, 9.0)
    assert tuple(result.labels[:4]) == (2, 0, 3, 1)


def test_zero_mad_feature_is_unavailable_without_scale_substitution() -> None:
    features, indices = _four_mode_features()
    features[:, 6] = 0.25

    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (FEATURE_SCALE_ZERO,)
    assert result.labels.size == 0


def test_fewer_than_locked_minimum_windows_is_unavailable() -> None:
    features, indices = _four_mode_features()
    count = F15Settings.locked().minimum_windows - 1

    result = fit_f15_pam(features[:count], indices[:count], settings=F15Settings.locked())

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (INSUFFICIENT_WINDOWS,)


def test_label_cap_marks_sampled_result_partial() -> None:
    features, _ = _four_mode_features()
    selected = features[[0, 1, 2, 3]]
    indices = np.asarray([0, 1, 3, 4], dtype=np.int64)
    settings = replace(F15Settings.locked(), minimum_windows=4, maximum_labels=4)

    result = fit_f15_pam(
        selected,
        indices,
        settings=settings,
        source_window_count=5,
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (LABEL_LIMIT, STABILITY_BLOCK_TOO_SHORT)
    assert result.stability_ari.size == 0


def test_short_stability_block_returns_partial_without_fake_ari() -> None:
    centres = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            [6.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
            [9.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
        ],
        dtype=np.float64,
    )
    features = centres[np.asarray([0, 1, 2, 3] * 3, dtype=np.int64)]
    settings = replace(F15Settings.locked(), minimum_windows=4)

    result = fit_f15_pam(features, np.arange(12, dtype=np.int64), settings=settings)

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (STABILITY_BLOCK_TOO_SHORT,)
    assert result.stability_ari.size == 0


def test_fewer_than_four_unique_rows_cannot_build_all_medoids() -> None:
    features = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    settings = replace(F15Settings.locked(), minimum_windows=4)

    result = fit_f15_pam(features, np.arange(4, dtype=np.int64), settings=settings)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (EMPTY_CLUSTER,)


def test_all_identical_windows_are_an_empty_cluster() -> None:
    features = np.ones((80, 7), dtype=np.float64)
    indices = np.arange(80, dtype=np.int64)

    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (EMPTY_CLUSTER,)
    assert result.medoid_indices.size == 0


def test_result_rejects_duplicate_reason_codes() -> None:
    features, indices = _four_mode_features()
    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    with pytest.raises(CharacterizationError) as raised:
        replace(result, reason_codes=(LABEL_LIMIT, LABEL_LIMIT))

    assert raised.value.reason_code == "status_invariant"


def test_available_result_rejects_nonempty_reasons() -> None:
    features, indices = _four_mode_features()
    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    with pytest.raises(CharacterizationError) as raised:
        replace(result, reason_codes=(LABEL_LIMIT,))

    assert raised.value.reason_code == "status_invariant"


def test_result_publishes_feature_standardization_and_real_medoids() -> None:
    features, indices = _four_mode_features()

    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    assert result.feature_names == FEATURE_NAMES
    assert np.array_equal(result.window_indices, indices)
    assert np.array_equal(result.feature_medians, np.asarray([4.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5]))
    assert np.array_equal(result.feature_mads, np.asarray([3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]))
    assert result.standardized_features.shape == (160, 7)
    assert np.array_equal(result.medoid_features, features[[1, 3, 0, 2]])


def test_dwell_runs_and_transition_counts_are_exact() -> None:
    features, indices = _four_mode_features()

    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    assert result.dwell_labels.shape == (160,)
    assert np.all(result.dwell_durations_s == 0.02)
    expected_counts = np.asarray(
        [
            [0, 0, 0, 40],
            [0, 0, 39, 0],
            [40, 0, 0, 0],
            [0, 40, 0, 0],
        ],
        dtype=np.int64,
    )
    assert np.array_equal(result.transition_counts, expected_counts)
    expected_probabilities = expected_counts.astype(np.float64) / np.sum(
        expected_counts, axis=1, keepdims=True
    )
    assert np.array_equal(result.transition_probabilities, expected_probabilities)


def test_eight_descending_blocks_refit_with_adjusted_rand_index_one() -> None:
    features, indices = _four_mode_features()

    result = fit_f15_pam(features, indices, settings=F15Settings.locked())

    assert result.stability_ari.shape == (8,)
    assert np.array_equal(result.stability_ari, np.ones(8, dtype=np.float64))


def test_equal_medoid_rms_is_ordered_by_lowest_window_index() -> None:
    centres = np.asarray(
        [
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [1.0, 3.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            [1.0, 0.0, 3.0, 2.0, 2.0, 2.0, 2.0],
            [1.0, 1.0, 0.0, 3.0, 3.0, 3.0, 3.0],
        ],
        dtype=np.float64,
    )
    order = np.asarray([2, 0, 3, 1] * 40, dtype=np.int64)
    features = centres[order]
    for group in range(4):
        positions = np.flatnonzero(order == group)
        features[positions[-20:], 0] = 5.0

    result = fit_f15_pam(
        features,
        np.arange(order.size, dtype=np.int64),
        settings=F15Settings.locked(),
    )

    expected = np.lexsort((result.medoid_indices, result.medoid_rms_v))
    assert np.array_equal(result.medoid_indices, result.medoid_indices[expected])


def test_repeated_fit_is_bitwise_identical_without_rng() -> None:
    features, indices = _four_mode_features()

    first = fit_f15_pam(features, indices, settings=F15Settings.locked())
    second = fit_f15_pam(features, indices, settings=F15Settings.locked())

    def fingerprint(result: F15Result) -> tuple[bytes, ...]:
        return tuple(
            array.tobytes()
            for array in (
                result.feature_medians,
                result.feature_mads,
                result.standardized_features,
                result.window_indices,
                result.medoid_indices,
                result.medoid_features,
                result.medoid_rms_v,
                result.labels,
                result.dwell_labels,
                result.dwell_durations_s,
                result.transition_counts,
                result.transition_probabilities,
                result.stability_ari,
            )
        )

    assert fingerprint(first) == fingerprint(second)


def test_pam_build_breaks_equal_farthest_distances_by_lowest_index() -> None:
    standardized = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [-6.0, 1.0, 0.0, -1.0, 0.0, 1.0, 0.0],
            [6.0, -1.0, 0.0, 1.0, 0.0, -1.0, 0.0],
            [-2.0, 1.0, 0.0, -1.0, 0.0, 1.0, 0.0],
            [2.0, -1.0, 0.0, 1.0, 0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )

    assert pam_build_indices(standardized, cluster_count=4) == (0, 1, 2, 3)


def test_pam_swap_replaces_noncentral_medoid_with_lowest_index() -> None:
    # В каждом облаке десять центральных и две крайние точки. Начальный крайний
    # медиоид стоит 10·2²; замена индекса 11 на 0 снижает стоимость до 2·2².
    standardized = np.concatenate(
        (
            np.concatenate((np.zeros(10), np.full(2, 2.0))),
            np.concatenate((np.full(10, 10.0), np.full(2, 12.0))),
        )
    )[:, None]
    initial = (11, 23)

    medoids, passes = pam_swap_indices(standardized, initial, maximum_passes=100)

    assert medoids == (0, 23)
    assert passes == 1


def test_adjusted_rand_index_matches_hand_counted_negative_value() -> None:
    # C(4,2)=6; внутри каждого разбиения по 2 пары, совместных пар нет.
    # ARI = (0 - 2*2/6) / ((2+2)/2 - 2*2/6) = -1/2.
    first = np.asarray([0, 0, 1, 1], dtype=np.int64)
    second = np.asarray([0, 1, 0, 1], dtype=np.int64)

    assert adjusted_rand_index(first, second) == -0.5
