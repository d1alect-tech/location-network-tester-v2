from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization.clipping import ClippingBounds
from lnt.characterization.events import compute_root_events
from lnt.characterization.records import Status
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RATE_HZ = 100_000.0


def _recipe(
    *,
    maximum_events: int = 4096,
    threshold_sigma: float = 5.0,
    minimum_snr_db: float = 10.0,
    dead_time_s: float = 0.0001,
    chunk_samples: int = 4096,
    max_work_bytes: int | None = None,
    max_stored_trajectories: int = 4096,
) -> CharacterizationRecipe:
    raw = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    resources = cast("dict[str, JsonValue]", raw["resource_limits"])
    resources["chunk_samples"] = chunk_samples
    resources["max_stored_trajectories"] = max_stored_trajectories
    if max_work_bytes is not None:
        resources["max_work_bytes"] = max_work_bytes
    event_settings = cast("dict[str, JsonValue]", raw["events"])
    event_settings.update(
        maximum_events=maximum_events,
        threshold_sigma=threshold_sigma,
        minimum_snr_db=minimum_snr_db,
        dead_time_s=dead_time_s,
    )
    for family in cast("list[JsonValue]", raw["families"]):
        family_map = cast("dict[str, JsonValue]", family)
        if family_map["id"] in {
            "f02_amplitude_time_shape",
            "f08_transient_morphology",
            "f09_event_ordering",
            "f11_conditional_distributions",
        }:
            family_map["maximum_events"] = maximum_events
        for name in (
            "maximum_tracks",
            "maximum_stored_samples",
            "maximum_episodes",
            "maximum_stored_bins",
            "maximum_lag_points",
            "maximum_triggers_per_direction",
            "maximum_labels",
            "maximum_triads",
            "maximum_stored_cells",
        ):
            if name in family_map:
                family_map[name] = min(cast("int", family_map[name]), max_stored_trajectories)
    recipe = parse_analysis_recipe(raw)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _signal(sample_count: int) -> np.ndarray:
    return np.resize(np.array([-0.01, 0.0, 0.01]), sample_count).astype(np.float64)


def _bounds(
    low_v: float | None = -0.5,
    high_v: float | None = 0.5,
    reason_code: str | None = None,
) -> ClippingBounds:
    return ClippingBounds(
        low_v=low_v,
        high_v=high_v,
        reason_code=reason_code,
        telemetry_rail_count=None,
    )


def test_root_streams_to_eof_with_bounded_retention_and_uncapped_replay() -> None:
    samples = _signal(24_000)
    peaks = [2_000, 6_000, 10_000, 14_000, 18_000]
    samples[peaks] = [0.20, -0.22, 0.24, -0.26, 0.28]

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(maximum_events=2),
        clipping=_bounds(),
    )

    assert [event.peak_sample for event in root.events] == peaks[:2]
    assert [event.ordinal for event in root.events] == [1, 2]
    assert (root.candidate_count, root.accepted_count, root.omitted_count) == (5, 5, 3)
    assert root.selection_rule == "first_by_peak_sample"
    assert root.retained_candidates_complete is False
    assert root.status is Status.PARTIAL
    assert "event_retention_limit" in root.reason_codes
    replayed = tuple(root.replay())
    assert [item.event.peak_sample for item in replayed if item.kind == "event"] == peaks
    assert [item.event.ordinal for item in replayed if item.kind == "event"] == [1, 2, 3, 4, 5]


def test_snr_gate_is_inclusive_at_exact_recipe_ratio() -> None:
    samples = _signal(16_000)
    sigma_v = 1.4826 * 0.01
    samples[5_000] = 5.0 * sigma_v
    samples[10_000] = 4.9 * sigma_v
    minimum_db = 20.0 * math.log10(5.0)

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(threshold_sigma=4.0, minimum_snr_db=minimum_db),
        clipping=_bounds(),
    )

    assert root.candidate_count == 2
    assert root.accepted_count == 1
    assert root.events[0].peak_sample == 5_000
    assert root.events[0].snr_ratio == pytest.approx(5.0)
    assert root.settings.minimum_snr_ratio == pytest.approx(5.0)


def test_dead_time_is_nonparalyzable_and_exclusions_are_explicit() -> None:
    samples = _signal(12_000)
    samples[[5_000, 5_012, 5_024, 5_040]] = 0.3

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(dead_time_s=0.0003),
        clipping=_bounds(),
    )

    assert [event.peak_sample for event in root.events] == [5_000, 5_040]
    assert root.dead_time_rejected_count == 2
    excluded = [
        (item.candidate.peak_sample, item.blocked_by_event_ordinal) for item in root.exclusions
    ]
    assert excluded == [
        (5_012, 1),
        (5_024, 1),
    ]
    assert all(item.end_sample == 5_029 for item in root.exclusions)


def test_nonfinite_gap_is_never_bridged_and_replay_keeps_timeline_ordinals() -> None:
    samples = _signal(12_000)
    samples[[5_998, 6_002]] = [0.3, -0.3]
    samples[6_000:6_002] = np.nan

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(dead_time_s=1 / _RATE_HZ),
        clipping=_bounds(),
    )

    replayed = tuple(root.replay())
    assert [item.kind for item in replayed] == ["event", "gap", "event"]
    assert [(gap.start_sample, gap.end_sample) for gap in root.gaps] == [(6_000, 6_001)]
    assert [event.ordinal for event in root.events] == [1, 2]
    assert root.gap_count == 1


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        (_bounds(), True),
        (_bounds(None, None, "clipping_localization_unavailable"), None),
        (_bounds(None, None, "not_applicable_synthetic"), False),
    ],
)
def test_clipping_is_tri_state_without_changing_saved_volts(
    bounds: ClippingBounds, expected: bool | None
) -> None:
    samples = _signal(8_000)
    samples[4_000] = 0.5
    original = samples.copy()

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(),
        clipping=bounds,
    )

    assert root.events[0].clipped is expected
    assert root.events[0].peak_value_v == 0.5
    assert np.array_equal(samples, original)


