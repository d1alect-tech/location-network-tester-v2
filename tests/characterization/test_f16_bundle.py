"""Persistence mapper F16: masked absence, accounting и claim boundary."""

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
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f16_bundle import (
    F16_ID,
    F16_INDEX,
    MEMORY_TABLE_ID,
    build_f16_family,
    decode_f16_result,
)
from lnt.characterization.f16_contract import (
    ACF_AGGREGATION,
    ANALYZED_SEGMENT_CONVENTION,
    AUTOCORRELATION_NAME,
    CLAIM_BOUNDARY,
    COUNT_MEAN_NAME,
    COUNT_VARIANCE_NAME,
    COUNT_WINDOW_CONVENTION,
    DECLARED_CODES,
    FANO_FACTOR_NAME,
    INSUFFICIENT_COUNT_WINDOWS,
    INSUFFICIENT_PAIRS,
    LAG_ABOVE_SUPPORT,
    LAG_SAMPLE_CONVENTION,
    MAD_CONVENTION,
    PHASE_REFERENCE_UNAVAILABLE,
    RECURRENCE_RATE_NAME,
    SCALE_ZERO,
)
from lnt.characterization.f16_result import F16Result
from lnt.characterization.f16_validation import validate_f16_result
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
    "f16_lag_s",
    AUTOCORRELATION_NAME,
    "f16_pair_count",
    "f16_recurrence_radius_mad",
    RECURRENCE_RATE_NAME,
    "f16_count_window_s",
    "f16_count_window_count",
    COUNT_MEAN_NAME,
    COUNT_VARIANCE_NAME,
    FANO_FACTOR_NAME,
)
_ARRAY_FIELDS: Final = (
    "lag_s",
    "autocorrelation",
    "pair_count",
    "recurrence_radius_mad",
    "recurrence_rate",
    "count_window_s",
    "count_window_count",
    "count_mean",
    "count_variance",
    "fano_factor",
    "lag_available",
    "count_window_available",
    "fano_available",
    "sample_count",
    "qualified_sample_count",
    "analyzed_segment_count",
    "event_count",
)
_LAG_MASK: Final = "f16_lag_valid"
_RECURRENCE_MASK: Final = "f16_recurrence_rate_valid"
_COUNT_MASK: Final = "f16_count_window_valid"
_FANO_MASK: Final = "f16_fano_factor_valid"


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F16_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _partial() -> F16Result:
    """Ручная F16-фикстура: два lag mask и два count-window mask."""
    lag_available = np.asarray([True, False, True, True, True, False], dtype=np.bool_)
    autocorrelation = np.asarray([0.125, np.nan, -0.25, 0.5, 0.75, np.nan], dtype=np.float64)
    recurrence = np.asarray(
        [
            [0.0, 0.25, 0.5],
            [np.nan, np.nan, np.nan],
            [0.1, 0.4, 0.8],
            [0.2, 0.6, 0.9],
            [0.3, 0.7, 1.0],
            [np.nan, np.nan, np.nan],
        ],
        dtype=np.float64,
    )
    count_window_available = np.asarray([True, True, False, False], dtype=np.bool_)
    count_mean = np.asarray([16.0 / 119.0, 16.0 / 23.0, np.nan, np.nan], dtype=np.float64)
    count_variance = np.asarray([0.25, 0.5, np.nan, np.nan], dtype=np.float64)
    fano_available = count_window_available.copy()
    return F16Result(
        status=Status.PARTIAL,
        reason_codes=(INSUFFICIENT_COUNT_WINDOWS, INSUFFICIENT_PAIRS, LAG_ABOVE_SUPPORT),
        lag_s=np.asarray([0.0001, 0.001, 0.01, 0.02, 0.1, 0.5], dtype=np.float64),
        autocorrelation=autocorrelation,
        pair_count=np.asarray([120, 99, 130, 140, 150, 0], dtype=np.int64),
        lag_available=lag_available,
        recurrence_radius_mad=np.asarray([0.5, 1.0, 2.0], dtype=np.float64),
        recurrence_rate=recurrence,
        count_window_s=np.asarray([0.02, 0.1, 0.5, 1.0], dtype=np.float64),
        count_window_count=np.asarray([119, 23, 4, 2], dtype=np.int64),
        count_mean=count_mean,
        count_variance=count_variance,
        fano_factor=np.asarray([0.25 / (16.0 / 119.0), 0.5 / (16.0 / 23.0), np.nan, np.nan]),
        count_window_available=count_window_available,
        fano_available=fano_available,
        sample_count=240_000,
        qualified_sample_count=240_000,
        analyzed_segment_count=1,
        event_count=16,
    )


