from __future__ import annotations

import math
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING

import pytest

from lnt.analysis_store import AnalysisRecipe, RecipeError

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue


def _recipe_mapping() -> dict[str, JsonValue]:
    return {
        "schema_version": 1,
        "mode": "standard",
        "channels": ["ch1", "ch2"],
        "band_grid": {"low_hz": 3000.0, "high_hz": 200000.0, "grid_hz": 50.0},
        "welch": {
            "window": "hann",
            "segment_samples": 4096,
            "overlap_fraction": 0.5,
            "detrend": "constant",
            "scaling": "density",
            "average": "mean",
        },
        "spectrogram": {"enabled": True, "segment_samples": 1024, "overlap_fraction": 0.25},
        "events": {"enabled": True, "threshold_sigma": 5.0},
        "bands": {"edges_hz": [3000.0, 10000.0, 200000.0]},
        "correction": {"method": "none"},
        "uncertainty": {"enabled": False, "confidence_level": 0.95, "bootstrap_samples": 0},
    }


def test_equivalent_mapping_order_has_same_recipe_hash() -> None:
    given = _recipe_mapping()
    reversed_mapping = dict(reversed(list(given.items())))

    first = AnalysisRecipe.from_mapping(given)
    second = AnalysisRecipe.from_mapping(reversed_mapping)

    assert first.canonical_json == second.canonical_json
    assert first.recipe_sha256 == second.recipe_sha256


def test_clone_on_edit_returns_new_recipe_and_preserves_original() -> None:
    original = AnalysisRecipe.from_mapping(_recipe_mapping())

    changed = original.clone(mode="line_quality")

    assert changed is not original
    assert original.mode == "standard"
    assert changed.mode == "line_quality"
    assert changed.recipe_sha256 != original.recipe_sha256
    with pytest.raises(FrozenInstanceError):
        AnalysisRecipe.__setattr__(original, "mode", "mutated")


@pytest.mark.parametrize(
    ("path", "value"),
    [("unknown", 1), ("band_grid", {"low_hz": 1.0, "high_hz": 2.0, "grid_hz": 1.0, "x": 1})],
)
def test_unknown_fields_are_rejected(path: str, value: object) -> None:
    mapping = _recipe_mapping()
    if isinstance(value, int | str | float | bool | list | dict) or value is None:
        mapping[path] = value

    with pytest.raises(RecipeError):
        AnalysisRecipe.from_mapping(mapping)


def test_non_finite_number_is_rejected() -> None:
    mapping = _recipe_mapping()
    mapping["events"] = {"enabled": True, "threshold_sigma": math.nan}

    with pytest.raises(RecipeError):
        AnalysisRecipe.from_mapping(mapping)
