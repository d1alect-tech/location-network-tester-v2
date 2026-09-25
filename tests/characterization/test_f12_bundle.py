"""Persistence mapper F12: masked absence, artifact cap и claim boundary."""

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
    ScalarSummary,
    Status,
    Unit,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f12_bundle import (
    F12_ID,
    F12_INDEX,
    KURTOSIS_TABLE_ID,
    build_f12_family,
    decode_f12_result,
)
from lnt.characterization.f12_contract import (
    ADJUSTED_P_VALUE_NAME,
    ARTIFACT_LIMIT,
    BH_SCOPE,
    CAP_STORAGE_CONVENTION,
    CLAIM_BOUNDARY,
    CONJUGATE_SYMMETRY_CONVENTION,
    DECLARED_CODES,
    FRAME_COUNT_NAME,
    FREQUENCY_AXIS_NAME,
    INSUFFICIENT_FRAMES,
    MAXIMUM_SPECTRAL_KURTOSIS_NAME,
    MAXIMUM_TIE_BREAK,
    METHOD,
    NO_SIGNIFICANT_BIN,
    NULL_SCOPE,
    PHASE_REFERENCE_UNAVAILABLE,
    RANDOM_PHASE_CONVENTION,
    SCALE_INDEX_NAME,
    SCALE_UNSUPPORTED,
    SELECTED_BAND_CONVENTION,
    SELECTED_BAND_HIGH_NAME,
    SELECTED_BAND_LOW_NAME,
    SPECTRAL_KURTOSIS_NAME,
    SURROGATE_PHASE_MEAN_CONVENTION,
    SURROGATE_SUPPORT_NAME,
    WINDOW_SUPPORT_NAME,
    ZERO_POWER,
)
from lnt.characterization.f12_result import F12Result
from lnt.characterization.f12_validation import validate_f12_result
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band, validate_unit_name
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RECORD_S: Final = 2.4
_ARRAY_IDS: Final = (
    "f12_segment_samples",
    FRAME_COUNT_NAME,
    "f12_scale_available",
    FREQUENCY_AXIS_NAME,
    SCALE_INDEX_NAME,
    SPECTRAL_KURTOSIS_NAME,
    ADJUSTED_P_VALUE_NAME,
)
_SUMMARY_IDS: Final = (
    "f12_sample_count",
    "f12_qualified_sample_count",
    WINDOW_SUPPORT_NAME,
    "f12_candidate_count",
    "f12_significant_bin_count",
    "f12_stored_significant_bin_count",
    SURROGATE_SUPPORT_NAME,
    MAXIMUM_SPECTRAL_KURTOSIS_NAME,
)
_BAND_IDS: Final = (SELECTED_BAND_LOW_NAME, SELECTED_BAND_HIGH_NAME, "f12_selected_scale_index")
_SK_MASK: Final = f"{SPECTRAL_KURTOSIS_NAME}_valid"
_P_MASK: Final = f"{ADJUSTED_P_VALUE_NAME}_valid"
_CONVENTIONS: Final = (
    ("bh_scope", BH_SCOPE),
    ("maximum_tie_break", MAXIMUM_TIE_BREAK),
    ("selected_band_convention", SELECTED_BAND_CONVENTION),
    ("cap_storage_convention", CAP_STORAGE_CONVENTION),
    ("null_scope", NULL_SCOPE),
    ("surrogate_phase_mean_convention", SURROGATE_PHASE_MEAN_CONVENTION),
    ("random_phase_convention", RANDOM_PHASE_CONVENTION),
    ("conjugate_symmetry_convention", CONJUGATE_SYMMETRY_CONVENTION),
)
_ARRAY_FIELDS: Final = (
    "segment_samples",
    "frame_count",
    "scale_available",
    "frequencies_hz",
    "scale_index",
    "spectral_kurtosis",
    "adjusted_p_value",
    "maximum_spectral_kurtosis",
    "selected_scale_index",
    "selected_band_low_hz",
    "selected_band_high_hz",
    "sample_count",
    "qualified_sample_count",
    "analyzed_scale_count",
    "candidate_count",
    "significant_bin_count",
    "stored_significant_bin_count",
    "surrogate_count",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F12_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _available() -> F12Result:
    """Доступная F12: четыре scale, пять значимых бинов, полоса из трёх."""
    return F12Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        segment_samples=np.asarray([256, 1024, 4096, 16384], dtype=np.int64),
        frame_count=np.asarray([64, 48, 40, 32], dtype=np.int64),
        scale_available=np.ones(4, dtype=np.bool_),
        frequencies_hz=np.asarray([3000.0, 6000.0, 9000.0, 12000.0, 15000.0], dtype=np.float64),
        scale_index=np.zeros(5, dtype=np.int64),
        spectral_kurtosis=np.asarray([4.0, 2.5, 3.0, 1.0, 0.5], dtype=np.float64),
        adjusted_p_value=np.asarray([0.01, 0.02, 0.03, 0.04, 0.05], dtype=np.float64),
        maximum_spectral_kurtosis=4.0,
        selected_scale_index=0,
        selected_band_low_hz=3000.0,
        selected_band_high_hz=9000.0,
        sample_count=240_000,
        qualified_sample_count=240_000,
        analyzed_scale_count=4,
        candidate_count=12,
        significant_bin_count=5,
        stored_significant_bin_count=5,
        surrogate_count=199,
    )