def _build(
    result: F16Result,
    *,
    family: CharacterizationFamily | None = None,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f16_family(
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
        mapped if index == F16_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def _assert_result_equal(actual: F16Result, expected: F16Result) -> None:
    for name in _ARRAY_FIELDS:
        left = getattr(actual, name)
        right = getattr(expected, name)
        if isinstance(right, np.ndarray):
            assert isinstance(left, np.ndarray)
            assert left.dtype == right.dtype
            np.testing.assert_array_equal(left, right)
        else:
            assert left == right


def test_partial_f16_codec_round_trip_restores_masked_absence() -> None:
    """Fill 0.0 и mask восстанавливают точный NaN-контракт движка."""
    result = _partial()
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
    restored = decode_f16_result(loaded.bundle.families[F16_INDEX], loaded.arrays, loaded.tables)
    validate_f16_result(restored)

    assert F16_ID == "f16_multiscale_memory"
    assert F16_INDEX == 15
    assert FAMILY_IDS[F16_INDEX] == F16_ID
    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == result.reason_codes
    assert tuple(reference.array_id for reference in mapped.array_refs) == _ARRAY_IDS
    assert set(tables) == {MEMORY_TABLE_ID}
    assert loaded.bundle.families[F16_INDEX] == mapped
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert loaded.arrays[array_id].shape == values.shape
        np.testing.assert_array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables

    assert arrays[_LAG_MASK].tolist() == [1, 0, 1, 1, 1, 0]
    assert arrays[_RECURRENCE_MASK][1].tolist() == [0, 0, 0]
    assert arrays[_RECURRENCE_MASK][5].tolist() == [0, 0, 0]
    assert arrays[_COUNT_MASK].tolist() == [1, 1, 0, 0]
    assert arrays[_FANO_MASK].tolist() == [1, 1, 0, 0]
    assert arrays[AUTOCORRELATION_NAME][~result.lag_available].tolist() == [0.0, 0.0]
    assert np.all(arrays[RECURRENCE_RATE_NAME][~result.lag_available] == 0.0)
    assert np.all(arrays[COUNT_MEAN_NAME][~result.count_window_available] == 0.0)
    assert np.all(arrays[COUNT_VARIANCE_NAME][~result.count_window_available] == 0.0)
    assert np.all(arrays[FANO_FACTOR_NAME][~result.fano_available] == 0.0)
    assert all(np.all(np.isfinite(value)) for value in arrays.values())
    assert arrays[AUTOCORRELATION_NAME].dtype == np.dtype(np.float64)
    assert arrays["f16_pair_count"].dtype == np.dtype(np.int64)
    assert arrays[_LAG_MASK].dtype == np.dtype(np.uint8)
    for reference in mapped.array_refs:
        assert validate_unit_name(reference.array_id, reference.unit) is None

    table = tables[MEMORY_TABLE_ID]
    metadata = dict(zip((column.name for column in table.columns), table.rows[0], strict=True))
    assert metadata["lag_sample_convention"] == LAG_SAMPLE_CONVENTION
    assert metadata["mad_convention"] == MAD_CONVENTION
    assert metadata["acf_aggregation"] == ACF_AGGREGATION
    assert metadata["analyzed_segment_convention"] == ANALYZED_SEGMENT_CONVENTION
    assert metadata["count_window_convention"] == COUNT_WINDOW_CONVENTION
    assert metadata["claim_boundary"] == CLAIM_BOUNDARY
    _assert_result_equal(restored, result)


def _available() -> F16Result:
    """Доступная F16-фикстура: все lags и четыре Fano scales поддержаны."""
    count_mean = np.asarray([1.0, 0.5, 0.25, 0.2], dtype=np.float64)
    count_variance = np.asarray([2.0, 1.5, 1.0, 0.5], dtype=np.float64)
    return F16Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        lag_s=np.asarray([0.0001, 0.001, 0.01, 0.02, 0.1, 0.5], dtype=np.float64),
        autocorrelation=np.asarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], dtype=np.float64),
        pair_count=np.asarray([120, 130, 140, 150, 160, 170], dtype=np.int64),
        lag_available=np.ones(6, dtype=np.bool_),
        recurrence_radius_mad=np.asarray([0.5, 1.0, 2.0], dtype=np.float64),
        recurrence_rate=np.linspace(0.0, 1.0, 18, dtype=np.float64).reshape(6, 3),
        count_window_s=np.asarray([0.02, 0.1, 0.5, 1.0], dtype=np.float64),
        count_window_count=np.asarray([20, 20, 20, 10], dtype=np.int64),
        count_mean=count_mean,
        count_variance=count_variance,
        fano_factor=count_variance / count_mean,
        count_window_available=np.ones(4, dtype=np.bool_),
        fano_available=np.ones(4, dtype=np.bool_),
        sample_count=240_000,
        qualified_sample_count=240_000,
        analyzed_segment_count=1,
        event_count=37,
    )


