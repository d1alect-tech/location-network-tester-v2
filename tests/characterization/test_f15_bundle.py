"""F15 persistence mapper tests."""

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
    Unit,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f15_bundle import F15_ID, F15_INDEX, build_f15_family
from lnt.characterization.f15_result import (
    FEATURE_NAMES,
    FEATURE_UNITS,
    INSUFFICIENT_WINDOWS,
    LABEL_LIMIT,
    METHOD,
    STABILITY_BLOCK_TOO_SHORT,
    F15Result,
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
_ROWS: Final = 8
_ARRAY_IDS: Final = (
    "f15_feature_medians",
    "f15_feature_mads",
    "f15_standardized_features",
    "f15_window_indices",
    "f15_medoid_indices",
    "f15_medoid_features",
    "f15_medoid_rms_v",
    "f15_labels",
    "f15_dwell_labels",
    "f15_dwell_durations_s",
    "f15_transition_counts",
    "f15_transition_probabilities",
    "f15_stability_ari",
)
_TABLE_ID: Final = "f15_feature_metadata"


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F15_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _available() -> F15Result:
    labels = np.asarray([0, 1, 2, 3, 0, 1, 2, 3], dtype=np.int64)
    counts = np.zeros((4, 4), dtype=np.int64)
    counts[0, 1] = 2
    counts[1, 2] = 2
    counts[2, 3] = 2
    counts[3, 0] = 1
    probabilities = counts.astype(np.float64) / np.sum(counts, axis=1, keepdims=True)
    return F15Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        window_s=0.02,
        feature_names=FEATURE_NAMES,
        feature_medians=np.arange(1.0, 8.0),
        feature_mads=np.ones(7, dtype=np.float64),
        standardized_features=np.arange(_ROWS * 7, dtype=np.float64).reshape(_ROWS, 7),
        window_indices=np.arange(10, 18, dtype=np.int64),
        medoid_indices=np.asarray([11, 13, 15, 17], dtype=np.int64),
        medoid_features=np.arange(28, dtype=np.float64).reshape(4, 7),
        medoid_rms_v=np.asarray([1.0, 2.0, 3.0, 4.0]),
        labels=labels,
        dwell_labels=labels.copy(),
        dwell_durations_s=np.full(_ROWS, 0.02),
        transition_counts=counts,
        transition_probabilities=probabilities,
        stability_ari=np.asarray([1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]),
        swap_passes=7,
        complete_window_count=_ROWS,
        qualified_window_count=_ROWS,
        unretained_window_count=0,
    )


