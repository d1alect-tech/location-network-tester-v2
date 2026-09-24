"""Покрытие маппера F09: ручные фикстуры результата, статусы, поддержка, кодек."""

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
from lnt.characterization.f09_bundle import F09_ID, F09_INDEX, build_f09_family
from lnt.characterization.f09_result import (
    BOUNDARY_HANDLING,
    DECLARED_CODES,
    METHOD,
    F09Result,
    Transition,
)
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band, Inference, validate_unit_name
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RECORD_S: Final = 2.4
_DEAD_TIME_S: Final = 0.0001
_START_S: Final = 0.1
_END_S: Final = 0.21
_LABEL_A: Final = "positive|band_low"
_LABEL_B: Final = "negative|band_low"
_LABELS: Final = (_LABEL_A, _LABEL_A, _LABEL_B, _LABEL_B, _LABEL_A, _LABEL_A)
# Шесть событий: три в пачке до 0.110, разрыв 90 мс, три в пачке до 0.210.
_DT: Final = (0.005, 0.005, 0.090, 0.005, 0.005)
_RUNS: Final = (2, 2, 2)
_CLUSTER_STARTS: Final = (0.1, 0.2)
_CLUSTER_SPREADS: Final = (0.010, 0.010)
_CLUSTER_SIZES: Final = (3, 3)
_TRANSITIONS: Final = (
    Transition(source=_LABEL_A, target=_LABEL_A, count=2),
    Transition(source=_LABEL_A, target=_LABEL_B, count=1),
    Transition(source=_LABEL_B, target=_LABEL_B, count=1),
    Transition(source=_LABEL_B, target=_LABEL_A, count=1),
)
_ARRAY_IDS: Final = (
    "f09_dt_s",
    "f09_polarity_run_lengths",
    "f09_cluster_start_s",
    "f09_cluster_spread_s",
    "f09_cluster_sizes",
)
_TABLE_ID: Final = "f09_transitions"
_VOCAB: Final = (
    "insufficient_events",
    "dead_time_overlap",
    "single_cycle_record",
    "gaps_present",
)


def _recipe() -> CharacterizationRecipe:
    """Рецепт-пример из репозитория: семейство F09 берётся по индексу."""
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    """Объявленное семейство F09 из рецепта."""
    return _recipe().families[F09_INDEX]


def _band() -> Band:
    """Полоса анализа из настроек STFT рецепта."""
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _available() -> F09Result:
    """Ручной доступный результат: шесть событий, два кластера, четыре перехода."""
    return F09Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        event_type_fields=("polarity", "dominant_band"),
        event_labels=_LABELS,
        transitions=_TRANSITIONS,
        dt_s=np.array(_DT, dtype=np.float64),
        polarity_run_lengths=np.array(_RUNS, dtype=np.int64),
        cluster_start_s=np.array(_CLUSTER_STARTS, dtype=np.float64),
        cluster_spread_s=np.array(_CLUSTER_SPREADS, dtype=np.float64),
        cluster_sizes=np.array(_CLUSTER_SIZES, dtype=np.int64),
        cluster_count=len(_CLUSTER_SIZES),
        excluded_waiting_interval_count=0,
        omitted_event_count=0,
        boundary_event_count=1,
        unclassified_band_count=0,
        dead_time_s=_DEAD_TIME_S,
        dead_time_rejected_count=2,
        dead_time_omitted_count=0,
        gap_count=1,
        omitted_gap_count=0,
        candidate_count=8,
        boundary_handling=BOUNDARY_HANDLING,
        inference=Inference(),
        sample_count=6,
        observation_count=6,
        missing_count=0,
        stored_count=6,
        start_s=_START_S,
        end_s=_END_S,
    )


def _refusal(code: str) -> F09Result:
    """Отказ без выдуманных значений: пустые ряды и None вместо интервала."""
    return dataclasses.replace(
        _available(),
        status=Status.UNAVAILABLE,
        reason_codes=(code,),
        event_labels=(),
        transitions=(),
        dt_s=np.empty(0, dtype=np.float64),
        polarity_run_lengths=np.empty(0, dtype=np.int64),
        cluster_start_s=np.empty(0, dtype=np.float64),
        cluster_spread_s=np.empty(0, dtype=np.float64),
        cluster_sizes=np.empty(0, dtype=np.int64),
        cluster_count=0,
        observation_count=0,
        missing_count=6,
        stored_count=0,
        start_s=None,
        end_s=None,
    )