def _canonical_sparse() -> F16Result:
    """Канон 2.4 s: 119/23/4/2 окон, поэтому Fano supported только 2/4."""
    count_mean = np.asarray([8.0 / 119.0, 4.0 / 23.0, np.nan, np.nan], dtype=np.float64)
    count_variance = np.asarray([0.5, 0.25, np.nan, np.nan], dtype=np.float64)
    return F16Result(
        status=Status.PARTIAL,
        reason_codes=(INSUFFICIENT_COUNT_WINDOWS,),
        lag_s=np.asarray([0.0001, 0.001, 0.01, 0.02, 0.1, 0.5], dtype=np.float64),
        autocorrelation=np.asarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], dtype=np.float64),
        pair_count=np.asarray(
            [239_999, 239_990, 239_900, 239_800, 239_000, 235_000], dtype=np.int64
        ),
        lag_available=np.ones(6, dtype=np.bool_),
        recurrence_radius_mad=np.asarray([0.5, 1.0, 2.0], dtype=np.float64),
        recurrence_rate=np.linspace(0.0, 1.0, 18, dtype=np.float64).reshape(6, 3),
        count_window_s=np.asarray([0.02, 0.1, 0.5, 1.0], dtype=np.float64),
        count_window_count=np.asarray([119, 23, 4, 2], dtype=np.int64),
        count_mean=count_mean,
        count_variance=count_variance,
        fano_factor=np.asarray(
            [0.5 / (8.0 / 119.0), 0.25 / (4.0 / 23.0), np.nan, np.nan],
            dtype=np.float64,
        ),
        count_window_available=np.asarray([True, True, False, False], dtype=np.bool_),
        fano_available=np.asarray([True, True, False, False], dtype=np.bool_),
        sample_count=240_000,
        qualified_sample_count=240_000,
        analyzed_segment_count=1,
        event_count=12,
    )


def _unavailable() -> F16Result:
    """UNAVAILABLE сохраняет внешний sample/event count, но публикует пустые domains."""
    return F16Result(
        status=Status.UNAVAILABLE,
        reason_codes=(SCALE_ZERO,),
        lag_s=np.empty(0, dtype=np.float64),
        autocorrelation=np.empty(0, dtype=np.float64),
        pair_count=np.empty(0, dtype=np.int64),
        lag_available=np.empty(0, dtype=np.bool_),
        recurrence_radius_mad=np.empty(0, dtype=np.float64),
        recurrence_rate=np.empty(0, dtype=np.float64),
        count_window_s=np.empty(0, dtype=np.float64),
        count_window_count=np.empty(0, dtype=np.int64),
        count_mean=np.empty(0, dtype=np.float64),
        count_variance=np.empty(0, dtype=np.float64),
        fano_factor=np.empty(0, dtype=np.float64),
        count_window_available=np.empty(0, dtype=np.bool_),
        fano_available=np.empty(0, dtype=np.bool_),
        sample_count=240_000,
        qualified_sample_count=0,
        analyzed_segment_count=0,
        event_count=7,
    )


