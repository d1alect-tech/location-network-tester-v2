"""F02 bundle assembly: mapped F02 beside an unchanged F01 family."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import (
    FAMILY_IDS,
    CharacterizationError,
    Status,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.event_models import RootEvent
from lnt.characterization.f01_bundle import build_f01_bundle
from lnt.characterization.f01_phase_cycle import F01Result, compute_f01_phase_cycle
from lnt.characterization.f02_amplitude_shape import METHOD as F02_METHOD
from lnt.characterization.f02_amplitude_shape import (
    F02Result,
    compute_f02_amplitude_time_shape,
)
from lnt.characterization.f02_bundle import build_f01_f02_bundle
from lnt.context.json_codec import decode_object
from lnt.events.models import Polarity

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 8000.0
_TEMPLATE_SAMPLES = 1000
_AMPS = {1: 6.0, 3: 0.6, 5: 0.3, 7: 0.15}
_PHASES = {1: 0.4, 3: -0.7, 5: 1.1, 7: 0.2}
_F02_ARRAY_IDS = {"f02_a", "f02_tau_s", "f02_rho", "f02_e_res_v2_s"}

type Float64Array = NDArray[np.float64]


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _comb(duration_s: float = 2.4) -> Float64Array:
    n = round(_FS_HZ * duration_s)
    t = np.arange(n, dtype=np.float64) / _FS_HZ
    signal = np.zeros(n, dtype=np.float64)
    for order in range(1, 41):
        signal += (6.0 / order) * np.sin(2.0 * np.pi * 50.0 * order * t)
    return signal


def _f01_result() -> F01Result:
    signal = _comb()
    result = compute_f01_phase_cycle(signal, sample_rate_hz=_FS_HZ, sync_reference=signal)
    assert result.status is Status.AVAILABLE
    return result


def _template() -> Float64Array:
    theta = np.linspace(0.0, 2.0 * np.pi, _TEMPLATE_SAMPLES, endpoint=False)
    out = np.zeros(_TEMPLATE_SAMPLES, dtype=np.float64)
    for order, amp in _AMPS.items():
        out += 2.0 * amp * np.cos(float(order) * theta + _PHASES[order])
    return out


def _event(start: int, end: int, ordinal: int = 1, snr_ratio: float = 100.0) -> RootEvent:
    peak = (start + end) // 2
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=0,
        start_sample=start,
        end_sample=end,
        peak_sample=peak,
        start_time_s=start / _FS_HZ,
        end_time_s=end / _FS_HZ,
        peak_time_s=peak / _FS_HZ,
        peak_value_v=20.0,
        polarity=Polarity.POSITIVE,
        snr_ratio=snr_ratio,
        excess_v2_s=0.0,
        v2_s=0.0,
        clipped=False,
        dominant_band=None,
        dominant_band_reason_code=None,
        boundary=False,
    )


def _f02_result() -> F02Result:
    template = _template()
    span = _TEMPLATE_SAMPLES
    rng = np.random.default_rng(6022)
    record = rng.standard_normal(3 * span) * 0.05
    delayed = np.zeros(span, dtype=np.float64)
    delayed[37:] = 1.7 * template[: span - 37]
    record[span : 2 * span] += delayed
    result = compute_f02_amplitude_time_shape(
        record, template, (_event(span, 2 * span - 1),), sample_rate_hz=_FS_HZ
    )
    assert result.status is Status.AVAILABLE
    return result


def _mixed_result() -> F02Result:
    """One fitted event beside one rejected event: the PARTIAL accounting case."""
    fitted = _f02_result()
    return dataclasses.replace(
        fitted,
        status=Status.PARTIAL,
        reason_codes=("below_snr",),
        amplitudes=(fitted.amplitudes[0], None),
        delays_s=(fitted.delays_s[0], None),
        residual_fractions=(fitted.residual_fractions[0], None),
        residual_energies_v2_s=(fitted.residual_energies_v2_s[0], None),
        evaluated_event_count=2,
    )


def _unavailable_f02() -> F02Result:
    blanks: tuple[None, ...] = (None,)
    return dataclasses.replace(
        _f02_result(),
        status=Status.UNAVAILABLE,
        reason_codes=("template_unavailable",),
        amplitudes=blanks,
        delays_s=blanks,
        residual_fractions=blanks,
        residual_energies_v2_s=blanks,
        evaluated_event_count=0,
        omitted_event_count=0,
    )


def _limits() -> int:
    return _recipe().resource_limits.max_artifact_bytes


def test_bundle_has_exactly_eighteen_ordered_families() -> None:
    bundle, _, _ = build_f01_f02_bundle(_f01_result(), _f02_result(), _recipe())
    assert tuple(family.family_id for family in bundle.families) == FAMILY_IDS
    assert bundle.families[0].status is Status.AVAILABLE
    assert bundle.families[1].family_id == "f02_amplitude_time_shape"
    assert bundle.families[1].status is Status.AVAILABLE


def test_sixteen_placeholders_use_recipe_methods_without_outputs() -> None:
    recipe = _recipe()
    bundle, arrays, tables = build_f01_f02_bundle(_f01_result(), _f02_result(), recipe)
    expected = {family.id: (family.method, family.method_version) for family in recipe.families}
    for family in bundle.families[2:]:
        assert family.status is Status.UNAVAILABLE
        assert family.reason_codes == ("not_computed",)
        assert (family.method, family.method_version) == expected[family.family_id]
        assert family.array_refs == ()
        assert family.table_refs == ()
        assert family.comparison_summary == ()
    assert expected["f03_interharmonic_tracking"][0] == "synchronous_bin_nearest_neighbor_tracks"
    assert set(tables) == {"f01_harmonics"}
    assert not any(name.startswith("f03_") for name in arrays)


def test_f01_family_and_outputs_are_unchanged_by_f02() -> None:
    f01 = _f01_result()
    recipe = _recipe()
    single, single_arrays, single_tables = build_f01_bundle(f01, recipe)
    combined, combined_arrays, combined_tables = build_f01_f02_bundle(f01, _f02_result(), recipe)
    assert combined.families[0] == single.families[0]
    assert combined_tables == single_tables
    for name, array in single_arrays.items():
        assert np.array_equal(combined_arrays[name], array)


def test_f02_available_maps_quantities_to_outputs() -> None:
    result = _f02_result()
    bundle, arrays, _ = build_f01_f02_bundle(_f01_result(), result, _recipe())
    family = bundle.families[1]
    assert family.status is Status.AVAILABLE
    assert family.reason_codes == ()
    assert (family.method, family.method_version) == (F02_METHOD, 1)
    assert family.signal_plane == "ch1_scope_input"
    assert family.comparison_summary[0].name == "f02_event_count"
    assert family.comparison_summary[0].value == pytest.approx(1.0)
    assert {reference.array_id for reference in family.array_refs} == _F02_ARRAY_IDS
    assert all(reference.validity_mask_id is None for reference in family.array_refs)
    assert set(arrays) >= _F02_ARRAY_IDS
    assert arrays["f02_a"].shape == (1,)
    assert arrays["f02_a"][0] == pytest.approx(1.7, abs=0.01)
    assert arrays["f02_tau_s"][0] == pytest.approx(37.0 / _FS_HZ, rel=1e-3)
    assert arrays["f02_rho"][0] < 0.25
    assert arrays["f02_e_res_v2_s"].dtype.name == "float64"
    assert family.support.observation_count == result.evaluated_event_count == 1
    assert family.support.missing_count == 0


def test_measured_channel_selects_f02_signal_plane() -> None:
    bundle, _, _ = build_f01_f02_bundle(
        _f01_result(), _f02_result(), _recipe(), measured_channel="ch2"
    )
    assert bundle.families[1].signal_plane == "ch2_transformer_secondary"


def test_partial_f02_stores_only_fitted_events_with_masks() -> None:
    bundle, arrays, tables = build_f01_f02_bundle(_f01_result(), _mixed_result(), _recipe())
    family = bundle.families[1]
    assert family.status is Status.PARTIAL
    assert family.reason_codes == ("below_snr",)
    assert all(reference.validity_mask_id is not None for reference in family.array_refs)
    assert arrays["f02_a"].shape == (1,)
    assert arrays["f02_a_valid"].dtype == np.uint8
    assert arrays["f02_a_valid"].tolist() == [1]
    assert family.support.sample_count == 2
    assert family.support.observation_count == 1
    assert family.support.missing_count == 1
    assert family.support.stored_count == 1
    loaded = load_bundle(encode_bundle(bundle, arrays, tables, max_artifact_bytes=_limits()))
    assert loaded.bundle.families[1] == family


def test_unavailable_f02_maps_reason_codes_without_outputs() -> None:
    bundle, arrays, tables = build_f01_f02_bundle(_f01_result(), _unavailable_f02(), _recipe())
    family = bundle.families[1]
    assert family.status is Status.UNAVAILABLE
    assert family.reason_codes == ("template_unavailable",)
    assert family.array_refs == ()
    assert family.table_refs == ()
    assert family.comparison_summary == ()
    assert family.support.sample_count == 0
    assert not any(name.startswith("f02_") for name in arrays)
    assert "f02_events" not in tables
    loaded = load_bundle(encode_bundle(bundle, arrays, tables, max_artifact_bytes=_limits()))
    assert loaded.bundle == bundle


def test_round_trip_through_bundle_codec() -> None:
    bundle, arrays, tables = build_f01_f02_bundle(_f01_result(), _f02_result(), _recipe())
    files = encode_bundle(bundle, arrays, tables, max_artifact_bytes=_limits())
    assert tuple(files) == (
        "characterization.json",
        "characterization-arrays.npz",
        "characterization-tables.json",
    )
    loaded = load_bundle(files)
    assert loaded.bundle == bundle
    assert set(loaded.arrays) == set(arrays)
    assert loaded.tables == tables


def test_unavailable_f02_without_reasons_is_rejected() -> None:
    broken = dataclasses.replace(_unavailable_f02(), reason_codes=())
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f01_f02_bundle(_f01_result(), broken, _recipe())


def test_available_f02_with_reasons_is_rejected() -> None:
    broken = dataclasses.replace(_f02_result(), reason_codes=("below_snr",))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f01_f02_bundle(_f01_result(), broken, _recipe())


def _capped_result() -> F02Result:
    """Два непересекающихся события при maximum_events=1: случай усечённого хвоста."""
    template = _template()
    span = _TEMPLATE_SAMPLES
    rng = np.random.default_rng(6022)
    record = rng.standard_normal(5 * span) * 0.05
    delayed = np.zeros(span, dtype=np.float64)
    delayed[37:] = 1.7 * template[: span - 37]
    record[span : 2 * span] += delayed
    record[3 * span : 4 * span] += delayed
    result = compute_f02_amplitude_time_shape(
        record,
        template,
        (_event(span, 2 * span - 1, ordinal=1), _event(3 * span, 4 * span - 1, ordinal=2)),
        sample_rate_hz=_FS_HZ,
        maximum_events=1,
    )
    assert result.evaluated_event_count == 1
    assert result.omitted_event_count == 1
    return result


def test_capped_event_inventory_stays_visible_in_support() -> None:
    """Усечённый хвост за maximum_events не исчезает из учёта поддержки."""
    bundle, arrays, _tables = build_f01_f02_bundle(_f01_result(), _capped_result(), _recipe())
    f02 = bundle.families[1]
    assert f02.support.sample_count == 2
    assert f02.support.observation_count == 1
    assert f02.support.missing_count == 1
    assert f02.support.stored_count == 1
    summary = {item.name: item.value for item in f02.comparison_summary}
    assert summary["f02_event_count"] == 1.0
    assert summary["f02_omitted_event_count"] == 1.0
    assert arrays["f02_a"].size == 1