def _partial() -> F12Result:
    """PARTIAL: одна scale недоступна, cap не связан, полоса из двух бинов."""
    frequencies = np.asarray([3000.0, 6000.0, 9000.0, 12000.0], dtype=np.float64)
    return F12Result(
        status=Status.PARTIAL,
        reason_codes=(SCALE_UNSUPPORTED,),
        segment_samples=np.asarray([256, 1024, 4096, 16384], dtype=np.int64),
        frame_count=np.asarray([64, 48, 40, 0], dtype=np.int64),
        scale_available=np.asarray([True, True, True, False], dtype=np.bool_),
        frequencies_hz=frequencies,
        scale_index=np.zeros(4, dtype=np.int64),
        spectral_kurtosis=np.asarray([2.0, 1.0, 0.5, 0.25], dtype=np.float64),
        adjusted_p_value=np.asarray([0.01, 0.02, 0.03, 0.04], dtype=np.float64),
        maximum_spectral_kurtosis=2.0,
        selected_scale_index=0,
        selected_band_low_hz=3000.0,
        selected_band_high_hz=6000.0,
        sample_count=240_000,
        qualified_sample_count=240_000,
        analyzed_scale_count=3,
        candidate_count=9,
        significant_bin_count=4,
        stored_significant_bin_count=4,
        surrogate_count=199,
    )


def _no_significant() -> F12Result:
    """PARTIAL без значимых бинов: пустой домен и структурно отсутствующая полоса."""
    return F12Result(
        status=Status.PARTIAL,
        reason_codes=(NO_SIGNIFICANT_BIN,),
        segment_samples=np.asarray([256, 1024, 4096, 16384], dtype=np.int64),
        frame_count=np.asarray([64, 48, 40, 32], dtype=np.int64),
        scale_available=np.ones(4, dtype=np.bool_),
        frequencies_hz=np.empty(0, dtype=np.float64),
        scale_index=np.empty(0, dtype=np.int64),
        spectral_kurtosis=np.empty(0, dtype=np.float64),
        adjusted_p_value=np.empty(0, dtype=np.float64),
        maximum_spectral_kurtosis=0.75,
        selected_scale_index=None,
        selected_band_low_hz=None,
        selected_band_high_hz=None,
        sample_count=240_000,
        qualified_sample_count=240_000,
        analyzed_scale_count=4,
        candidate_count=12,
        significant_bin_count=0,
        stored_significant_bin_count=0,
        surrogate_count=199,
    )