def _without_validation(result: F16Result, **fields: object) -> F16Result:
    """Обойти только dataclass-валидацию для проверки mapper-шов."""
    broken = object.__new__(F16Result)
    for field in dataclasses.fields(F16Result):
        object.__setattr__(broken, field.name, getattr(result, field.name))
    for name, value in fields.items():
        object.__setattr__(broken, name, value)
    return broken


def _round_trip(
    result: F16Result,
) -> tuple[F16Result, dict[str, np.ndarray], dict[str, TableBlock]]:
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
    restored = decode_f16_result(loaded.bundle.families[F16_INDEX], loaded.arrays, loaded.tables)
    return restored, dict(loaded.arrays), dict(loaded.tables)


def test_available_f16_round_trips_every_field_dtype_and_orientation() -> None:
    """Available F16 сохраняет все поля; recurrence остаётся lag-major 6×3."""
    result = _available()
    mapped, arrays, _ = _build(result)
    restored, loaded_arrays, _ = _round_trip(result)

    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert arrays[RECURRENCE_RATE_NAME].shape == (6, 3)
    assert loaded_arrays[RECURRENCE_RATE_NAME].shape == (6, 3)
    assert loaded_arrays[RECURRENCE_RATE_NAME].dtype == np.dtype(np.float64)
    assert loaded_arrays["f16_pair_count"].dtype == np.dtype(np.int64)
    assert loaded_arrays[_LAG_MASK].dtype == np.dtype(np.uint8)
    _assert_result_equal(restored, result)


def test_persisted_measurement_rejects_finite_value_outside_mask() -> None:
    """Masked-out cell обязан быть ровно declared fill 0.0."""
    mapped, arrays, tables = _build(_partial())
    changed = dict(arrays)
    values = changed[AUTOCORRELATION_NAME].copy()
    values[1] = 0.25
    changed[AUTOCORRELATION_NAME] = values

    with pytest.raises(CharacterizationError, match="zero-under-mask"):
        decode_f16_result(mapped, changed, tables)


@pytest.mark.parametrize(
    "array_id",
    [
        AUTOCORRELATION_NAME,
        RECURRENCE_RATE_NAME,
        COUNT_MEAN_NAME,
        COUNT_VARIANCE_NAME,
        FANO_FACTOR_NAME,
    ],
)
def test_nonfinite_persisted_measurement_is_rejected_by_codec(array_id: str) -> None:
    """Ни один persisted F16 measurement array не принимает NaN."""
    mapped, arrays, tables = _build(_partial())
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


def test_wrong_recipe_slot_method_version_or_declaration_is_rejected() -> None:
    """Mapper принимает только frozen F16 slot 15 и exact recipe surface."""
    result = _available()
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=_recipe().families[F16_INDEX - 1])
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=dataclasses.replace(_family(), method="wrong_method"))
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=dataclasses.replace(_family(), method_version=2))
    parameters = tuple(
        ("autocovariance", "population") if name == "autocovariance" else (name, value)
        for name, value in _family().parameters
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result, family=dataclasses.replace(_family(), parameters=parameters))


