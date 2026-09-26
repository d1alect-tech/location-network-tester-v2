from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lnt.analysis_store import CharacterizationRecipe, RecipeError, parse_analysis_recipe
from lnt.analysis_v2.recipes import RecipeCatalog
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.context.json_codec import JsonValue


_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"


def _mapping() -> dict[str, JsonValue]:
    return decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")


def test_characterization_example_round_trips_through_public_parser() -> None:
    mapping = _mapping()

    recipe = parse_analysis_recipe(mapping)

    assert isinstance(recipe, CharacterizationRecipe)
    assert recipe.to_mapping() == mapping
    assert recipe.recipe_sha256 == (
        "b4b3b66c7a23aeca8cc48db263537f7313f9f70d67502c95084e2677cd9db3f8"
    )
    assert tuple(family.id for family in recipe.families) == (
        "f01_phase_cycle",
        "f02_amplitude_time_shape",
        "f03_interharmonic_tracking",
        "f04_multicycle_periodicity",
        "f05_phase_conditioned_statistics",
        "f06_modulation_trajectories",
        "f07_comb_sideband_cepstrum",
        "f08_transient_morphology",
        "f09_event_ordering",
        "f10_threshold_episode_surface",
        "f11_conditional_distributions",
        "f12_spectral_kurtosis",
        "f13_band_envelope_coactivity",
        "f14_cross_channel_event_association",
        "f15_interpretable_modes",
        "f16_multiscale_memory",
        "f17_cyclic_spectral_coherence",
        "f18_bicoherence_triads",
    )


def test_characterization_canonical_hash_ignores_object_key_order() -> None:
    mapping = _mapping()
    reversed_mapping = dict(reversed(tuple(mapping.items())))
    phase = mapping["phase"]
    assert isinstance(phase, dict)
    reversed_mapping["phase"] = dict(reversed(tuple(phase.items())))

    assert (
        parse_analysis_recipe(mapping).canonical_json
        == parse_analysis_recipe(reversed_mapping).canonical_json
    )


def test_ch1_only_recipe_preserves_unavailable_ch2_phase_reference() -> None:
    mapping = _mapping()
    mapping["channels"] = ["ch1"]

    recipe = parse_analysis_recipe(mapping)

    assert isinstance(recipe, CharacterizationRecipe)
    assert recipe.channels == ("ch1",)
    assert recipe.phase.reference_channel == "ch2"


@pytest.mark.parametrize("channels", [("ch1", "ch1"), ("ch3",)])
def test_characterization_rejects_duplicate_or_unknown_channels(channels: tuple[str, ...]) -> None:
    mapping = _mapping()
    mapping["channels"] = list(channels)

    with pytest.raises(RecipeError):
        parse_analysis_recipe(mapping)


def _missing_family(mapping: dict[str, JsonValue]) -> None:
    families = mapping["families"]
    assert isinstance(families, list)
    families.pop()


def _duplicate_family(mapping: dict[str, JsonValue]) -> None:
    families = mapping["families"]
    assert isinstance(families, list)
    families[1] = families[0]


def _rename_family(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 0)["id"] = "f01_renamed"


def _enable_family(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 0)["enabled"] = True


def _invalid_method(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 0)["method"] = "other"


def _invalid_method_version(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 0)["method_version"] = 2


def _floating_method_version(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 0)["method_version"] = 1.0


def _invalid_enum(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 5)["filter"] = "fir"


def _non_finite(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 0)["window_s"] = math.inf


def _invalid_bands(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 10)["bands_hz"] = [[3000.0, 10000.0], [9000.0, 50000.0]]


def _invalid_grid(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 9)["threshold_sigma"] = [3.0, 3.0]


def _invalid_support(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 10)["minimum_support"] = 0


def _resource_over_cap(mapping: dict[str, JsonValue]) -> None:
    resources = mapping["resource_limits"]
    assert isinstance(resources, dict)
    resources["max_work_bytes"] = 268435457


def _family_cap_over_resource(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 5)["maximum_stored_samples"] = 4097


def _surrogate_total_over_resource(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 17)["iaaft_surrogate_count"] = 101


def _inconsistent_f11_f15(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 10)["mode_count"] = 3


def _invalid_f02_source(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 1)["template_family_id"] = "f03_interharmonic_tracking"


def _invalid_f04_source(mapping: dict[str, JsonValue]) -> None:
    _family(mapping, 3)["carrier_source_family_id"] = "f05_phase_conditioned_statistics"


def _family(mapping: dict[str, JsonValue], index: int) -> dict[str, JsonValue]:
    families = mapping["families"]
    assert isinstance(families, list)
    family = families[index]
    assert isinstance(family, dict)
    return family


def _set_family(index: int, field: str, value: JsonValue) -> Callable[[dict[str, JsonValue]], None]:
    def mutate(mapping: dict[str, JsonValue]) -> None:
        _family(mapping, index)[field] = value

    return mutate