def _capped() -> F12Result:
    """PARTIAL со связанным cap: 5000 значимых бинов, 4096 сохранённых."""
    stored = 4096
    frequencies = 3000.0 + 100.0 * np.arange(stored, dtype=np.float64)
    kurtosis = np.empty(stored, dtype=np.float64)
    kurtosis[0] = 10.0
    kurtosis[1:] = 1.0 + np.arange(stored - 1, dtype=np.float64) * 1e-3
    return F12Result(
        status=Status.PARTIAL,
        reason_codes=(ARTIFACT_LIMIT,),
        segment_samples=np.asarray([256, 1024, 4096, 16384], dtype=np.int64),
        frame_count=np.asarray([64, 48, 40, 32], dtype=np.int64),
        scale_available=np.ones(4, dtype=np.bool_),
        frequencies_hz=frequencies,
        scale_index=np.zeros(stored, dtype=np.int64),
        spectral_kurtosis=kurtosis,
        adjusted_p_value=np.full(stored, 0.01, dtype=np.float64),
        maximum_spectral_kurtosis=10.0,
        selected_scale_index=0,
        selected_band_low_hz=3000.0,
        selected_band_high_hz=3000.0 + 100.0 * 99.0,
        sample_count=240_000,
        qualified_sample_count=240_000,
        analyzed_scale_count=4,
        candidate_count=6000,
        significant_bin_count=5000,
        stored_significant_bin_count=stored,
        surrogate_count=199,
    )


def _unavailable() -> F12Result:
    """UNAVAILABLE: только внешний sample count, никаких доменов и опор."""
    return F12Result(
        status=Status.UNAVAILABLE,
        reason_codes=(ZERO_POWER,),
        segment_samples=np.empty(0, dtype=np.int64),
        frame_count=np.empty(0, dtype=np.int64),
        scale_available=np.empty(0, dtype=np.bool_),
        frequencies_hz=np.empty(0, dtype=np.float64),
        scale_index=np.empty(0, dtype=np.int64),
        spectral_kurtosis=np.empty(0, dtype=np.float64),
        adjusted_p_value=np.empty(0, dtype=np.float64),
        maximum_spectral_kurtosis=None,
        selected_scale_index=None,
        selected_band_low_hz=None,
        selected_band_high_hz=None,
        sample_count=240_000,
        qualified_sample_count=0,
        analyzed_scale_count=0,
        candidate_count=0,
        significant_bin_count=0,
        stored_significant_bin_count=0,
        surrogate_count=0,
    )