def test_misaligned_engine_arrays_are_rejected_without_reshape() -> None:
    """Locked geometry проверяется до persistence; транспонирование запрещено."""
    result = _partial()
    cases = (
        _without_validation(result, recurrence_rate=np.zeros((3, 6), dtype=np.float64)),
        _without_validation(result, count_mean=np.zeros(3, dtype=np.float64)),
        _without_validation(result, lag_available=np.ones(5, dtype=np.bool_)),
        _without_validation(
            result,
            lag_s=np.asarray([0.0001, 0.001, 0.01, 0.02, 0.1, 0.6], dtype=np.float64),
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_wrong_shape_persisted_mask_is_rejected() -> None:
    """Codec и F16 decoder отвергают mask, не совпадающий с value array."""
    mapped, arrays, tables = _build(_partial())
    changed = dict(arrays)
    changed[_LAG_MASK] = np.ones(5, dtype=np.uint8)
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, changed, tables)

    with pytest.raises(CharacterizationError, match="array_mask"):
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    with pytest.raises(CharacterizationError, match="mask"):
        decode_f16_result(mapped, changed, tables)


def test_broken_pair_window_event_and_segment_accounting_is_rejected() -> None:
    """Persisted support и masks не принимают несогласованные engine counters."""
    result = _partial()
    cases = (
        _without_validation(result, event_count=-1),
        _without_validation(result, qualified_sample_count=240_001),
        _without_validation(result, analyzed_segment_count=0),
        _without_validation(result, analyzed_segment_count=240_001),
        _without_validation(
            result, pair_count=np.asarray([120, -1, 130, 140, 150, 0], dtype=np.int64)
        ),
        _without_validation(
            result,
            count_window_count=np.asarray([119, 23, -4, 2], dtype=np.int64),
        ),
        _without_validation(result, lag_available=np.ones(6, dtype=np.bool_)),
        _without_validation(
            result,
            count_window_available=np.asarray([False, True, False, False], dtype=np.bool_),
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_reason_vocabulary_order_duplicates_and_status_matrix_are_rejected() -> None:
    """Codes closed, sorted, unique; status matrix и terminal reasons строги."""
    available = _available()
    unavailable = _unavailable()
    cases = (
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(LAG_ABOVE_SUPPORT, INSUFFICIENT_PAIRS),
        ),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(INSUFFICIENT_PAIRS, INSUFFICIENT_PAIRS),
        ),
        _without_validation(available, status=Status.PARTIAL, reason_codes=("not_computed",)),
        _without_validation(available, reason_codes=(INSUFFICIENT_PAIRS,)),
        _without_validation(available, status=Status.PARTIAL, reason_codes=()),
        _without_validation(unavailable, reason_codes=()),
        _without_validation(unavailable, lag_s=available.lag_s.copy()),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(PHASE_REFERENCE_UNAVAILABLE,),
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)
    assert {INSUFFICIENT_PAIRS, SCALE_ZERO} <= set(DECLARED_CODES)


def test_unavailable_publishes_no_domains_and_round_trips_codec() -> None:
    """UNAVAILABLE не публикует axes, arrays, tables или summaries."""
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
    assert mapped.reason_codes == (SCALE_ZERO,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert arrays == {}
    assert tables == {}
    assert loaded.bundle.families[F16_INDEX] == mapped
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}


def test_canonical_two_of_four_masked_fano_scales_remain_visible() -> None:
    """2.4 s record даёт 4 и 2 окна; оба Fano scales masked и код видим."""
    result = _canonical_sparse()
    mapped, arrays, tables = _build(result)
    restored, _, _ = _round_trip(result)

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (INSUFFICIENT_COUNT_WINDOWS,)
    assert arrays["f16_count_window_count"].tolist() == [119, 23, 4, 2]
    assert arrays[_COUNT_MASK].tolist() == [1, 1, 0, 0]
    assert arrays[_FANO_MASK].tolist() == [1, 1, 0, 0]
    assert np.all(arrays[FANO_FACTOR_NAME][2:] == 0.0)
    assert np.all(np.isnan(restored.fano_factor[2:]))
    validate_f16_result(restored)
    assert tables[MEMORY_TABLE_ID].rows[0][-1] == CLAIM_BOUNDARY

    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(result, reason_codes=()))
    with pytest.raises(CharacterizationError, match="declared reason"):
        _build(_without_validation(result, reason_codes=(INSUFFICIENT_PAIRS,)))


def test_claim_metadata_tamper_is_rejected() -> None:
    """Claim boundary и conventions нельзя пересказать в persisted table."""
    mapped, arrays, tables = _build(_partial())
    table = tables[MEMORY_TABLE_ID]
    row = list(table.rows[0])
    row[-1] = "population causation established"
    changed = dict(tables)
    changed[MEMORY_TABLE_ID] = dataclasses.replace(table, rows=(tuple(row),))

    with pytest.raises(CharacterizationError, match="metadata"):
        decode_f16_result(mapped, arrays, changed)


def test_persisted_summary_accounting_must_match_support() -> None:
    """Persisted qualified count не может расходиться с FamilyResult support."""
    mapped, arrays, tables = _build(_partial())
    summaries = tuple(
        dataclasses.replace(item, value=item.value + 1.0)
        if item.name == "f16_qualified_sample_count"
        else item
        for item in mapped.comparison_summary
    )
    broken = dataclasses.replace(mapped, comparison_summary=summaries)

    with pytest.raises(CharacterizationError, match="accounting"):
        decode_f16_result(broken, arrays, tables)
