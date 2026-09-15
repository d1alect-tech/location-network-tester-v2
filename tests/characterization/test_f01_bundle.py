"""F01 bundle assembly: F01 outputs plus seventeen not_computed placeholders."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import (
    FAMILY_IDS,
    CharacterizationBundle,
    CharacterizationError,
    Status,
    TableBlock,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f01_bundle import build_f01_bundle
from lnt.characterization.f01_phase_cycle import METHOD, F01Result, compute_f01_phase_cycle
from lnt.context.json_codec import decode_object

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 8000.0

type Float64Array = NDArray[np.float64]


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _synthetic(duration_s: float = 2.4) -> Float64Array:
    # Full 40-harmonic comb: every order carries energy so all
    # phase resultants stay at 1.0 and the outcome is AVAILABLE.
    n = round(_FS_HZ * duration_s)
    t = np.arange(n, dtype=np.float64) / _FS_HZ
    signal = np.zeros(n, dtype=np.float64)
    for order in range(1, 41):
        signal += (6.0 / order) * np.sin(2.0 * np.pi * 50.0 * order * t)
    return signal


def _available_result() -> F01Result:
    signal = _synthetic()
    result = compute_f01_phase_cycle(signal, sample_rate_hz=_FS_HZ, sync_reference=signal)
    assert result.status is Status.AVAILABLE
    return result


def test_bundle_has_exactly_eighteen_ordered_families() -> None:
    bundle, _, _ = build_f01_bundle(_available_result(), _recipe())
    assert tuple(family.family_id for family in bundle.families) == FAMILY_IDS
    assert bundle.families[0].signal_plane == "ch1_scope_input"


def test_measured_channel_selects_signal_plane() -> None:
    bundle, _, _ = build_f01_bundle(_available_result(), _recipe(), measured_channel="ch2")
    assert bundle.families[0].signal_plane == "ch2_transformer_secondary"


def test_f01_available_maps_quantities_to_outputs() -> None:
    result = _available_result()
    bundle, arrays, tables = build_f01_bundle(result, _recipe())
    family = bundle.families[0]
    assert family.status is Status.AVAILABLE
    assert family.reason_codes == ()
    assert (family.method, family.method_version) == (METHOD, 1)
    assert family.comparison_summary[0].name == "f1_hz"
    assert family.comparison_summary[0].value == pytest.approx(50.0, abs=0.5)
    assert set(arrays) == {"f01_c_k_v", "f01_phi_rel_k_rad", "f01_x_template_v"}
    assert arrays["f01_c_k_v"].dtype.name == "complex128"
    assert arrays["f01_c_k_v"].shape == (40,)
    assert arrays["f01_x_template_v"].shape == (1000,)
    assert result.c_k_v is not None
    assert result.phi_rel_k_rad is not None
    assert np.array_equal(arrays["f01_c_k_v"], result.c_k_v)
    assert np.array_equal(arrays["f01_phi_rel_k_rad"], result.phi_rel_k_rad)
    table = tables["f01_harmonics"]
    assert table.row_count == 40
    assert table.rows[0][0] == 1
    assert table.rows[0][1] == pytest.approx(6.0, rel=0.01)
    assert table.rows[2][1] == pytest.approx(2.0, rel=0.01)


def test_placeholders_use_recipe_methods_without_outputs() -> None:
    recipe = _recipe()
    expected = {family.id: (family.method, family.method_version) for family in recipe.families}
    bundle, _, tables = build_f01_bundle(_available_result(), recipe)
    assert bundle.families[0].family_id == "f01_phase_cycle"
    for family in bundle.families[1:]:
        assert family.status is Status.UNAVAILABLE
        assert family.reason_codes == ("not_computed",)
        assert (family.method, family.method_version) == expected[family.family_id]
        assert family.array_refs == ()
        assert family.table_refs == ()
        assert family.comparison_summary == ()
    assert expected["f02_amplitude_time_shape"][0] == "template_gain_delay_least_squares"
    assert set(tables) == {"f01_harmonics"}
    assert "f01_harmonics" not in {
        reference.table_id for family in bundle.families[1:] for reference in family.table_refs
    }


def test_round_trip_through_bundle_codec() -> None:
    recipe = _recipe()
    bundle, arrays, tables = build_f01_bundle(_available_result(), recipe)
    files = encode_bundle(
        bundle, arrays, tables, max_artifact_bytes=recipe.resource_limits.max_artifact_bytes
    )
    assert tuple(files) == (
        "characterization.json",
        "characterization-arrays.npz",
        "characterization-tables.json",
    )
    loaded = load_bundle(files)
    assert loaded.bundle == bundle
    assert set(loaded.arrays) == set(arrays)
    assert loaded.tables == tables
    assert isinstance(bundle, CharacterizationBundle)
    assert isinstance(next(iter(tables.values())), TableBlock)


def test_partial_f01_carries_codes_masks_and_outputs() -> None:
    result = dataclasses.replace(
        _available_result(), status=Status.PARTIAL, reason_codes=("phase_unstable",)
    )
    bundle, arrays, tables = build_f01_bundle(result, _recipe())
    family = bundle.families[0]
    assert family.status is Status.PARTIAL
    assert family.reason_codes == ("phase_unstable",)
    assert all(reference.validity_mask_id is not None for reference in family.array_refs)
    assert set(arrays) == {
        "f01_c_k_v",
        "f01_c_k_valid",
        "f01_phi_rel_k_rad",
        "f01_phi_rel_k_valid",
        "f01_x_template_v",
        "f01_x_template_valid",
    }
    files = encode_bundle(
        bundle, arrays, tables, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )
    assert load_bundle(files).bundle == bundle


def test_unavailable_f01_maps_reason_codes_without_outputs() -> None:
    result = _available_result()
    unavailable = dataclasses.replace(
        result,
        status=Status.UNAVAILABLE,
        reason_codes=("window_too_short",),
        f1_hz=None,
        c_k_v=None,
        phi_rel_k_rad=None,
        phase_resultant_k=None,
        x_template_v=None,
        window_count=0,
        evaluated_window_count=0,
    )
    bundle, arrays, tables = build_f01_bundle(unavailable, _recipe())
    family = bundle.families[0]
    assert family.status is Status.UNAVAILABLE
    assert family.reason_codes == ("window_too_short",)
    assert family.array_refs == ()
    assert family.table_refs == ()
    assert family.comparison_summary == ()
    assert arrays == {}
    assert tables == {}
    files = encode_bundle(
        bundle, arrays, tables, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )
    assert load_bundle(files).bundle == bundle


def test_missing_outputs_or_reasons_are_rejected() -> None:
    result = _available_result()
    assert result.c_k_v is not None
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f01_bundle(dataclasses.replace(result, c_k_v=None), _recipe())
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f01_bundle(
            dataclasses.replace(
                result,
                status=Status.UNAVAILABLE,
                reason_codes=(),
                f1_hz=None,
                c_k_v=None,
                phi_rel_k_rad=None,
                phase_resultant_k=None,
                x_template_v=None,
            ),
            _recipe(),
        )