def _set_root_group(
    group: str, field: str, value: JsonValue
) -> Callable[[dict[str, JsonValue]], None]:
    def mutate(mapping: dict[str, JsonValue]) -> None:
        settings = mapping[group]
        assert isinstance(settings, dict)
        settings[field] = value

    return mutate


@pytest.mark.parametrize(
    "mutate",
    [
        _set_family(0, "window_s", 0.0),
        _set_family(0, "cycles_per_window", 0),
        _set_family(0, "phase_resultant_min", 1.1),
        _set_family(2, "detection_margin_db", 0.0),
        _set_family(5, "band_low_hz", 50000.0),
        _set_family(5, "filter_order", 0),
        _set_family(6, "fft_samples", 0),
        _set_family(6, "log_floor_db_below_maximum", 0.0),
        _set_family(11, "segment_samples", [256, 0, 4096]),
        _set_family(11, "minimum_frames", 0),
        _set_family(11, "surrogate_count", 0),
        _set_family(12, "lag_high_s", -0.03),
        _set_family(13, "trigger_window_high_s", -0.03),
        _set_family(14, "cluster_count", 0),
        _set_family(14, "stability_blocks", 0),
        _set_family(16, "segment_samples", 0),
        _set_family(16, "minimum_frames", 0),
        _set_family(16, "surrogate_count", 0),
        _set_family(17, "segment_samples", 0),
        _set_family(17, "minimum_frames", 0),
        _set_family(17, "phase_randomized_surrogate_count", 0),
        _set_family(17, "iaaft_iterations", 0),
        _set_family(17, "iaaft_relative_rms_magnitude_tolerance", 0.0),
        _set_root_group("phase", "phase_bins", 0),
        _set_family(4, "phase_bins", 32),
    ],
)
def test_explicit_family_shapes_reject_invalid_values(
    mutate: Callable[[dict[str, JsonValue]], None],
) -> None:
    mapping = _mapping()
    mutate(mapping)

    with pytest.raises(RecipeError):
        parse_analysis_recipe(mapping)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            _set_family(3, "maximum_averaging_fraction_of_record", 1.0),
            id="f04-method-v1-averaging-fraction",
        ),
        pytest.param(
            _set_family(5, "phase_increment_max_rad", 4.0),
            id="f06-itoh-maximum",
        ),
        pytest.param(
            _set_family(9, "threshold_sigma", list(range(1, 34))),
            id="f10-threshold-axis-hard-maximum",
        ),
        pytest.param(
            _set_family(9, "threshold_sigma", [3.0, 4.0, 8.0, 12.0]),
            id="f10-method-v1-threshold-grid",
        ),
        pytest.param(
            _set_family(10, "cdf_points", 1_000_000_000),
            id="f11-method-v1-cdf-points",
        ),
        pytest.param(_floating_method_version, id="method-version-must-be-integer"),
    ],
)
def test_unsupported_family_parameter_values_fail_closed(
    mutate: Callable[[dict[str, JsonValue]], None],
) -> None:
    mapping = _mapping()
    mutate(mapping)

    with pytest.raises(RecipeError):
        parse_analysis_recipe(mapping)


@pytest.mark.parametrize(
    "mutate",
    [
        _missing_family,
        _duplicate_family,
        _rename_family,
        _enable_family,
        _invalid_method,
        _invalid_method_version,
        _invalid_enum,
        _non_finite,
        _invalid_bands,
        _invalid_grid,
        _invalid_support,
        _resource_over_cap,
        _family_cap_over_resource,
        _surrogate_total_over_resource,
        _inconsistent_f11_f15,
        _invalid_f02_source,
        _invalid_f04_source,
    ],
)
def test_malformed_characterization_recipe_fails_closed(
    mutate: Callable[[dict[str, JsonValue]], None],
) -> None:
    mapping = _mapping()
    mutate(mapping)

    with pytest.raises(RecipeError):
        parse_analysis_recipe(mapping)


@pytest.mark.parametrize("version", [None, True, 0, 3, "2"])
def test_dispatcher_rejects_unsupported_schema_version(version: JsonValue) -> None:
    mapping = _mapping()
    mapping["schema_version"] = version

    with pytest.raises(RecipeError):
        parse_analysis_recipe(mapping)


def test_catalog_round_trips_v2_and_rejects_clone_without_side_effect(tmp_path: Path) -> None:
    recipe = parse_analysis_recipe(_mapping())
    catalog = RecipeCatalog(tmp_path / "recipes")

    created = catalog.create("characterization", recipe)
    before = catalog.list()

    with pytest.raises(RecipeError, match="schema_version=2"):
        catalog.clone(created.recipe_id, "copy")

    assert catalog.get(created.recipe_id).recipe == recipe
    assert catalog.list() == before