def _build(
    result: F12Result,
    *,
    family: CharacterizationFamily | None = None,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f12_family(
        result,
        _family() if family is None else family,
        _band(),
        record_duration_s=_RECORD_S,
    )


def _full_bundle(
    mapped: FamilyResult,
    arrays: dict[str, np.ndarray],
    tables: dict[str, TableBlock],
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    recipe = _recipe()
    band = _band()
    families = tuple(
        mapped if index == F12_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def _round_trip(
    result: F12Result,
) -> tuple[F12Result, dict[str, np.ndarray], dict[str, TableBlock]]:
    mapped, arrays, tables = _build(result)
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, arrays, tables)
    loaded = load_bundle(
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    )
    restored = decode_f12_result(loaded.bundle.families[F12_INDEX], loaded.arrays, loaded.tables)
    return restored, dict(loaded.arrays), dict(loaded.tables)


def _without_validation(result: F12Result, **fields: object) -> F12Result:
    """Обойти только dataclass-валидацию для проверки mapper-шов."""
    broken = object.__new__(F12Result)
    for field in dataclasses.fields(F12Result):
        object.__setattr__(broken, field.name, getattr(result, field.name))
    for name, value in fields.items():
        object.__setattr__(broken, name, value)
    return broken


def _assert_result_equal(actual: F12Result, expected: F12Result) -> None:
    for name in _ARRAY_FIELDS:
        left = getattr(actual, name)
        right = getattr(expected, name)
        if isinstance(right, np.ndarray):
            assert isinstance(left, np.ndarray)
            assert left.dtype == right.dtype
            np.testing.assert_array_equal(left, right)
        else:
            assert left == right


def _metadata(tables: dict[str, TableBlock]) -> dict[str, object]:
    table = tables[KURTOSIS_TABLE_ID]
    return dict(zip((column.name for column in table.columns), table.rows[0], strict=True))


def test_available_f12_round_trips_through_bundle_codec_exactly() -> None:
    """Encode→decode сохраняет dtypes, формы, порядок ссылок и все счётчики."""
    result = _available()
    mapped, arrays, tables = _build(result)
    restored, loaded_arrays, loaded_tables = _round_trip(result)

    assert F12_ID == "f12_spectral_kurtosis"
    assert F12_INDEX == 11
    assert FAMILY_IDS[F12_INDEX] == F12_ID
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert tuple(reference.array_id for reference in mapped.array_refs) == _ARRAY_IDS
    assert tuple(item.name for item in mapped.comparison_summary) == (*_SUMMARY_IDS, *_BAND_IDS)
    assert set(tables) == {KURTOSIS_TABLE_ID}
    assert set(loaded_arrays) == set(arrays)
    assert loaded_tables == tables
    for array_id, values in arrays.items():
        assert loaded_arrays[array_id].dtype == values.dtype
        assert loaded_arrays[array_id].shape == values.shape
        np.testing.assert_array_equal(loaded_arrays[array_id], values)
    assert arrays[FRAME_COUNT_NAME].dtype == np.dtype(np.int64)
    assert arrays["f12_scale_available"].dtype == np.dtype(np.uint8)
    assert arrays[SPECTRAL_KURTOSIS_NAME].dtype == np.dtype(np.float64)
    assert arrays[_SK_MASK].dtype == np.dtype(np.uint8)
    assert arrays[_SK_MASK].tolist() == [1, 1, 1, 1, 1]
    assert arrays[_P_MASK].tolist() == [1, 1, 1, 1, 1]
    assert all(np.all(np.isfinite(value)) for value in arrays.values())
    for reference in mapped.array_refs:
        assert validate_unit_name(reference.array_id, reference.unit) is None
    validate_f12_result(restored)
    _assert_result_equal(restored, result)


def test_metadata_table_carries_identity_conventions_and_claim_boundary() -> None:
    """Метаданные несут слот, метод, все восемь конвенций и точный CLAIM_BOUNDARY."""
    _mapped, _arrays, tables = _build(_available())
    table = tables[KURTOSIS_TABLE_ID]
    metadata = _metadata(tables)

    assert table.row_count == 1
    assert table.stored_count == 1
    assert metadata["family_id"] == F12_ID
    assert metadata["family_index"] == F12_INDEX
    assert metadata["method"] == METHOD
    assert metadata["method_version"] == 1
    assert metadata["false_discovery_rate"] == 0.05
    assert metadata["maximum_stored_bins"] == 4096
    assert metadata["claim_boundary"] == CLAIM_BOUNDARY
    for name, value in _CONVENTIONS:
        assert metadata[name] == value
    assert SPECTRAL_KURTOSIS_NAME in str(metadata["quantity_units"])
    assert ADJUSTED_P_VALUE_NAME in str(metadata["quantity_units"])
    assert MAXIMUM_SPECTRAL_KURTOSIS_NAME in str(metadata["quantity_units"])
    assert SELECTED_BAND_LOW_NAME in str(metadata["quantity_units"])
    assert SELECTED_BAND_HIGH_NAME in str(metadata["quantity_units"])
    assert FRAME_COUNT_NAME in str(metadata["quantity_units"])
    assert SCALE_INDEX_NAME in str(metadata["quantity_units"])
    assert SURROGATE_SUPPORT_NAME in str(metadata["quantity_units"])
    assert WINDOW_SUPPORT_NAME in str(metadata["quantity_units"])


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("claim_boundary", "population causation established"),
        ("claim_boundary", CLAIM_BOUNDARY.replace("spectral kurtosis", "global kurtosis")),
        ("bh_scope", "per_scale_candidate_list"),
        ("cap_storage_convention", "lowest_scale_then_lowest_frequency"),
        ("random_phase_convention", "any_phase_including_nyquist"),
    ],
)
def test_altered_or_paraphrased_metadata_text_is_rejected(column: str, value: str) -> None:
    """Декодер отвергает пересказ границы притязаний и любой сдвиг конвенции."""
    mapped, arrays, tables = _build(_available())
    table = tables[KURTOSIS_TABLE_ID]
    index = next(position for position, item in enumerate(table.columns) if item.name == column)
    row = list(table.rows[0])
    row[index] = value
    changed = dict(tables)
    changed[KURTOSIS_TABLE_ID] = dataclasses.replace(table, rows=(tuple(row),))

    with pytest.raises(CharacterizationError, match="metadata"):
        decode_f12_result(mapped, arrays, changed)


