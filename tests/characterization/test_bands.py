from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization.bands import band_index, resolve_characterization_bands
from lnt.context.json_codec import decode_object
from lnt.errors import InputError
from lnt.features.bands import EstimandDirection, FrequencyUnit

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"


def _mapping() -> dict[str, JsonValue]:
    return decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")


def _recipe(
    *,
    bands: list[list[float]] | None = None,
    nyquist_fraction_max: float | None = None,
) -> CharacterizationRecipe:
    mapping = _mapping()
    families = mapping["families"]
    assert isinstance(families, list)
    if bands is not None:
        for index in (10, 12):
            family = families[index]
            assert isinstance(family, dict)
            family["bands_hz"] = cast("JsonValue", bands)
    if nyquist_fraction_max is not None:
        stft = mapping["stft"]
        assert isinstance(stft, dict)
        stft["nyquist_fraction_max"] = nyquist_fraction_max
        for index in (11, 16, 17):
            family = families[index]
            assert isinstance(family, dict)
            family["nyquist_fraction_max"] = nyquist_fraction_max
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def test_resolver_preserves_declared_f13_bands_and_identity() -> None:
    recipe = _recipe()
    before = recipe.to_mapping()

    resolved = resolve_characterization_bands(recipe, 1_000_000.0)

    assert tuple((item.requested.low, item.requested.high) for item in resolved) == (
        (3_000.0, 10_000.0),
        (10_000.0, 50_000.0),
        (50_000.0, 200_000.0),
    )
    assert tuple(item.requested.name for item in resolved) == (
        "band_0001",
        "band_0002",
        "band_0003",
    )
    assert all(item.requested.unit is FrequencyUnit.HZ for item in resolved)
    assert all(item.requested.direction is EstimandDirection.DESCRIPTIVE for item in resolved)
    assert all(item.effective == item.requested for item in resolved)
    assert all(item.reason_code is None for item in resolved)
    assert resolve_characterization_bands(recipe, 1_000_000.0) == resolved
    assert recipe.to_mapping() == before


@pytest.mark.parametrize(
    ("frequency_hz", "expected"),
    [
        (math.nextafter(3_000.0, -math.inf), None),
        (3_000.0, 0),
        (math.nextafter(3_000.0, math.inf), 0),
        (math.nextafter(10_000.0, -math.inf), 0),
        (10_000.0, 1),
        (math.nextafter(10_000.0, math.inf), 1),
        (math.nextafter(50_000.0, -math.inf), 1),
        (50_000.0, 2),
        (math.nextafter(50_000.0, math.inf), 2),
        (math.nextafter(200_000.0, -math.inf), 2),
        (200_000.0, 2),
        (math.nextafter(200_000.0, math.inf), None),
    ],
)
def test_band_index_uses_declared_boundary_rule(frequency_hz: float, expected: int | None) -> None:
    bands = resolve_characterization_bands(_recipe(), 1_000_000.0)

    assert band_index(frequency_hz, bands) == expected


def test_low_sample_rate_keeps_requested_band_and_clamps_effective_high() -> None:
    resolved = resolve_characterization_bands(_recipe(), 200_000.0)

    upper = resolved[2]
    assert (upper.requested.low_hz, upper.requested.high_hz) == (50_000.0, 200_000.0)
    assert upper.effective is not None
    assert (upper.effective.low_hz, upper.effective.high_hz) == (50_000.0, 90_000.0)
    assert upper.effective.name == upper.requested.name
    assert upper.reason_code is None
    assert band_index(90_000.0, resolved) == 2
    assert band_index(math.nextafter(90_000.0, math.inf), resolved) is None


def test_resolver_uses_recipe_nyquist_fraction() -> None:
    resolved = resolve_characterization_bands(
        _recipe(nyquist_fraction_max=0.4),
        200_000.0,
    )

    assert resolved[2].effective is not None
    assert resolved[2].effective.high_hz == 80_000.0


def test_unsupported_last_band_does_not_close_or_absorb_the_supported_interval() -> None:
    resolved = resolve_characterization_bands(_recipe(), 100_000.0)

    assert resolved[1].effective is not None
    assert resolved[1].effective.high_hz == 45_000.0
    assert resolved[2].effective is None
    assert resolved[2].reason_code == "band_above_nyquist"
    assert band_index(math.nextafter(45_000.0, -math.inf), resolved) == 1
    assert band_index(45_000.0, resolved) is None
    assert band_index(50_000.0, resolved) is None


def test_disjoint_valid_recipe_preserves_gaps_and_original_indices() -> None:
    recipe = _recipe(bands=[[3_000.0, 10_000.0], [20_000.0, 50_000.0], [80_000.0, 200_000.0]])

    resolved = resolve_characterization_bands(recipe, 1_000_000.0)

    assert tuple((item.requested.low_hz, item.requested.high_hz) for item in resolved) == (
        (3_000.0, 10_000.0),
        (20_000.0, 50_000.0),
        (80_000.0, 200_000.0),
    )
    assert band_index(15_000.0, resolved) is None
    assert band_index(20_000.0, resolved) == 1
    assert band_index(60_000.0, resolved) is None
    assert band_index(80_000.0, resolved) == 2


@pytest.mark.parametrize("sample_rate_hz", [0.0, -1.0, math.inf, -math.inf, math.nan])
def test_resolver_rejects_nonpositive_or_nonfinite_sample_rate(sample_rate_hz: float) -> None:
    with pytest.raises(InputError):
        resolve_characterization_bands(_recipe(), sample_rate_hz)