def _build(
    result: F15Result,
    *,
    family: CharacterizationFamily | None = None,
    measured_channel: str = "ch1",
    record_duration_s: float = _RECORD_S,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f15_family(
        result,
        _family() if family is None else family,
        _band(),
        measured_channel=measured_channel,
        record_duration_s=record_duration_s,
    )


def test_f15_bundle_slot_is_declared() -> None:
    """F15 owns slot fourteen in the frozen family order."""
    assert F15_INDEX == 14
    assert F15_ID == "f15_interpretable_modes"
    assert FAMILY_IDS[F15_INDEX] == F15_ID
    assert _recipe().families[F15_INDEX].method == METHOD


def test_available_publishes_arrays_and_feature_metadata() -> None:
    """Available F15 publishes every numeric field plus ordered feature metadata."""
    result = _available()
    mapped, arrays, tables = _build(result)
    by_id = {ref.array_id: ref for ref in mapped.array_refs}

    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert mapped.units == (Unit.V, Unit.RATIO, Unit.COUNT, Unit.S)
    assert tuple(ref.array_id for ref in mapped.array_refs) == _ARRAY_IDS
    assert mapped.table_refs[0].table_id == _TABLE_ID
    assert set(tables) == {_TABLE_ID}
    assert "f15_transitions" not in tables
    assert tuple(row[1] for row in tables[_TABLE_ID].rows) == FEATURE_NAMES
    assert tuple(row[2] for row in tables[_TABLE_ID].rows) == tuple(
        unit.value for unit in FEATURE_UNITS
    )
    for array_id in _ARRAY_IDS:
        assert by_id[array_id].shape == arrays[array_id].shape
        assert by_id[array_id].dtype == arrays[array_id].dtype.name
    assert np.array_equal(arrays["f15_feature_medians"], result.feature_medians)
    assert np.array_equal(arrays["f15_standardized_features"], result.standardized_features)
    assert np.array_equal(arrays["f15_transition_counts"], result.transition_counts)
    assert np.array_equal(arrays["f15_stability_ari"], result.stability_ari)


def _unavailable() -> F15Result:
    return F15Result(
        status=Status.UNAVAILABLE,
        reason_codes=(INSUFFICIENT_WINDOWS,),
        window_s=0.02,
        feature_names=FEATURE_NAMES,
        feature_medians=np.empty(0, dtype=np.float64),
        feature_mads=np.empty(0, dtype=np.float64),
        standardized_features=np.empty((0, 7), dtype=np.float64),
        window_indices=np.empty(0, dtype=np.int64),
        medoid_indices=np.empty(0, dtype=np.int64),
        medoid_features=np.empty((0, 7), dtype=np.float64),
        medoid_rms_v=np.empty(0, dtype=np.float64),
        labels=np.empty(0, dtype=np.int64),
        dwell_labels=np.empty(0, dtype=np.int64),
        dwell_durations_s=np.empty(0, dtype=np.float64),
        transition_counts=np.empty((0, 0), dtype=np.int64),
        transition_probabilities=np.empty((0, 0), dtype=np.float64),
        stability_ari=np.empty(0, dtype=np.float64),
        swap_passes=0,
        complete_window_count=12,
        qualified_window_count=0,
        unretained_window_count=12,
    )


def test_unavailable_publishes_no_outputs() -> None:
    """Unavailable F15 keeps empty domains and zero support."""
    mapped, arrays, tables = _build(_unavailable())

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (INSUFFICIENT_WINDOWS,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert arrays == {}
    assert tables == {}
    assert mapped.support.sample_count == 0
    assert mapped.support.observation_count == 0
    assert mapped.support.stored_count == 0
    assert mapped.support.duration_s == 0.0


def test_partial_publishes_one_mask_per_array_with_exact_shape() -> None:
    """Partial F15 declares validity for every numeric domain."""
    result = dataclasses.replace(
        _available(),
        status=Status.PARTIAL,
        reason_codes=(STABILITY_BLOCK_TOO_SHORT,),
        stability_ari=np.empty(0, dtype=np.float64),
    )
    mapped, arrays, _ = _build(result)

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (STABILITY_BLOCK_TOO_SHORT,)
    for ref in mapped.array_refs:
        mask_id = ref.validity_mask_id
        assert mask_id == f"{ref.array_id}_valid"
        assert mask_id is not None
        assert arrays[mask_id].dtype == np.uint8
        assert arrays[mask_id].shape == ref.shape
    assert arrays["f15_stability_ari"].shape == (0,)
    assert arrays["f15_stability_ari_valid"].shape == (0,)


def _full_bundle(
    mapped: FamilyResult,
    arrays: dict[str, np.ndarray],
    tables: dict[str, TableBlock],
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    recipe = _recipe()
    band = _band()
    families = tuple(
        mapped if index == F15_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def test_family_arrays_and_feature_table_round_trip_through_codec() -> None:
    """F15 preserves every published field, shape, dtype, and table row."""
    mapped, arrays, tables = _build(_available())
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, arrays, tables)
    files = encode_bundle(
        bundle,
        bundle_arrays,
        bundle_tables,
        max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
    )

    loaded = load_bundle(files)

    assert loaded.bundle.families[F15_INDEX] == mapped
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert loaded.arrays[array_id].shape == values.shape
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables
    assert loaded.tables["f15_feature_metadata"].rows == tables["f15_feature_metadata"].rows


def _without_result_validation(result: F15Result, **fields: object) -> F15Result:
    broken = object.__new__(F15Result)
    for field in dataclasses.fields(F15Result):
        object.__setattr__(broken, field.name, getattr(result, field.name))
    for name, value in fields.items():
        object.__setattr__(broken, name, value)
    return broken


def test_unsorted_or_duplicated_reasons_are_rejected() -> None:
    """Mapper rejects reason order and duplicates even if engine validation is bypassed."""
    for reasons in (
        ("label_limit", "empty_cluster"),
        ("label_limit", "label_limit"),
    ):
        broken = _without_result_validation(
            _available(), status=Status.PARTIAL, reason_codes=reasons
        )
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_available_partial_and_unavailable_status_invariants_are_rejected() -> None:
    """Status and reason combinations are checked at persistence seam."""
    cases = (
        _without_result_validation(_available(), reason_codes=("label_limit",)),
        _without_result_validation(_available(), status=Status.PARTIAL, reason_codes=()),
        _without_result_validation(_unavailable(), status=Status.UNAVAILABLE, reason_codes=()),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_wrong_recipe_slot_is_rejected() -> None:
    """Mapper accepts F15 only in its frozen recipe slot."""
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=_recipe().families[F15_INDEX - 1])


def test_misaligned_array_is_rejected() -> None:
    """A field with a different declared shape fails instead of being reshaped."""
    broken = _without_result_validation(
        _available(), standardized_features=np.zeros((_ROWS - 1, 7), dtype=np.float64)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_broken_transition_accounting_is_rejected() -> None:
    """Published transition counts must be derived from stored labels."""
    broken = _without_result_validation(
        _available(), transition_counts=np.zeros((4, 4), dtype=np.int64)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_broken_dwell_length_is_rejected_as_declared_not_raw_broadcast() -> None:
    """Пустой массив длительностей даёт объявленную ошибку, а не сырой ValueError.

    ``np.allclose`` broadcast'ит ``(1,)`` против ``(N,)``, поэтому длина 1 здесь
    ничего не доказывает; пустой массив против непустого несовместим и бросает
    broadcast-``ValueError``. Непойманное исключение на границе бандла
    уничтожило бы весь прогон характеризации, а не одно семейство. Проверка формы
    стоит первым условием там же, как в ``f14_arrays.py:183``, поэтому короткое
    замыкание происходит до ``allclose``. Пустой массив недоступен для AVAILABLE:
    ``labels.size == 0`` отвергнут выше, значит ожидаемых длительностей всегда
    хотя бы одна.
    """
    broken = _without_result_validation(
        _available(), dwell_durations_s=np.zeros(0, dtype=np.float64)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_wrong_shape_validity_mask_is_rejected_by_codec() -> None:
    """A partial mask cannot have a different shape than its array reference."""
    result = dataclasses.replace(
        _available(),
        status=Status.PARTIAL,
        reason_codes=(STABILITY_BLOCK_TOO_SHORT,),
        stability_ari=np.empty(0, dtype=np.float64),
    )
    mapped, arrays, tables = _build(result)
    arrays["f15_labels_valid"] = np.ones(_ROWS + 1, dtype=np.uint8)
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, arrays, tables)
    with pytest.raises(CharacterizationError, match="array_mask"):
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )


def _capped() -> F15Result:
    rows = 4096
    labels = np.repeat(np.asarray([0, 1, 2, 3], dtype=np.int64), rows // 4)
    counts = np.zeros((4, 4), dtype=np.int64)
    np.add.at(counts, (labels[:-1], labels[1:]), 1)
    totals = np.sum(counts, axis=1, keepdims=True)
    probabilities = np.divide(
        counts, totals, out=np.zeros_like(counts, dtype=np.float64), where=totals != 0
    )
    return F15Result(
        status=Status.PARTIAL,
        reason_codes=(LABEL_LIMIT,),
        window_s=0.02,
        feature_names=FEATURE_NAMES,
        feature_medians=np.arange(1.0, 8.0),
        feature_mads=np.ones(7, dtype=np.float64),
        standardized_features=np.zeros((rows, 7), dtype=np.float64),
        window_indices=np.arange(rows, dtype=np.int64),
        medoid_indices=np.asarray([1, 3, 5, 7], dtype=np.int64),
        medoid_features=np.arange(28, dtype=np.float64).reshape(4, 7),
        medoid_rms_v=np.asarray([1.0, 2.0, 3.0, 4.0]),
        labels=labels,
        dwell_labels=np.asarray([0, 1, 2, 3], dtype=np.int64),
        dwell_durations_s=np.full(4, 1024.0 * 0.02),
        transition_counts=counts,
        transition_probabilities=probabilities,
        stability_ari=np.ones(8, dtype=np.float64),
        swap_passes=2,
        complete_window_count=rows + 1,
        qualified_window_count=rows,
        unretained_window_count=1,
    )


def test_label_cap_is_declared_in_support_and_summaries() -> None:
    """The 4096-label cap stays visible; no fabricated rows or padded values appear."""
    mapped, arrays, _ = _build(_capped(), record_duration_s=100.0)
    summary = {item.name: item.value for item in mapped.comparison_summary}

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (LABEL_LIMIT,)
    assert arrays["f15_labels"].shape == (4096,)
    assert mapped.support.sample_count == 4097
    assert mapped.support.observation_count == 4096
    assert mapped.support.missing_count == 1
    assert mapped.support.stored_count == 4096
    assert mapped.support.selection_rule == "even_floor_index"
    assert summary["f15_stored_label_count"] == 4096.0
    assert summary["f15_maximum_labels"] == 4096.0
    assert summary["f15_unretained_window_count"] == 1.0


def test_partial_masks_round_trip_through_codec() -> None:
    """Partial masks and feature metadata survive the three-file codec."""
    result = dataclasses.replace(
        _available(),
        status=Status.PARTIAL,
        reason_codes=(STABILITY_BLOCK_TOO_SHORT,),
        stability_ari=np.empty(0, dtype=np.float64),
    )
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

    assert loaded.bundle.families[F15_INDEX] == mapped
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables


def test_array_units_and_dtypes_follow_declared_vocabulary() -> None:
    """Every array reference has matching dtype, shape, and valid unit name."""
    result = _available()
    mapped, arrays, _ = _build(result)
    for ref in mapped.array_refs:
        validate_unit_name(ref.array_id, ref.unit)
        assert ref.dtype == arrays[ref.array_id].dtype.name
        assert ref.shape == arrays[ref.array_id].shape
    assert arrays["f15_window_indices"].dtype == np.int64
    assert arrays["f15_labels"].dtype == np.int64
    assert arrays["f15_medoid_rms_v"].dtype == np.float64
    assert arrays["f15_dwell_durations_s"].dtype == np.float64
    assert arrays["f15_transition_counts"].dtype == np.int64


def test_channel_selects_persisted_signal_plane() -> None:
    """Measured channel selects F15 envelope signal plane."""
    assert _build(_available(), measured_channel="ch2")[0].signal_plane == (
        "ch2_transformer_secondary"
    )
    assert _build(_available())[0].signal_plane == "ch1_scope_input"


def test_broken_window_and_label_accounting_is_rejected() -> None:
    """Support, dwell, and probability relationships must agree with labels."""
    broken = (
        _without_result_validation(_available(), unretained_window_count=1),
        _without_result_validation(_available(), qualified_window_count=_ROWS - 1),
        _without_result_validation(
            _available(), dwell_durations_s=np.full(_ROWS, 0.04, dtype=np.float64)
        ),
        _without_result_validation(
            _available(), transition_probabilities=np.zeros((4, 4), dtype=np.float64)
        ),
    )
    for result in broken:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(result)


def test_undeclared_reason_code_is_rejected() -> None:
    """Reason vocabulary is closed at persistence seam."""
    broken = _without_result_validation(
        _available(), status=Status.PARTIAL, reason_codes=("not_computed",)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_window_duration_is_f15_window_not_record_duration() -> None:
    """Envelope window keeps 20 ms geometry while support covers complete windows."""
    mapped = _build(_available())[0]
    assert mapped.window.kind == "fixed"
    assert mapped.window.duration_s == 0.02
    assert mapped.window.sample_count is None
    assert mapped.window.overlap_fraction == 0.0
    assert mapped.support.end_s == pytest.approx(0.16)


def test_unavailable_round_trips_without_outputs() -> None:
    """Unavailable F15 codec path preserves reason and publishes no arrays."""
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
    assert loaded.bundle.families[F15_INDEX] == mapped
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}