def test_unavailable_f12_publishes_empty_domains_and_round_trips() -> None:
    """UNAVAILABLE не публикует ни массивов, ни таблицы, ни сводок."""
    mapped, arrays, tables = _build(_unavailable())
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, arrays, tables)
    loaded = load_bundle(
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    )

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (ZERO_POWER,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert mapped.support.observation_count == 0
    assert mapped.support.sample_count == 0
    assert arrays == {}
    assert tables == {}
    assert loaded.bundle.families[F12_INDEX] == mapped
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}


def test_wrong_recipe_slot_method_version_or_declaration_is_rejected() -> None:
    """Mapper принимает только frozen F12 слот 11 и exact recipe surface."""
    result = _available()
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=_recipe().families[F12_INDEX - 1])
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=dataclasses.replace(_family(), method="wrong_method"))
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=dataclasses.replace(_family(), method_version=2))
    parameters = tuple(
        ("surrogate_count", 99) if name == "surrogate_count" else (name, value)
        for name, value in _family().parameters
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result, family=dataclasses.replace(_family(), parameters=parameters))


def test_persisted_nonfinite_measurement_is_rejected_by_the_global_codec() -> None:
    """Ни один persisted F12 measurement array не принимает NaN или inf."""
    mapped, arrays, tables = _build(_partial())
    for array_id in (SPECTRAL_KURTOSIS_NAME, ADJUSTED_P_VALUE_NAME, FREQUENCY_AXIS_NAME):
        changed = dict(arrays)
        values = changed[array_id].copy()
        values.flat[0] = np.nan
        changed[array_id] = values
        bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, changed, tables)
        with pytest.raises(CharacterizationError, match="array_finite"):
            encode_bundle(
                bundle,
                bundle_arrays,
                bundle_tables,
                max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
            )


def test_masked_out_cell_must_be_exactly_the_declared_zero_filler() -> None:
    """Двусторонний инвариант: вне маски только ровно declared fill 0.0."""
    mapped, arrays, tables = _build(_partial())
    changed = dict(arrays)
    values = changed[SPECTRAL_KURTOSIS_NAME].copy()
    values[3] = 0.5
    changed[SPECTRAL_KURTOSIS_NAME] = values
    mask = changed[_SK_MASK].copy()
    mask[3] = 0
    changed[_SK_MASK] = mask

    with pytest.raises(CharacterizationError, match="zero-under-mask"):
        decode_f12_result(mapped, changed, tables)


def test_mask_restored_absence_is_rejected_by_the_finite_engine_contract() -> None:
    """F12-движок публикует только конечные значения: NaN под маской не измеряние."""
    mapped, arrays, tables = _build(_partial())
    changed = dict(arrays)
    values = changed[ADJUSTED_P_VALUE_NAME].copy()
    values[2] = 0.0
    changed[ADJUSTED_P_VALUE_NAME] = values
    mask = changed[_P_MASK].copy()
    mask[2] = 0
    changed[_P_MASK] = mask

    with pytest.raises(CharacterizationError, match="must be finite"):
        decode_f12_result(mapped, changed, tables)


@pytest.mark.parametrize("array_id", [_SK_MASK, _P_MASK, f"{FRAME_COUNT_NAME}_valid"])
def test_missing_or_malformed_validity_mask_is_rejected(array_id: str) -> None:
    """Маска обязательна, должна быть uint8 той же формы и не теряться."""
    mapped, arrays, tables = _build(_partial())
    dropped = {name: value for name, value in arrays.items() if name != array_id}
    with pytest.raises(CharacterizationError, match="mask"):
        decode_f12_result(mapped, dropped, tables)
    wrong_dtype = dict(arrays)
    wrong_dtype[array_id] = arrays[array_id].astype(np.int64)
    with pytest.raises(CharacterizationError, match="mask"):
        decode_f12_result(mapped, wrong_dtype, tables)
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, wrong_dtype, tables)
    with pytest.raises(CharacterizationError, match="array_mask"):
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )


@pytest.mark.parametrize("array_id", [FRAME_COUNT_NAME, "f12_scale_available", FREQUENCY_AXIS_NAME])
def test_wrong_persisted_dtype_shape_or_reference_order_is_rejected(array_id: str) -> None:
    """Изменённые форма, порядок ссылок и ref маски не проходят декодер."""
    mapped, arrays, tables = _build(_partial())
    wrong_shape = dict(arrays)
    wrong_shape[array_id] = arrays[array_id].reshape(-1)[:2]
    with pytest.raises(CharacterizationError, match="dtype or shape"):
        decode_f12_result(mapped, wrong_shape, tables)
    reordered = dataclasses.replace(
        mapped, array_refs=(mapped.array_refs[1], mapped.array_refs[0], *mapped.array_refs[2:])
    )
    with pytest.raises(CharacterizationError, match="canonical"):
        decode_f12_result(reordered, arrays, tables)


