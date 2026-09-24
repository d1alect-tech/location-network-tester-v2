"""Persistence tests for bidirectional F14 event association."""

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
from lnt.characterization.f14_bundle import F14_ID, F14_INDEX, build_f14_family
from lnt.characterization.f14_contract import (
    BASELINE_PROBABILITY_NAME,
    CHANNEL_MISSING,
    CLAIM_BOUNDARY,
    DECLARED_CODES,
    EVENT_LIMIT,
    EVENT_PROBABILITY_NAME,
    GAPS_PRESENT,
    INSUFFICIENT_TRIGGERS,
    LAG_SIGN_CONVENTION,
    MEAN_WAVEFORM_NAME,
    NEAREST_LAG_NAME,
)
from lnt.characterization.f14_result import F14DirectionResult, F14Result
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band, validate_unit_name
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RECORD_S: Final = 2.4
_AXIS: Final = np.linspace(-0.02, 0.02, 401, dtype=np.float64)
_SHIFTS: Final = np.arange(1, 33, dtype=np.int64)
_TABLE_ID: Final = "f14_direction_metadata"
_ARRAY_IDS: Final = (
    "f14_direction_index",
    "f14_relative_time_s",
    "f14_cycle_shift_offsets",
    MEAN_WAVEFORM_NAME,
    EVENT_PROBABILITY_NAME,
    NEAREST_LAG_NAME,
    BASELINE_PROBABILITY_NAME,
    "f14_baseline_low",
    "f14_baseline_high",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F14_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _direction(
    trigger_channel: str,
    response_channel: str,
    *,
    total: int,
    qualified: int,
    stored: int,
    boundary: int,
    gaps: int,
    truncated: int,
    mean: float,
    probability: float,
    lags: np.ndarray,
) -> F14DirectionResult:
    baseline = np.repeat(
        probability + np.arange(32, dtype=np.float64)[:, None] / 1000.0,
        401,
        axis=1,
    )
    return F14DirectionResult(
        trigger_channel=trigger_channel,
        response_channel=response_channel,
        total_event_count=total,
        qualified_trigger_count=qualified,
        stored_trigger_count=stored,
        omitted_trigger_count=qualified - stored,
        boundary_trigger_count=boundary,
        gap_crossing_trigger_count=gaps,
        window_truncated_count=truncated,
        mean_waveform_v=np.full(401, mean, dtype=np.float64),
        event_probability=np.full(401, probability, dtype=np.float64),
        nearest_lag_s=lags,
        baseline_probability=baseline,
        baseline_low=np.min(baseline, axis=0),
        baseline_high=np.max(baseline, axis=0),
    )


def _available() -> F14Result:
    return F14Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        relative_time_s=_AXIS.copy(),
        directions=(
            _direction(
                "ch1",
                "ch2",
                total=25,
                qualified=20,
                stored=20,
                boundary=2,
                gaps=1,
                truncated=2,
                mean=0.25,
                probability=0.4,
                lags=np.asarray([0.001, -0.002, 0.003, -0.004], dtype=np.float64),
            ),
            _direction(
                "ch2",
                "ch1",
                total=30,
                qualified=20,
                stored=20,
                boundary=4,
                gaps=3,
                truncated=3,
                mean=-0.5,
                probability=0.6,
                lags=np.asarray([-0.001, 0.002, -0.003, 0.004, -0.005], dtype=np.float64),
            ),
        ),
        sample_count=1_000,
        qualified_cycle_count=40,
    )