def _replace(result: F09Result, **fields: object) -> F09Result:
    """Копия фикстуры с подменёнными полями без запуска движка."""
    return dataclasses.replace(result, **fields)


def _build(
    result: F09Result,
    *,
    family: CharacterizationFamily | None = None,
    measured_channel: str = "ch1",
    record_duration_s: float = _RECORD_S,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Конверт F09, словарь массивов и словарь таблиц для ручной фикстуры."""
    return build_f09_family(
        result,
        _family() if family is None else family,
        _band(),
        measured_channel=measured_channel,
        record_duration_s=record_duration_s,
    )


def _full_bundle(
    family: FamilyResult,
    arrays: dict[str, np.ndarray],
    tables: dict[str, TableBlock],
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Полный бандл из 18 семейств: F09 в своём слоте, остальное not_computed."""
    recipe = _recipe()
    band = _band()
    families = tuple(
        family if index == F09_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def _encoded(
    family: FamilyResult,
    arrays: dict[str, np.ndarray],
    tables: dict[str, TableBlock],
) -> dict[str, bytes]:
    """Три файла артефакта из полного бандла."""
    bundle, bundle_arrays, bundle_tables = _full_bundle(family, arrays, tables)
    return encode_bundle(
        bundle,
        bundle_arrays,
        bundle_tables,
        max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
    )


def test_constants_match_recipe_slot() -> None:
    """Индекс, идентификатор, метод и словарь кодов берутся из рецепта."""
    recipe = _recipe()
    assert F09_INDEX == 8
    assert F09_ID == "f09_event_ordering"
    assert FAMILY_IDS[F09_INDEX] == F09_ID
    assert recipe.families[F09_INDEX].id == F09_ID
    assert recipe.families[F09_INDEX].method == METHOD
    assert METHOD == "typed_transition_and_waiting_time_inventory"
    assert recipe.families[F09_INDEX].method_version == 1
    assert set(DECLARED_CODES) == set(_VOCAB)


def test_available_publishes_five_arrays_without_masks() -> None:
    """Доступный результат публикует пять рядов без масок и без причин."""
    mapped, arrays, tables = _build(_available())

    assert mapped.family_id == F09_ID
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert mapped.units == (Unit.S, Unit.COUNT)
    assert mapped.method == METHOD
    assert mapped.qc.passed is True
    assert tuple(ref.array_id for ref in mapped.array_refs) == _ARRAY_IDS
    assert all(ref.validity_mask_id is None for ref in mapped.array_refs)
    assert not any(name.endswith("_valid") for name in arrays)
    assert set(arrays) == set(_ARRAY_IDS)
    assert np.array_equal(arrays["f09_dt_s"], np.array(_DT, dtype=np.float64))
    assert np.array_equal(arrays["f09_polarity_run_lengths"], np.array(_RUNS, dtype=np.int64))
    assert np.array_equal(arrays["f09_cluster_start_s"], np.array(_CLUSTER_STARTS))
    assert np.array_equal(arrays["f09_cluster_spread_s"], np.array(_CLUSTER_SPREADS))
    assert np.array_equal(arrays["f09_cluster_sizes"], np.array(_CLUSTER_SIZES))
    assert set(tables) == {_TABLE_ID}


def test_array_units_and_dtypes_follow_the_declared_vocabulary() -> None:
    """Единицы и dtype каждого ряда соответствуют объявленному словарю."""
    mapped, arrays, _ = _build(_available())
    expected: dict[str, Unit] = dict(
        zip(_ARRAY_IDS, (Unit.S, Unit.COUNT, Unit.S, Unit.S, Unit.COUNT), strict=True)
    )
    for ref in mapped.array_refs:
        validate_unit_name(ref.array_id, ref.unit)
        assert ref.unit is expected[ref.array_id]
        assert ref.dtype == arrays[ref.array_id].dtype.name
        assert ref.shape == (arrays[ref.array_id].size,)
    assert arrays["f09_dt_s"].dtype == np.float64
    assert arrays["f09_polarity_run_lengths"].dtype == np.int64
    assert arrays["f09_cluster_sizes"].dtype == np.int64


def test_transition_table_is_pair_keyed_in_first_appearance_order() -> None:
    """Переходы n_ij: пара меток это ключ, порядок первого появления сохранён."""
    mapped, _, tables = _build(_available())
    assert mapped.table_refs == (TableReference(table_id=_TABLE_ID, role="transition_counts"),)
    table = tables[_TABLE_ID]
    assert table.table_id == _TABLE_ID
    assert tuple(column.name for column in table.columns) == (
        "source_label",
        "target_label",
        "n_ij",
    )
    assert tuple(column.type.value for column in table.columns) == ("text", "text", "integer")
    assert table.columns[2].unit is Unit.COUNT
    assert table.rows == (
        (_LABEL_A, _LABEL_A, 2),
        (_LABEL_A, _LABEL_B, 1),
        (_LABEL_B, _LABEL_B, 1),
        (_LABEL_B, _LABEL_A, 1),
    )
    assert (table.row_count, table.stored_count, table.selection_rule) == (4, 4, "all")


def test_partial_publishes_per_array_masks_of_different_lengths() -> None:
    """Частичность объявляется маской на каждый массив: ряды разной длины."""
    result = _replace(_available(), status=Status.PARTIAL, reason_codes=("gaps_present",))
    mapped, arrays, tables = _build(result)

    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == ("gaps_present",)
    assert mapped.qc.passed is False
    assert len(_DT) != len(_RUNS) != len(_CLUSTER_SIZES)
    for ref in mapped.array_refs:
        mask_id = f"{ref.array_id}_valid"
        assert ref.validity_mask_id == mask_id
        assert arrays[mask_id].dtype == np.uint8
        assert arrays[mask_id].shape == ref.shape
        assert set(np.unique(arrays[mask_id]).tolist()) <= {0, 1}
        assert int(np.count_nonzero(arrays[mask_id])) == ref.shape[0]
    by_id = {ref.array_id: ref for ref in mapped.array_refs}
    assert by_id["f09_dt_s"].shape == (len(_DT),)
    assert by_id["f09_polarity_run_lengths"].shape == (len(_RUNS),)
    assert by_id["f09_cluster_sizes"].shape == (len(_CLUSTER_SIZES),)
    assert arrays["f09_dt_s_valid"].shape != arrays["f09_cluster_sizes_valid"].shape
    assert set(tables) == {_TABLE_ID}


def test_partial_codes_are_sorted_within_the_declared_vocabulary() -> None:
    """Коды частичности сортируются и остаются в объявленном словаре."""
    result = _replace(
        _available(),
        status=Status.PARTIAL,
        reason_codes=("single_cycle_record", "dead_time_overlap", "gaps_present"),
    )
    mapped, _, _ = _build(result)
    assert mapped.reason_codes == ("dead_time_overlap", "gaps_present", "single_cycle_record")
    assert mapped.qc.reason_codes == mapped.reason_codes
    assert all(code in DECLARED_CODES for code in mapped.reason_codes)


def test_unavailable_publishes_no_arrays_no_tables_and_zero_support() -> None:
    """Отказ не публикует ни массивов, ни таблиц, ни сводок; поддержка нулевая."""
    mapped, arrays, tables = _build(_refusal("insufficient_events"))

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == ("insufficient_events",)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert mapped.qc.passed is False
    assert arrays == {}
    assert tables == {}
    support = mapped.support
    assert (
        support.sample_count,
        support.observation_count,
        support.missing_count,
        support.stored_count,
    ) == (0, 0, 0, 0)
    assert support.start_s == 0.0
    assert support.end_s == 0.0
    assert support.duration_s == 0.0
    assert mapped.n == 0
    assert mapped.window.kind == "record"
    assert mapped.window.duration_s == _RECORD_S


def test_every_declared_code_maps_to_unavailable() -> None:
    """Каждый объявленный код это отказ без публикаций."""
    for code in _VOCAB:
        mapped, arrays, tables = _build(_refusal(code))
        assert mapped.status is Status.UNAVAILABLE
        assert mapped.reason_codes == (code,)
        assert arrays == {}
        assert tables == {}
        assert mapped.support.observation_count == 0


def test_summaries_equal_result_counters() -> None:
    """Сводки повторяют готовые счётчики движка один в один, новых чисел нет."""
    result = _available()
    mapped, _, _ = _build(result)
    summary = {item.name: item for item in mapped.comparison_summary}
    assert tuple(summary) == (
        "f09_cluster_count",
        "f09_boundary_event_count",
        "f09_dead_time_rejected_count",
        "f09_gap_count",
        "f09_excluded_waiting_interval_count",
        "f09_omitted_event_count",
        "f09_dead_time_s",
    )
    assert summary["f09_cluster_count"].value == float(result.cluster_count) == 2.0
    assert summary["f09_cluster_count"].unit is Unit.COUNT
    assert summary["f09_boundary_event_count"].value == float(result.boundary_event_count) == 1.0
    assert summary["f09_dead_time_rejected_count"].value == 2.0
    assert summary["f09_gap_count"].value == float(result.gap_count) == 1.0
    assert summary["f09_excluded_waiting_interval_count"].value == 0.0
    assert summary["f09_omitted_event_count"].value == 0.0
    assert summary["f09_dead_time_s"].value == result.dead_time_s == _DEAD_TIME_S
    assert summary["f09_dead_time_s"].unit is Unit.S
    assert all(item.circular is False for item in mapped.comparison_summary)


def test_window_is_the_record_and_support_copies_counters() -> None:
    """Окно это вся запись; поддержка копирует счётчики результата."""
    result = _available()
    mapped, _, _ = _build(result)

    assert mapped.window.kind == "record"
    assert mapped.window.duration_s == _RECORD_S
    assert mapped.window.sample_count is None
    assert mapped.window.overlap_fraction == 0.0
    assert mapped.support.start_s == pytest.approx(_START_S)
    assert mapped.support.end_s == pytest.approx(_END_S)
    assert mapped.support.duration_s == pytest.approx(_END_S - _START_S)
    assert mapped.support.sample_count == result.sample_count == 6
    assert mapped.support.observation_count == result.observation_count == 6
    assert mapped.support.missing_count == result.missing_count == 0
    assert mapped.support.stored_count == result.stored_count == 6
    assert mapped.support.selection_rule == "all"
    assert mapped.n == result.observation_count
    assert mapped.missing_rule == "exclude_and_count"
    assert mapped.filter.kind == "none"
    assert mapped.band == _band()


def test_inference_thesis_boundary_is_published() -> None:
    """Тезис спеки:456-459 несёт существующее поле inference, а не выдуманное."""
    mapped, _, _ = _build(_available())
    assert mapped.inference == Inference()
    assert mapped.inference.estimate_scope == "single_session_descriptive"
    assert mapped.inference.population_inference == "withheld"
    assert mapped.inference.reason_code == "independent_capture_units_required"
    for model in (F09Result, type(mapped)):
        names = tuple(field.name for field in dataclasses.fields(model))
        assert not any("p_value" in name or "confidence" in name for name in names)


def test_available_with_reasons_is_refused() -> None:
    """Доступный результат с причинами противоречит инварианту статуса."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_available(), reason_codes=("gaps_present",)))


def test_partial_without_reasons_is_refused() -> None:
    """Частичный результат без причин отвергается."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_available(), status=Status.PARTIAL))


def test_unavailable_without_reasons_is_refused() -> None:
    """Отказ без кодов отвергается."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_refusal("insufficient_events"), reason_codes=()))


def test_duplicate_reason_code_is_refused() -> None:
    """Повтор кода в причинах отвергается."""
    broken = _replace(_refusal("gaps_present"), reason_codes=("gaps_present", "gaps_present"))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_undeclared_reason_code_is_refused() -> None:
    """Код вне объявленного словаря F09 отвергается."""
    for broken in (
        _replace(_refusal("gaps_present"), reason_codes=("not_an_f09_code",)),
        _replace(_available(), status=Status.PARTIAL, reason_codes=("not_computed",)),
        _replace(_available(), status=Status.PARTIAL, reason_codes=("",)),
    ):
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_missing_support_interval_is_refused() -> None:
    """Публикуемый результат без интервала поддержки отвергается."""
    for broken in (
        _replace(_available(), start_s=None),
        _replace(_available(), end_s=None),
    ):
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_broken_support_counts_are_refused() -> None:
    """Расхождение счётчиков поддержки ломает инвариант."""
    for broken in (
        _replace(_available(), sample_count=7),
        _replace(_available(), stored_count=5),
        _replace(_available(), missing_count=1),
    ):
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_cluster_count_mismatch_is_refused() -> None:
    """Счётчик кластеров обязан совпадать с числом опубликованных строк."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_available(), cluster_count=3))


def test_multidimensional_series_is_refused() -> None:
    """Двумерный ряд отвергается: конверт хранит только одномерные ряды."""
    broken = _replace(_available(), dt_s=np.zeros((2, 2), dtype=np.float64))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_misaligned_cluster_rows_are_refused() -> None:
    """Кластерные ряды разной длины отвергаются."""
    broken = _replace(_available(), cluster_spread_s=np.array([0.01], dtype=np.float64))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_nonpositive_transition_count_is_refused() -> None:
    """Нулевой и отрицательный счётчик перехода не публикуется."""
    for count in (0, -1):
        broken = _replace(
            _available(),
            transitions=(Transition(source=_LABEL_A, target=_LABEL_B, count=count),),
        )
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_wrong_family_slot_is_refused() -> None:
    """Маппер F09 принимает только объявленное семейство F09."""
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=_recipe().families[F09_INDEX - 1])


def test_measured_channel_selects_signal_plane() -> None:
    """Канал измерения выбирает плоскость сигнала конверта."""
    mapped, _, _ = _build(_available(), measured_channel="ch2")
    assert mapped.signal_plane == "ch2_transformer_secondary"


def test_arrays_and_tables_round_trip_through_the_codec() -> None:
    """Массивы и таблица переходов переживают кодирование и загрузку."""
    family, arrays, tables = _build(_available())
    loaded = load_bundle(_encoded(family, arrays, tables))

    assert loaded.bundle.families[F09_INDEX] == family
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables
    assert loaded.tables[_TABLE_ID].rows == tables[_TABLE_ID].rows


def test_partial_masks_round_trip_through_the_codec() -> None:
    """Частичный результат с масками на каждый массив переживает кодек."""
    result = _replace(
        _available(),
        status=Status.PARTIAL,
        reason_codes=("dead_time_overlap", "gaps_present"),
    )
    family, arrays, tables = _build(result)
    loaded = load_bundle(_encoded(family, arrays, tables))

    assert loaded.bundle.families[F09_INDEX] == family
    assert loaded.bundle.families[F09_INDEX].reason_codes == (
        "dead_time_overlap",
        "gaps_present",
    )
    assert set(loaded.arrays) == set(arrays)
    assert dict(loaded.tables) == tables


def test_inference_survives_the_codec_round_trip() -> None:
    """Граница вывода переживает кодек: тезис нельзя потерять молча."""
    family, arrays, tables = _build(_available())
    loaded = load_bundle(_encoded(family, arrays, tables))
    inference = loaded.bundle.families[F09_INDEX].inference
    assert inference == Inference()
    assert inference.population_inference == "withheld"
    assert inference.reason_code == "independent_capture_units_required"


def test_unavailable_round_trips_without_outputs() -> None:
    """Отказ переживает кодек без массивов, таблиц и сводок."""
    family, arrays, tables = _build(_refusal("single_cycle_record"))
    loaded = load_bundle(_encoded(family, arrays, tables))
    assert loaded.bundle.families[F09_INDEX] == family
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}