def test_validity_mask_reference_is_never_optional_for_a_measurement() -> None:
    """PARTIAL обязан объявить mask (модель), AVAILABLE всё равно требует его ref."""
    available, available_arrays, available_tables = _build(_available())
    stripped = dataclasses.replace(
        available,
        array_refs=tuple(
            dataclasses.replace(reference, validity_mask_id=None)
            if reference.array_id == SPECTRAL_KURTOSIS_NAME
            else reference
            for reference in available.array_refs
        ),
    )
    with pytest.raises(CharacterizationError, match="canonical"):
        decode_f12_result(stripped, available_arrays, available_tables)

    partial, partial_arrays, partial_tables = _build(_partial())
    with pytest.raises(CharacterizationError, match="invalid family result"):
        dataclasses.replace(
            partial,
            array_refs=tuple(
                dataclasses.replace(reference, validity_mask_id=None)
                if reference.array_id == SPECTRAL_KURTOSIS_NAME
                else reference
                for reference in partial.array_refs
            ),
        )
    assert _partial().status is Status.PARTIAL
    assert partial_tables[KURTOSIS_TABLE_ID].row_count == 1
    assert partial_arrays[FRAME_COUNT_NAME].size == 4


def test_frozen_axis_drift_is_rejected_both_ways() -> None:
    """Объявленная ось scales и её persisted копия обязаны совпадать."""
    result = _available()
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(
            _without_validation(
                result, segment_samples=np.asarray([256, 1024, 4096, 8192], dtype=np.int64)
            )
        )
    mapped, arrays, tables = _build(result)
    drifted = dict(arrays)
    drifted["f12_segment_samples"] = np.asarray([256, 1024, 4096, 8192], dtype=np.int64)
    with pytest.raises(CharacterizationError, match="frozen"):
        decode_f12_result(mapped, drifted, tables)


def test_absent_selected_band_is_explicit_absence_without_status_degradation() -> None:
    """Структурное отсутствие полосы публикуется отсутствием, а не нулём."""
    result = _no_significant()
    mapped, arrays, tables = _build(result)
    restored, _, _ = _round_trip(result)
    names = tuple(item.name for item in mapped.comparison_summary)

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == result.reason_codes == (NO_SIGNIFICANT_BIN,)
    assert not set(names) & set(_BAND_IDS)
    assert arrays[SPECTRAL_KURTOSIS_NAME].size == 0
    assert arrays[ADJUSTED_P_VALUE_NAME].size == 0
    assert arrays[FREQUENCY_AXIS_NAME].size == 0
    assert tables[KURTOSIS_TABLE_ID].row_count == 1
    validate_f12_result(restored)
    _assert_result_equal(restored, result)


@pytest.mark.parametrize("broken", ["band_present", "band_absent"])
def test_selected_band_presence_must_match_significant_bin_count(broken: str) -> None:
    """Полоса публикуется тогда и только тогда, когда есть значимые бины."""
    source = _no_significant() if broken == "band_present" else _available()
    mapped, arrays, tables = _build(source)
    if broken == "band_present":
        summaries = (
            *mapped.comparison_summary,
            ScalarSummary(name=SELECTED_BAND_LOW_NAME, value=3000.0, unit=Unit.HZ),
            ScalarSummary(name=SELECTED_BAND_HIGH_NAME, value=9000.0, unit=Unit.HZ),
            ScalarSummary(name="f12_selected_scale_index", value=0.0, unit=Unit.COUNT),
        )
    else:
        summaries = mapped.comparison_summary[:-3]
    tampered = dataclasses.replace(mapped, comparison_summary=summaries)

    with pytest.raises(CharacterizationError, match="selected band"):
        decode_f12_result(tampered, arrays, tables)