def _build(
    result: F14Result,
    *,
    family: CharacterizationFamily | None = None,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f14_family(
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
        mapped if index == F14_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def test_available_f14_round_trips_all_directions_and_metadata() -> None:
    """The public mapper preserves both directional domains and the lag boundary."""
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

    assert mapped.family_id == F14_ID
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert mapped.signal_plane.value == "cross_channel_measured_planes"
    assert tuple(reference.array_id for reference in mapped.array_refs) == _ARRAY_IDS
    assert set(tables) == {_TABLE_ID}
    assert len(tables[_TABLE_ID].rows) == 2
    assert tuple(row[0] for row in tables[_TABLE_ID].rows) == (0, 1)
    assert tuple(row[1:3] for row in tables[_TABLE_ID].rows) == (
        ("ch1", "ch2"),
        ("ch2", "ch1"),
    )
    assert loaded.bundle.families[F14_INDEX] == mapped
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert loaded.arrays[array_id].shape == values.shape
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables
    assert np.array_equal(arrays[MEAN_WAVEFORM_NAME][0], result.directions[0].mean_waveform_v)
    assert np.array_equal(arrays[EVENT_PROBABILITY_NAME][1], result.directions[1].event_probability)
    assert np.array_equal(
        arrays[NEAREST_LAG_NAME],
        np.concatenate([result.directions[0].nearest_lag_s, result.directions[1].nearest_lag_s]),
    )
    assert np.array_equal(arrays["f14_nearest_lag_offsets"], np.asarray([0, 4, 9]))
    assert np.array_equal(arrays["f14_relative_time_s"], _AXIS)
    assert np.array_equal(arrays["f14_cycle_shift_offsets"], _SHIFTS)
    assert tuple(
        validate_unit_name(reference.array_id, reference.unit) for reference in mapped.array_refs
    ) == (None,) * len(_ARRAY_IDS)


def _without_validation(result: F14Result, **fields: object) -> F14Result:
    """Обойти только dataclass-валидацию, чтобы проверить mapper-шов."""
    broken = object.__new__(F14Result)
    for field in dataclasses.fields(F14Result):
        object.__setattr__(broken, field.name, getattr(result, field.name))
    for name, value in fields.items():
        object.__setattr__(broken, name, value)
    return broken


def _empty_direction(trigger: str, response: str) -> F14DirectionResult:
    return F14DirectionResult(
        trigger_channel=trigger,
        response_channel=response,
        total_event_count=0,
        qualified_trigger_count=0,
        stored_trigger_count=0,
        omitted_trigger_count=0,
        boundary_trigger_count=0,
        gap_crossing_trigger_count=0,
        window_truncated_count=0,
        mean_waveform_v=np.empty(0, dtype=np.float64),
        event_probability=np.empty(0, dtype=np.float64),
        nearest_lag_s=np.empty(0, dtype=np.float64),
        baseline_probability=np.empty((0, 0), dtype=np.float64),
        baseline_low=np.empty(0, dtype=np.float64),
        baseline_high=np.empty(0, dtype=np.float64),
    )


def _unavailable() -> F14Result:
    return F14Result(
        status=Status.UNAVAILABLE,
        reason_codes=(CHANNEL_MISSING,),
        relative_time_s=np.empty(0, dtype=np.float64),
        directions=(_empty_direction("ch1", "ch2"), _empty_direction("ch2", "ch1")),
        sample_count=0,
        qualified_cycle_count=0,
    )


def _unavailable_with_counts() -> F14Result:
    first = dataclasses.replace(
        _empty_direction("ch1", "ch2"),
        total_event_count=8,
        qualified_trigger_count=3,
        omitted_trigger_count=3,
        boundary_trigger_count=2,
        gap_crossing_trigger_count=1,
        window_truncated_count=2,
    )
    second = dataclasses.replace(
        _empty_direction("ch2", "ch1"),
        total_event_count=6,
        qualified_trigger_count=2,
        omitted_trigger_count=2,
        boundary_trigger_count=1,
        gap_crossing_trigger_count=1,
        window_truncated_count=2,
    )
    return F14Result(
        status=Status.UNAVAILABLE,
        reason_codes=(INSUFFICIENT_TRIGGERS,),
        relative_time_s=np.empty(0, dtype=np.float64),
        directions=(first, second),
        sample_count=1_000,
        qualified_cycle_count=0,
    )


def _capped() -> F14Result:
    result = _available()
    first = dataclasses.replace(
        result.directions[0],
        total_event_count=5_000,
        qualified_trigger_count=4_995,
        stored_trigger_count=4_096,
        omitted_trigger_count=899,
    )
    return dataclasses.replace(
        result,
        status=Status.PARTIAL,
        reason_codes=(EVENT_LIMIT,),
        directions=(first, result.directions[1]),
    )


def test_f14_is_in_frozen_slot_thirteen() -> None:
    """F14 сохраняет frozen ID, метод и позицию рецепта."""
    assert F14_INDEX == 13
    assert F14_ID == "f14_cross_channel_event_association"
    assert FAMILY_IDS[F14_INDEX] == F14_ID
    assert _family().method == "bidirectional_event_triggered_cross_channel_association"


def test_wrong_recipe_slot_or_method_is_rejected() -> None:
    """Mapper принимает только F14 в слоте 13 с frozen method."""
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=_recipe().families[F14_INDEX - 1])
    wrong_method = dataclasses.replace(_family(), method="wrong_method")
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=wrong_method)


