"""F13: тесты persistence-маппера коактивности огибающих."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Final

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import (
    FAMILY_IDS,
    CharacterizationBundle,
    CharacterizationError,
    Status,
    TableReference,
    Unit,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f13_bundle import F13_ID, F13_INDEX, build_f13_family
from lnt.characterization.f13_math import PAIR_INDICES
from lnt.characterization.f13_result import (
    ACTIVITY_FRACTION_NAME,
    DECLARED_CODES,
    LEAKAGE_AMBIGUOUS,
    PHASE_REFERENCE_UNAVAILABLE,
    F13Result,
)
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band, validate_unit_name
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RECORD_S: Final = 2.4
_BANDS: Final = ((3_000.0, 10_000.0), (10_000.0, 50_000.0), (50_000.0, 200_000.0))
_BAND_NAMES: Final = ("band_0001", "band_0002", "band_0003")
_TABLE_ID: Final = "f13_band_metadata"
_ARRAY_IDS: Final = (
    "f13_band_index",
    "f13_band_low_hz",
    "f13_band_high_hz",
    "f13_lag_s",
    ACTIVITY_FRACTION_NAME,
    "f13_active_sample_count",
    "f13_zero_lag_correlation",
    "f13_coincidence_probability",
    "f13_lift",
    "f13_maximum_lag_s",
    "f13_maximum_lag_correlation",
)
_PAIR_NAMES: Final = (
    "f13_zero_lag_correlation",
    "f13_coincidence_probability",
    "f13_lift",
    "f13_maximum_lag_s",
    "f13_maximum_lag_correlation",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F13_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _available() -> F13Result:
    """Analytic fixture: 1000 qualified samples and three distinct band domains."""
    zero = np.asarray([[1.0, 0.2, 0.3], [0.2, 1.0, 0.4], [0.3, 0.4, 1.0]], dtype=np.float64)
    coincidence = np.asarray([[0.2, 0.1, 0.12], [0.1, 0.4, 0.18], [0.12, 0.18, 0.5]])
    lift = np.asarray([[1.0, 1.25, 1.2], [1.25, 1.0, 0.9], [1.2, 0.9, 1.0]])
    maximum_lag = np.asarray([[0.0, 0.01, -0.02], [0.01, 0.0, 0.02], [-0.02, 0.02, 0.0]])
    maximum_correlation = np.asarray(
        [[1.0, 0.5, -0.4], [0.5, 1.0, 0.3], [-0.4, 0.3, 1.0]], dtype=np.float64
    )
    return F13Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        band_names=_BAND_NAMES,
        bands_hz=_BANDS,
        lag_s=np.asarray([-0.02, -0.01, 0.0, 0.01, 0.02], dtype=np.float64),
        activity_fraction=np.asarray([0.2, 0.4, 0.5], dtype=np.float64),
        active_sample_count=np.asarray([200, 400, 500], dtype=np.int64),
        sample_count=1_200,
        qualified_sample_count=1_000,
        zero_lag_correlation=zero,
        coincidence_probability=coincidence,
        lift=lift,
        maximum_lag_s=maximum_lag,
        maximum_lag_correlation=maximum_correlation,
    )


def _unavailable() -> F13Result:
    return F13Result(
        status=Status.UNAVAILABLE,
        reason_codes=(PHASE_REFERENCE_UNAVAILABLE,),
        band_names=_BAND_NAMES,
        bands_hz=_BANDS,
        lag_s=np.empty(0, dtype=np.float64),
        activity_fraction=np.empty(0, dtype=np.float64),
        active_sample_count=np.empty(0, dtype=np.int64),
        sample_count=1_200,
        qualified_sample_count=0,
        zero_lag_correlation=np.empty(0, dtype=np.float64),
        coincidence_probability=np.empty(0, dtype=np.float64),
        lift=np.empty(0, dtype=np.float64),
        maximum_lag_s=np.empty(0, dtype=np.float64),
        maximum_lag_correlation=np.empty(0, dtype=np.float64),
    )


def _build(
    result: F13Result,
    *,
    family: CharacterizationFamily | None = None,
    channel: str = "ch1",
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f13_family(
        result,
        _family() if family is None else family,
        _band(),
        measured_channel=channel,
        record_duration_s=_RECORD_S,
    )


def _without_validation(result: F13Result, **fields: object) -> F13Result:
    """Обойти только dataclass-валидацию, чтобы проверить шов mapper-а."""
    broken = object.__new__(F13Result)
    for field in dataclasses.fields(F13Result):
        object.__setattr__(broken, field.name, getattr(result, field.name))
    for name, value in fields.items():
        object.__setattr__(broken, name, value)
    return broken


def _full_bundle(
    mapped: FamilyResult,
    arrays: dict[str, np.ndarray],
    tables: dict[str, TableBlock],
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    recipe = _recipe()
    band = _band()
    families = tuple(
        mapped if index == F13_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def test_f13_is_in_frozen_slot_twelve() -> None:
    """F13 сохраняет frozen ID, метод и позицию рецепта."""
    recipe = _recipe()
    assert F13_INDEX == 12
    assert F13_ID == "f13_band_envelope_coactivity"
    assert FAMILY_IDS[F13_INDEX] == F13_ID
    assert recipe.families[F13_INDEX].method == "phase_residual_hilbert_envelope_coactivity"


def test_available_maps_every_result_field_and_band_metadata() -> None:
    """Доступный F13 публикует оси, пять матриц и гетерогенные метаданные полос."""
    result = _available()
    mapped, arrays, tables = _build(result)
    refs = {reference.array_id: reference for reference in mapped.array_refs}

    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert mapped.units == (Unit.RATIO, Unit.S, Unit.COUNT, Unit.HZ)
    assert mapped.window.kind == "record"
    assert mapped.window.duration_s == _RECORD_S
    assert mapped.filter.kind == "butterworth_sos"
    assert mapped.filter.order == 4
    assert mapped.filter.phase == "zero"
    assert tuple(reference.array_id for reference in mapped.array_refs) == _ARRAY_IDS
    assert mapped.table_refs == (TableReference(table_id=_TABLE_ID, role="band_metadata"),)
    assert set(tables) == {_TABLE_ID}
    assert tables[_TABLE_ID].row_count == 3
    assert tuple(row[1] for row in tables[_TABLE_ID].rows) == _BAND_NAMES
    assert tuple(row[2:4] for row in tables[_TABLE_ID].rows) == _BANDS
    for array_id in _ARRAY_IDS:
        assert refs[array_id].shape == arrays[array_id].shape
        assert refs[array_id].dtype == arrays[array_id].dtype.name
    assert np.array_equal(arrays["f13_activity_fraction"], result.activity_fraction)
    assert np.array_equal(arrays["f13_active_sample_count"], result.active_sample_count)
    assert np.array_equal(arrays["f13_lag_s"], result.lag_s)
    for name, field in zip(
        _PAIR_NAMES,
        (
            "zero_lag_correlation",
            "coincidence_probability",
            "lift",
            "maximum_lag_s",
            "maximum_lag_correlation",
        ),
        strict=True,
    ):
        assert np.array_equal(arrays[name], getattr(result, field))
    assert "f13_bipolar_count" not in arrays


def test_declared_values_and_lag_cap_are_visible_in_summaries() -> None:
    """Рецептные границы, guard и materialised cap не исчезают в mapper-е."""
    result = _available()
    mapped, _, _ = _build(result)
    summaries = {item.name: item for item in mapped.comparison_summary}

    assert summaries["f13_sample_count"].value == 1_200.0
    assert summaries["f13_qualified_sample_count"].value == 1_000.0
    assert summaries["f13_stored_lag_count"].value == 5.0
    assert summaries["f13_maximum_lag_points"].value == 2_049.0
    assert summaries["f13_lag_low_s"].value == pytest.approx(-0.02)
    assert summaries["f13_lag_high_s"].value == pytest.approx(0.02)
    assert summaries["f13_filter_edge_guard_fraction"].value == pytest.approx(0.01)
    assert summaries["f13_phase_bins"].value == 64.0
    assert summaries["f13_minimum_active_samples"].value == 20.0


def test_thinned_symmetric_lag_grid_is_accepted() -> None:
    """Разреженная сетка сохраняет диапазон, симметрию и нулевой lag."""
    thinned = _without_validation(
        _available(),
        lag_s=np.asarray([-0.02, 0.0, 0.02], dtype=np.float64),
        maximum_lag_s=np.asarray([[0.0, 0.02, -0.02], [0.02, 0.0, 0.02], [-0.02, 0.02, 0.0]]),
    )
    mapped, arrays, _ = _build(thinned)

    assert mapped.status is Status.AVAILABLE
    assert np.array_equal(arrays["f13_lag_s"], np.asarray([-0.02, 0.0, 0.02]))


def test_available_family_round_trips_through_codec_with_dtypes() -> None:
    """Artifact codec сохраняет F13 metadata, массивы, dtype и таблицу без потерь."""
    result = _available()
    mapped, arrays, tables = _build(result)
    bundle, all_arrays, all_tables = _full_bundle(mapped, arrays, tables)
    loaded = load_bundle(
        encode_bundle(
            bundle,
            all_arrays,
            all_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    )

    assert loaded.bundle.families[F13_INDEX] == mapped
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert loaded.arrays[array_id].shape == values.shape
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables


def test_partial_publishes_masks_for_every_array() -> None:
    """PARTIAL объявляет validity mask той же формы на каждом массиве."""
    result = dataclasses.replace(
        _available(), status=Status.PARTIAL, reason_codes=(LEAKAGE_AMBIGUOUS,)
    )
    mapped, arrays, _ = _build(result)

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (LEAKAGE_AMBIGUOUS,)
    for reference in mapped.array_refs:
        mask_id = reference.validity_mask_id
        assert mask_id == f"{reference.array_id}_valid"
        assert mask_id is not None
        assert arrays[mask_id].dtype == np.uint8
        assert arrays[mask_id].shape == reference.shape


def test_partial_masks_round_trip_through_codec() -> None:
    """Маски PARTIAL переживают NPZ round-trip без смены формы или dtype."""
    result = dataclasses.replace(
        _available(), status=Status.PARTIAL, reason_codes=(LEAKAGE_AMBIGUOUS,)
    )
    mapped, arrays, tables = _build(result)
    bundle, all_arrays, all_tables = _full_bundle(mapped, arrays, tables)
    loaded = load_bundle(
        encode_bundle(
            bundle,
            all_arrays,
            all_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    )

    assert loaded.bundle.families[F13_INDEX] == mapped
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert np.array_equal(loaded.arrays[array_id], values)


def test_unavailable_publishes_no_outputs_and_empty_domains() -> None:
    """UNAVAILABLE не публикует ни нулевые строки, ни NaN, ни таблицу."""
    mapped, arrays, tables = _build(_unavailable())

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert arrays == {}
    assert tables == {}
    assert mapped.support == type(mapped.support)(
        start_s=0.0,
        end_s=0.0,
        duration_s=0.0,
        sample_count=0,
        observation_count=0,
        missing_count=0,
        stored_count=0,
        selection_rule="all",
    )


def test_wrong_recipe_slot_is_rejected() -> None:
    """Mapper принимает F13 только в слоте 12."""
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=_recipe().families[F13_INDEX - 1])


def test_misaligned_array_is_rejected_without_reshape() -> None:
    """Форма F13-поля обязана совпасть, mapper не перестраивает матрицу."""
    broken = _without_validation(_available(), active_sample_count=np.zeros(2, dtype=np.int64))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_wrong_shape_validity_mask_is_rejected_by_codec() -> None:
    """Codec отвергает маску, размер которой отличается от массива."""
    result = dataclasses.replace(
        _available(), status=Status.PARTIAL, reason_codes=(LEAKAGE_AMBIGUOUS,)
    )
    mapped, arrays, tables = _build(result)
    arrays["f13_activity_fraction_valid"] = np.ones(2, dtype=np.uint8)
    bundle, all_arrays, all_tables = _full_bundle(mapped, arrays, tables)
    with pytest.raises(CharacterizationError, match="array_mask"):
        encode_bundle(
            bundle,
            all_arrays,
            all_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )


def test_broken_accounting_is_rejected() -> None:
    """Mapper проверяет qualified count, activity fraction и lift engine-формулы."""
    broken = (
        _without_validation(_available(), qualified_sample_count=999),
        _without_validation(_available(), activity_fraction=np.asarray([0.2, 0.4, 0.6])),
        _without_validation(
            _available(),
            coincidence_probability=np.asarray(
                [[0.2, 0.2, 0.12], [0.2, 0.4, 0.18], [0.12, 0.18, 0.5]]
            ),
        ),
    )
    for result in broken:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(result)


def test_grid_outside_declared_range_is_rejected() -> None:
    """Materialised grid не может выдавать себя за declared F13 range."""
    broken = _without_validation(
        _available(),
        lag_s=np.asarray([-0.03, -0.01, 0.0, 0.01, 0.02], dtype=np.float64),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_asymmetric_or_zero_lagging_grid_is_rejected() -> None:
    """Сетка обязана быть симметричной и содержать ровно доступный zero lag."""
    asymmetric = _without_validation(
        _available(), lag_s=np.asarray([-0.02, 0.0, 0.01, 0.02], dtype=np.float64)
    )
    no_zero = _without_validation(
        _available(), lag_s=np.asarray([-0.02, -0.01, 0.01, 0.02], dtype=np.float64)
    )
    for result in (asymmetric, no_zero):
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(result)


def test_lag_grid_over_declared_cap_is_rejected() -> None:
    """Mapper не усекает и не фабрикует lag rows сверх recipe cap."""
    lag = np.linspace(-0.02, 0.02, 2_051, dtype=np.float64)
    lag[1_025] = 0.0
    broken = _without_validation(
        _available(),
        lag_s=lag,
        maximum_lag_s=np.zeros((3, 3), dtype=np.float64),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_cap_sized_grid_is_declared_without_fabricated_rows() -> None:
    """Grid ровно на cap сохраняется целиком и виден в summary."""
    lag = np.linspace(-0.02, 0.02, 2_049, dtype=np.float64)
    lag[1_024] = 0.0
    result = _without_validation(
        _available(), lag_s=lag, maximum_lag_s=np.zeros((3, 3), dtype=np.float64)
    )
    mapped, arrays, _ = _build(result)
    summaries = {item.name: item for item in mapped.comparison_summary}

    assert arrays["f13_lag_s"].shape == (2_049,)
    assert summaries["f13_stored_lag_count"].value == 2_049.0
    assert summaries["f13_maximum_lag_points"].value == 2_049.0
    assert mapped.status is Status.AVAILABLE


def test_status_and_reason_vocabulary_invariants_are_rejected() -> None:
    """Status/reason matrix проверяетсяPersistence-швом независимо F13Result.__post_init__."""
    cases = (
        _without_validation(_available(), reason_codes=(LEAKAGE_AMBIGUOUS,)),
        _without_validation(_available(), status=Status.PARTIAL, reason_codes=()),
        _without_validation(_unavailable(), reason_codes=()),
        _without_validation(_available(), status=Status.PARTIAL, reason_codes=("not_computed",)),
        _without_validation(
            _available(), status=Status.PARTIAL, reason_codes=(LEAKAGE_AMBIGUOUS, LEAKAGE_AMBIGUOUS)
        ),
        _without_validation(
            _available(),
            status=Status.PARTIAL,
            reason_codes=(LEAKAGE_AMBIGUOUS, "band_above_nyquist"),
        ),
    )
    for result in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(result)


def test_reason_codes_are_sorted_unique_and_closed() -> None:
    """Reason vocabulary F13 не расширяется и не сортируется скрыто."""
    assert set(DECLARED_CODES) == {
        "phase_reference_unavailable",
        "band_above_nyquist",
        "filter_support_too_short",
        "filter_context_unstable",
        "nonfinite_input",
        "mixed_unavailable_support",
        "scale_zero",
        "insufficient_activity",
        "lag_support_too_short",
        "leakage_ambiguous",
    }
    result = dataclasses.replace(
        _available(),
        status=Status.PARTIAL,
        reason_codes=("band_above_nyquist", LEAKAGE_AMBIGUOUS),
    )
    mapped, _, _ = _build(result)
    assert mapped.reason_codes == ("band_above_nyquist", LEAKAGE_AMBIGUOUS)


def test_band_axis_must_follow_shared_resolver_order() -> None:
    """Persisted band names/edges не получают конкурирующий F13 naming."""
    broken = _without_validation(
        _available(),
        band_names=("band_0002", "band_0001", "band_0003"),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_measured_channel_and_units_are_persisted() -> None:
    """Signal plane и unit vocabulary соответствуют persisted F13 envelope."""
    mapped, arrays, _ = _build(_available(), channel="ch2")
    assert mapped.signal_plane.value == "ch2_transformer_secondary"
    for reference in mapped.array_refs:
        validate_unit_name(reference.array_id, reference.unit)
        assert arrays[reference.array_id].dtype.name == reference.dtype
    assert arrays["f13_active_sample_count"].dtype == np.int64
    assert arrays["f13_lift"].dtype == np.float64
    assert mapped.units == (Unit.RATIO, Unit.S, Unit.COUNT, Unit.HZ)
    assert PAIR_INDICES == ((0, 1), (0, 2), (1, 2))


def test_unavailable_round_trips_without_outputs() -> None:
    """Unavailable F13 проходит three-file codec как envelope без артефактов."""
    mapped, arrays, tables = _build(_unavailable())
    bundle, all_arrays, all_tables = _full_bundle(mapped, arrays, tables)
    loaded = load_bundle(
        encode_bundle(
            bundle,
            all_arrays,
            all_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    )
    assert loaded.bundle.families[F13_INDEX] == mapped
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}