def test_dominant_band_does_not_depend_on_clipping_localization() -> None:
    samples = _signal(12_000)
    start, length = 5_000, 200
    time_s = np.arange(length, dtype=np.float64) / _RATE_HZ
    samples[start : start + length] += 0.3 * np.sin(2.0 * np.pi * 5_000.0 * time_s)

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(),
        clipping=_bounds(None, None, "clipping_localization_unavailable"),
    )

    assert len(root.events) == 1
    assert root.events[0].dominant_band == "band_0001"
    assert root.events[0].dominant_band_reason_code is None
    assert root.events[0].clipped is None


@pytest.mark.parametrize(
    ("bounds", "expected_clipped"),
    [
        (_bounds(None, None, "not_applicable_synthetic"), False),
        (_bounds(None, None, "clipping_localization_unavailable"), None),
    ],
)
def test_known_5khz_band_is_independent_of_clipping_metadata(
    bounds: ClippingBounds, expected_clipped: bool | None
) -> None:
    samples = _signal(10_000)
    time_s = np.arange(200, dtype=np.float64) / _RATE_HZ
    samples[4_900:5_100] += 0.3 * np.sin(2.0 * np.pi * 5_000.0 * time_s)

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(),
        clipping=bounds,
    )

    assert len(root.events) == 1
    assert root.events[0].dominant_band == "band_0001"
    assert root.events[0].dominant_band_reason_code is None
    assert root.events[0].clipped is expected_clipped


def test_long_event_has_no_decimated_frequency_and_casts_only_bounded_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples = _signal(90_000)
    samples[np.arange(5_000, 75_001, 9)] = 0.3
    cast_sizes: list[int] = []
    real_asarray = np.asarray

    def tracked_asarray(
        value: np.ndarray,
        dtype: type[np.float64] | np.dtype[np.float64] | None = None,
    ) -> np.ndarray:
        result = real_asarray(value, dtype=dtype)
        cast_sizes.append(int(result.size))
        return result

    monkeypatch.setattr(np, "asarray", tracked_asarray)
    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(chunk_samples=4096),
        clipping=_bounds(),
    )

    event = root.events[0]
    assert event.end_sample - event.start_sample + 1 > root.settings.fft_max_samples
    assert event.dominant_band is None
    assert event.dominant_band_reason_code == "event_exceeds_fft_max_samples"
    assert max(cast_sizes) <= 4096
    assert event.v2_s > event.excess_v2_s > 0.0


def test_too_small_work_budget_reports_unavailable_without_scanning() -> None:
    root = compute_root_events(
        _signal(8_000),
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(max_work_bytes=32_000),
        clipping=_bounds(),
    )

    assert root.status is Status.UNAVAILABLE
    assert root.reason_codes == ("event_detector_work_budget_too_small",)
    assert root.events == ()
    assert tuple(root.replay()) == ()


def test_accounting_prefixes_honor_recipe_storage_cap() -> None:
    samples = _signal(80_000)
    samples[np.arange(5_000, 70_000, 1_000)] = np.nan

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(maximum_events=2, max_stored_trajectories=64),
        clipping=_bounds(),
    )

    assert root.gap_count == 65
    assert len(root.gaps) == 64
    assert root.omitted_gap_count == 1
    assert "gap_retention_limit" in root.reason_codes


def test_too_small_budget_still_checks_cancellation_for_compute_and_replay() -> None:
    error = RuntimeError("cancel unsupported work")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        compute_root_events(
            _signal(8_000),
            sample_rate_hz=_RATE_HZ,
            recipe=_recipe(max_work_bytes=32_000),
            clipping=_bounds(),
            checkpoint=cancel,
        )
    assert caught.value is error

    root = compute_root_events(
        _signal(8_000),
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(max_work_bytes=32_000),
        clipping=_bounds(),
    )
    with pytest.raises(RuntimeError) as replay_caught:
        next(root.replay(checkpoint=cancel))
    assert replay_caught.value is error


def test_checkpoint_exceptions_propagate_by_identity_for_compute_and_replay() -> None:
    samples = _signal(8_000)
    samples[4_000] = 0.3
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        compute_root_events(
            samples,
            sample_rate_hz=_RATE_HZ,
            recipe=_recipe(),
            clipping=_bounds(),
            checkpoint=cancel,
        )
    assert caught.value is error

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=_recipe(),
        clipping=_bounds(),
    )
    with pytest.raises(RuntimeError) as replay_caught:
        next(root.replay(checkpoint=cancel))
    assert replay_caught.value is error


def test_settings_provenance_is_explicit_and_json_stable() -> None:
    samples = _signal(8_000)
    samples[4_000] = 0.3
    recipe = _recipe(chunk_samples=2048)

    root = compute_root_events(
        samples,
        sample_rate_hz=_RATE_HZ,
        recipe=recipe,
        clipping=_bounds(),
    )

    assert root.settings.recipe_sha256 == recipe.recipe_sha256
    assert root.settings.noise_window_samples == 4001
    assert root.settings.noise_step_samples == 256
    assert root.settings.minimum_noise_samples == 2000
    assert root.settings.max_gap_samples == 8
    assert root.settings.minimum_event_samples == 1
    assert root.settings.chunk_samples == 2048
    assert json.loads(json.dumps(root.settings.to_dict()))["recipe_sha256"] == recipe.recipe_sha256