def test_misaligned_direction_arrays_are_rejected_without_reshape() -> None:
    """Ни один направленный массив нельзя молча перестроить под ось."""
    result = _available()
    cases = (
        _without_validation(
            result,
            directions=(
                dataclasses.replace(result.directions[0], mean_waveform_v=np.zeros(400)),
                result.directions[1],
            ),
        ),
        _without_validation(
            result,
            directions=(
                dataclasses.replace(result.directions[0], baseline_probability=np.zeros((31, 401))),
                result.directions[1],
            ),
        ),
        _without_validation(
            result,
            directions=(
                dataclasses.replace(result.directions[0], nearest_lag_s=np.zeros((1, 4))),
                result.directions[1],
            ),
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_broken_trigger_and_nearest_accounting_is_rejected() -> None:
    """Mapper проверяет total/qualified/stored/omitted и match count."""
    result = _available()
    first = result.directions[0]
    second = result.directions[1]
    cases = (
        _without_validation(
            result,
            directions=(dataclasses.replace(first, omitted_trigger_count=1), second),
        ),
        _without_validation(
            result,
            directions=(dataclasses.replace(first, stored_trigger_count=21), second),
        ),
        _without_validation(
            result,
            directions=(dataclasses.replace(first, total_event_count=24), second),
        ),
        _without_validation(
            result,
            directions=(dataclasses.replace(first, stored_trigger_count=3), second),
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_reason_vocabulary_and_status_matrix_are_rejected_at_persistence_seam() -> None:
    """Codes остаются declared, sorted, unique и соответствуют status."""
    available = _available()
    unavailable = _unavailable()
    cases = (
        _without_validation(
            available, status=Status.PARTIAL, reason_codes=("gaps_present", "event_limit")
        ),
        _without_validation(
            available, status=Status.PARTIAL, reason_codes=("gaps_present", "gaps_present")
        ),
        _without_validation(available, status=Status.PARTIAL, reason_codes=("not_computed",)),
        _without_validation(available, reason_codes=("event_limit",)),
        _without_validation(available, status=Status.PARTIAL, reason_codes=()),
        _without_validation(unavailable, reason_codes=()),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_unavailable_with_nonempty_domains_is_rejected() -> None:
    """UNAVAILABLE не может нести ось, waveform или baseline."""
    broken = _without_validation(_unavailable(), relative_time_s=_AXIS.copy())
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_unavailable_publishes_empty_arrays_and_tables_and_round_trips() -> None:
    """Unavailable F14 не публикует нулевые домены и проходит codec без outputs."""
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

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (CHANNEL_MISSING,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert arrays == {}
    assert tables == {}
    assert loaded.bundle.families[F14_INDEX] == mapped
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}


def test_unavailable_preserves_accounting_in_memory_but_publishes_no_domains() -> None:
    """UNAVAILABLE может честно считать отказы, не превращая их в outputs."""
    mapped, arrays, tables = _build(_unavailable_with_counts())

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (INSUFFICIENT_TRIGGERS,)
    assert arrays == {}
    assert tables == {}


def test_event_cap_is_visible_without_invented_rows() -> None:
    """Cap 4096 и реальный omitted count остаются в summary и table."""
    result = _capped()
    mapped, arrays, tables = _build(result)
    summaries = {item.name: item.value for item in mapped.comparison_summary}
    rows = tables[_TABLE_ID].rows

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (EVENT_LIMIT,)
    assert EVENT_LIMIT in DECLARED_CODES
    assert summaries["f14_maximum_triggers_per_direction"] == 4_096.0
    assert summaries["f14_omitted_trigger_count"] == 899.0
    assert summaries["f14_stored_trigger_count"] == 4_116.0
    assert rows[0][6] == 899
    assert rows[0][5] == 4_096
    assert arrays[MEAN_WAVEFORM_NAME].shape == (2, 401)
    assert arrays[EVENT_PROBABILITY_NAME].shape == (2, 401)
    assert arrays[BASELINE_PROBABILITY_NAME].shape == (2, 32, 401)


def test_each_direction_keeps_its_own_axis_rows_and_lag_offsets() -> None:
    """Два направления не смешиваются в одну строку и не теряют ragged offsets."""
    result = _available()
    mapped, arrays, tables = _build(result)

    assert mapped.array_refs[0].shape == (2,)
    assert arrays[MEAN_WAVEFORM_NAME].shape == (2, 401)
    assert np.array_equal(arrays[MEAN_WAVEFORM_NAME][0], result.directions[0].mean_waveform_v)
    assert np.array_equal(arrays[MEAN_WAVEFORM_NAME][1], result.directions[1].mean_waveform_v)
    assert np.array_equal(arrays[EVENT_PROBABILITY_NAME][0], result.directions[0].event_probability)
    assert np.array_equal(arrays[EVENT_PROBABILITY_NAME][1], result.directions[1].event_probability)
    assert np.array_equal(arrays["f14_nearest_lag_offsets"], np.asarray([0, 4, 9]))
    assert tuple((row[1], row[2]) for row in tables[_TABLE_ID].rows) == (
        ("ch1", "ch2"),
        ("ch2", "ch1"),
    )


def test_relative_axis_must_match_declared_recipe_range_and_bin_count() -> None:
    """Materialised relative axis не может противоречить locked recipe."""
    broken_axis = np.linspace(-0.01, 0.01, 401, dtype=np.float64)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(_available(), relative_time_s=broken_axis))
    short_axis = _AXIS[:-1]
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(_available(), relative_time_s=short_axis))


def test_lags_outside_declared_window_are_rejected_and_empty_lags_are_not_zero_filled() -> None:
    """Mapper не resurrect-ит lag за окном и сохраняет честный пустой вектор."""
    result = _available()
    outside = dataclasses.replace(result.directions[0], nearest_lag_s=np.asarray([0.03]))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(
            _without_validation(
                result,
                directions=(outside, result.directions[1]),
            )
        )
    empty = tuple(
        dataclasses.replace(direction, nearest_lag_s=np.empty(0, dtype=np.float64))
        for direction in result.directions
    )
    mapped, arrays, _ = _build(_without_validation(result, directions=empty))
    assert mapped.status is Status.AVAILABLE
    assert arrays[NEAREST_LAG_NAME].shape == (0,)
    assert np.array_equal(arrays["f14_nearest_lag_offsets"], np.asarray([0, 0, 0]))
    assert np.count_nonzero(arrays[NEAREST_LAG_NAME]) == 0


def test_partial_masks_and_wrong_shape_mask_are_checked_by_codec() -> None:
    """PARTIAL публикует маски, а codec отвергает маску неверной формы."""
    result = dataclasses.replace(_available(), status=Status.PARTIAL, reason_codes=(GAPS_PRESENT,))
    mapped, arrays, tables = _build(result)
    assert mapped.status is Status.PARTIAL
    for reference in mapped.array_refs:
        mask_id = reference.validity_mask_id
        assert mask_id == f"{reference.array_id}_valid"
        assert mask_id is not None
        assert arrays[mask_id].shape == reference.shape
        assert arrays[mask_id].dtype == np.uint8
    arrays[f"{MEAN_WAVEFORM_NAME}_valid"] = np.ones((2, 400), dtype=np.uint8)
    bundle, all_arrays, all_tables = _full_bundle(mapped, arrays, tables)
    with pytest.raises(CharacterizationError, match="array_mask"):
        encode_bundle(
            bundle,
            all_arrays,
            all_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )


def test_claim_boundary_and_lag_convention_are_persisted_verbatim() -> None:
    """Artifact metadata не позволяет прочитать F14 как причинный или физический lead claim."""
    _, _, tables = _build(_available())
    rows = tables[_TABLE_ID].rows
    assert all(row[13] == LAG_SIGN_CONVENTION for row in rows)
    assert all(row[14] == CLAIM_BOUNDARY for row in rows)
    assert all(row[15] == "earlier_target" for row in rows)
    assert all(row[16] == "exclude_incomplete_windows" for row in rows)
    assert "causality" in CLAIM_BOUNDARY
    assert "physical lead" in CLAIM_BOUNDARY


def test_array_dtypes_and_unit_vocabulary_survive_round_trip() -> None:
    """Каждый F14 array имеет объявленный dtype, форму и валидное имя единицы."""
    mapped, arrays, _ = _build(_available())
    for reference in mapped.array_refs:
        validate_unit_name(reference.array_id, reference.unit)
        assert reference.dtype == arrays[reference.array_id].dtype.name
        assert reference.shape == arrays[reference.array_id].shape
    assert arrays[MEAN_WAVEFORM_NAME].dtype == np.float64
    assert arrays["f14_direction_index"].dtype == np.int64
    assert arrays["f14_cycle_shift_offsets"].dtype == np.int64
    assert arrays["f14_nearest_lag_offsets"].dtype == np.int64


def test_event_limit_reason_is_exactly_aggregate_omitted_state() -> None:
    """reason event_limit нельзя добавить без omission или скрыть omission."""
    result = _capped()
    without_code = _without_validation(result, reason_codes=())
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(without_code)
    without_omission = _without_validation(
        _available(), status=Status.PARTIAL, reason_codes=(EVENT_LIMIT,)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(without_omission)


def test_partial_round_trip_preserves_masks_dtypes_and_table() -> None:
    """PARTIAL artifact сохраняет каждую mask, array dtype и direction table."""
    result = dataclasses.replace(_available(), status=Status.PARTIAL, reason_codes=(GAPS_PRESENT,))
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

    assert loaded.bundle.families[F14_INDEX] == mapped
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert loaded.arrays[array_id].shape == values.shape
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables


def test_unavailable_cannot_carry_a_direction_domain() -> None:
    """Непустой waveform одного UNAVAILABLE направления отвергается mapper-ом."""
    result = _unavailable()
    direction = dataclasses.replace(
        result.directions[0], mean_waveform_v=np.asarray([0.0], dtype=np.float64)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(result, directions=(direction, result.directions[1])))


def test_baseline_low_and_high_must_match_materialised_probability() -> None:
    """Derived baseline boundaries не могут быть подменены произвольными числами."""
    result = _available()
    direction = dataclasses.replace(
        result.directions[0], baseline_low=result.directions[0].baseline_low + 0.1
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(result, directions=(direction, result.directions[1])))


def test_built_result_must_meet_locked_minimum_trigger_count() -> None:
    """Built F14 не публикует fewer-than-20 triggers как available-like output."""
    result = _available()
    direction = dataclasses.replace(
        result.directions[0],
        total_event_count=19,
        qualified_trigger_count=19,
        stored_trigger_count=19,
        omitted_trigger_count=0,
        boundary_trigger_count=0,
        gap_crossing_trigger_count=0,
        window_truncated_count=0,
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_without_validation(result, directions=(direction, result.directions[1])))