def test_artifact_cap_keeps_maximum_first_and_declares_the_limit() -> None:
    """Связанный cap сохраняет maximum первым и публикует artifact_limit."""
    result = _capped()
    mapped, arrays, _tables = _build(result)
    restored, loaded_arrays, _ = _round_trip(result)

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (ARTIFACT_LIMIT,)
    assert arrays[SPECTRAL_KURTOSIS_NAME].shape == (4096,)
    assert arrays[SPECTRAL_KURTOSIS_NAME][0] == 10.0
    assert loaded_arrays[SPECTRAL_KURTOSIS_NAME].shape == (4096,)
    summaries = {item.name: item.value for item in mapped.comparison_summary}
    assert summaries["f12_significant_bin_count"] == 5000.0
    assert summaries["f12_stored_significant_bin_count"] == 4096.0
    _assert_result_equal(restored, result)

    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(result, reason_codes=()))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(result, stored_significant_bin_count=4000))


def test_stored_domain_must_follow_the_cap_storage_convention() -> None:
    """Максимум первым, дальше полоса, дальше возрастающий scale-frequency."""
    result = _available()
    with pytest.raises(CharacterizationError, match="cap storage"):
        _build(_without_validation(result, spectral_kurtosis=result.spectral_kurtosis[::-1].copy()))
    mapped, arrays, tables = _build(result)
    reordered = dict(arrays)
    reordered[SPECTRAL_KURTOSIS_NAME] = arrays[SPECTRAL_KURTOSIS_NAME][::-1].copy()
    with pytest.raises(CharacterizationError, match="cap storage"):
        decode_f12_result(mapped, reordered, tables)


def test_broken_scale_window_and_surrogate_accounting_is_rejected() -> None:
    """Маппер не мягче движка: опоры scale, окон и суррогатов проверяются дважды."""
    result = _partial()
    cases = (
        _without_validation(result, surrogate_count=99),
        _without_validation(result, analyzed_scale_count=4),
        _without_validation(result, analyzed_scale_count=0),
        _without_validation(result, qualified_sample_count=0),
        _without_validation(result, qualified_sample_count=240_001),
        _without_validation(result, frame_count=np.asarray([64, 48, 40, 32], dtype=np.int64)),
        _without_validation(result, frame_count=np.asarray([64, 8, 40, 0], dtype=np.int64)),
        _without_validation(result, scale_available=np.ones(4, dtype=np.bool_)),
        _without_validation(result, scale_available=np.zeros(4, dtype=np.bool_)),
        _without_validation(result, candidate_count=2),
        _without_validation(result, sample_count=-1),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)
    assert {SCALE_UNSUPPORTED, INSUFFICIENT_FRAMES, PHASE_REFERENCE_UNAVAILABLE} <= set(
        DECLARED_CODES
    )


def test_reason_vocabulary_order_duplicates_and_status_matrix_are_rejected() -> None:
    """Коды closed, sorted, unique; статусная матрица и терминальные коды строги."""
    available = _available()
    unavailable = _unavailable()
    cases = (
        _without_validation(available, status=Status.PARTIAL, reason_codes=(SCALE_UNSUPPORTED,)),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(SCALE_UNSUPPORTED, SCALE_UNSUPPORTED),
        ),
        _without_validation(
            available, status=Status.PARTIAL, reason_codes=(SCALE_UNSUPPORTED, ARTIFACT_LIMIT)
        ),
        _without_validation(available, status=Status.PARTIAL, reason_codes=("not_computed",)),
        _without_validation(available, reason_codes=(SCALE_UNSUPPORTED,)),
        _without_validation(available, status=Status.PARTIAL, reason_codes=()),
        _without_validation(unavailable, reason_codes=()),
        _without_validation(unavailable, frequencies_hz=available.frequencies_hz.copy()),
        _without_validation(
            unavailable, stored_significant_bin_count=available.stored_significant_bin_count
        ),
        _without_validation(
            available, status=Status.PARTIAL, reason_codes=(PHASE_REFERENCE_UNAVAILABLE,)
        ),
        _without_validation(available, status=Status.PARTIAL, reason_codes=(ZERO_POWER,)),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_persisted_summary_accounting_must_match_support_and_band() -> None:
    """Persisted счётчики не могут расходиться с Support и опубликованной полосой."""
    mapped, arrays, tables = _build(_partial())

    drifted = dataclasses.replace(
        mapped,
        comparison_summary=tuple(
            dataclasses.replace(item, value=item.value + 1.0)
            if item.name == "f12_qualified_sample_count"
            else item
            for item in mapped.comparison_summary
        ),
    )
    with pytest.raises(CharacterizationError, match="accounting"):
        decode_f12_result(drifted, arrays, tables)

    negative = dataclasses.replace(
        mapped,
        comparison_summary=tuple(
            dataclasses.replace(item, value=-1.0) if item.name == "f12_sample_count" else item
            for item in mapped.comparison_summary
        ),
    )
    with pytest.raises(CharacterizationError, match="accounting"):
        decode_f12_result(negative, arrays, tables)

    fractional = dataclasses.replace(
        mapped,
        comparison_summary=tuple(
            dataclasses.replace(item, value=2.5) if item.name == "f12_candidate_count" else item
            for item in mapped.comparison_summary
        ),
    )
    with pytest.raises(CharacterizationError, match="accounting"):
        decode_f12_result(fractional, arrays, tables)

    unsupported = dataclasses.replace(mapped, method="other_method")
    with pytest.raises(CharacterizationError, match="identity"):
        decode_f12_result(unsupported, arrays, tables)


def test_partial_f12_publishes_all_validity_masks_and_declares_the_scale_gap() -> None:
    """PARTIAL обязан объявить mask на каждом ref и код недоступной scale."""
    result = _partial()
    mapped, arrays, tables = _build(result)
    restored, _, _ = _round_trip(result)

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (SCALE_UNSUPPORTED,)
    assert all(reference.validity_mask_id is not None for reference in mapped.array_refs)
    assert arrays[FRAME_COUNT_NAME].tolist() == [64, 48, 40, 0]
    assert arrays["f12_scale_available"].tolist() == [1, 1, 1, 0]
    assert arrays[f"{FRAME_COUNT_NAME}_valid"].tolist() == [1, 1, 1, 1]
    summaries = {item.name: item.value for item in mapped.comparison_summary}
    assert summaries[WINDOW_SUPPORT_NAME] == 3.0
    assert summaries[SURROGATE_SUPPORT_NAME] == 199.0
    assert summaries[MAXIMUM_SPECTRAL_KURTOSIS_NAME] == 2.0
    assert summaries[SELECTED_BAND_LOW_NAME] == 3000.0
    assert summaries[SELECTED_BAND_HIGH_NAME] == 6000.0
    validate_f12_result(restored)
    _assert_result_equal(restored, result)
    assert tables[KURTOSIS_TABLE_ID].rows[0][-1] == CLAIM_BOUNDARY


def test_capped_partial_publishes_the_declared_band_range_untouched() -> None:
    """Cap ограничивает COUNT: объявленный диапазон частот полосы не урезается."""
    result = _capped()
    mapped, arrays, _tables = _build(result)
    mapped_again, arrays_again, _tables_again = _build(result)
    summaries = {item.name: item.value for item in mapped.comparison_summary}
    low = summaries[SELECTED_BAND_LOW_NAME]
    high = summaries[SELECTED_BAND_HIGH_NAME]

    assert low == 3000.0
    assert high == 3000.0 + 100.0 * 99.0
    assert high > low
    assert arrays[SPECTRAL_KURTOSIS_NAME].size == 4096
    assert arrays_again[SPECTRAL_KURTOSIS_NAME].size == 4096
    assert summaries["f12_significant_bin_count"] == 5000.0
    assert mapped_again == mapped


def test_decoded_families_survive_a_full_bundle_for_every_built_state() -> None:
    """Все построенные состояния F12 переживают общий кодек артефакта."""
    for result in (_available(), _partial(), _no_significant(), _capped()):
        mapped, arrays, tables = _build(result)
        bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, arrays, tables)
        loaded = load_bundle(
            encode_bundle(
                bundle,
                bundle_arrays,
                bundle_tables,
                max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
            )
        )
        restored = decode_f12_result(
            loaded.bundle.families[F12_INDEX], loaded.arrays, loaded.tables
        )
        assert loaded.bundle.families[F12_INDEX] == mapped
        _assert_result_equal(restored, result)
        assert isinstance(bundle, CharacterizationBundle)
