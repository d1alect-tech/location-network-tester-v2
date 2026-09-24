"""Покрытие маппера F08: ручные фикстуры, статусы, маски, кодек."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

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
from lnt.characterization.f08_bundle import F08_ID, F08_INDEX, build_f08_family
from lnt.characterization.f08_result import (
    DECLARED_CODES,
    METHOD,
    OVERLAPPING_EVENTS,
    SINGLE_EXPONENTIAL_POOR,
    TOO_FEW_SAMPLES,
    F08Result,
)
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F08_METHOD = "bounded_single_damped_sinusoid_fit"
_RECORD_S = 2.4
# Измеренные значения положительной фикстуры evidence (A=1, tau=0.002, f=2000).
_T_RISE_S = (6.4e-5, 7.2e-5, 8.0e-5)
_V_PEAK_V = (0.9472231672106931, 0.8125, 0.75)
_V2_S = (0.000509909184, 0.00041, 0.00038)
_N_ZC = (32, 30, 28)
_F_D_HZ = (1999.9947497368848, 2001.5, 1998.25)
_TAU_D_S = (0.0020006039356745, 0.0019, 0.0021)
_ZETA = (0.03974539882029245, 0.041, 0.038)
_RHO = (0.0024940592837948404, 0.011, 0.02)
_MEASURED_IDS = ("f08_t_rise_s", "f08_v_peak_v", "f08_v2_s", "f08_n_zc")
_FITTED_IDS = ("f08_f_d_hz", "f08_tau_d_s", "f08_zeta", "f08_residual_fraction")
_ARRAY_IDS = (*_MEASURED_IDS, *_FITTED_IDS)
_VOCAB = (
    "below_snr",
    "clipped",
    "multimode",
    "overlapping_events",
    "single_exponential_poor",
    "too_few_samples",
)


def _recipe() -> CharacterizationRecipe:
    """Рецепт-пример из репозитория, семейство F08 берётся по индексу."""
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    """Объявленное семейство F08 из рецепта."""
    return _recipe().families[F08_INDEX]


def _band() -> Band:
    """Полоса анализа из настроек STFT рецепта."""
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _available(count: int = 3) -> F08Result:
    """Готовый результат: все восемь величин измерены на каждом событии."""
    return F08Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        t_rise_s=_T_RISE_S[:count],
        v_peak_v=_V_PEAK_V[:count],
        v2_s=_V2_S[:count],
        n_zc=_N_ZC[:count],
        f_d_hz=_F_D_HZ[:count],
        tau_d_s=_TAU_D_S[:count],
        zeta=_ZETA[:count],
        residual_fraction=_RHO[:count],
        evaluated_event_count=count,
        omitted_event_count=0,
    )


def _partial() -> F08Result:
    """Три оценённых события и одно снятое капом: у третьего фит отклонён.

    Прямые величины измерены на всех трёх оценённых событиях (F08-18), а группа
    фита короче на одно событие плюс на усечённый капом хвост.
    """
    return F08Result(
        status=Status.PARTIAL,
        reason_codes=(SINGLE_EXPONENTIAL_POOR,),
        t_rise_s=(*_T_RISE_S, None),
        v_peak_v=(*_V_PEAK_V, None),
        v2_s=(*_V2_S, None),
        n_zc=(*_N_ZC, None),
        f_d_hz=(_F_D_HZ[0], _F_D_HZ[1], None, None),
        tau_d_s=(_TAU_D_S[0], _TAU_D_S[1], None, None),
        zeta=(_ZETA[0], _ZETA[1], None, None),
        residual_fraction=(_RHO[0], _RHO[1], None, None),
        evaluated_event_count=3,
        omitted_event_count=1,
    )


def _unavailable(code: str, events: int = 0) -> F08Result:
    """Отказ движка: ни одной прямой величины, счётчики инвентаря нулевые."""
    blanks: tuple[None, ...] = (None,) * events
    return F08Result(
        status=Status.UNAVAILABLE,
        reason_codes=(code,),
        t_rise_s=blanks,
        v_peak_v=blanks,
        v2_s=blanks,
        n_zc=blanks,
        f_d_hz=blanks,
        tau_d_s=blanks,
        zeta=blanks,
        residual_fraction=blanks,
        evaluated_event_count=0,
        omitted_event_count=0,
    )


def _replace(result: F08Result, **fields: object) -> F08Result:
    """Копия фикстуры с подменёнными полями без движка."""
    return dataclasses.replace(result, **fields)


def _build(
    result: F08Result,
    *,
    family: CharacterizationFamily | None = None,
    measured_channel: str = "ch1",
    record_duration_s: float = _RECORD_S,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Конверт F08 и словарь массивов для заданной ручной фикстуры."""
    return build_f08_family(
        result,
        _family() if family is None else family,
        _band(),
        measured_channel=measured_channel,
        record_duration_s=record_duration_s,
    )


def _full_bundle(result: F08Result) -> tuple[CharacterizationBundle, dict[str, np.ndarray]]:
    """Полный бандл из 18 семейств для прогона через кодек."""
    band = _band()
    mapped, arrays = _build(result)
    families = tuple(
        mapped if index == F08_INDEX else not_computed_family(item, band)
        for index, item in enumerate(_recipe().families)
    )
    return CharacterizationBundle(families=families), arrays


def _source(result: F08Result, array_id: str) -> tuple[float | None, ...] | tuple[int | None, ...]:
    """Исходный кортеж результата для одного объявленного массива."""
    return {
        "f08_t_rise_s": result.t_rise_s,
        "f08_v_peak_v": result.v_peak_v,
        "f08_v2_s": result.v2_s,
        "f08_n_zc": result.n_zc,
        "f08_f_d_hz": result.f_d_hz,
        "f08_tau_d_s": result.tau_d_s,
        "f08_zeta": result.zeta,
        "f08_residual_fraction": result.residual_fraction,
    }[array_id]


def test_constants_match_recipe_slot() -> None:
    """Индекс, идентификатор, метод и словарь кодов совпадают с рецептом."""
    recipe = _recipe()
    assert F08_INDEX == 7
    assert F08_ID == "f08_transient_morphology"
    assert FAMILY_IDS[F08_INDEX] == F08_ID
    assert recipe.families[F08_INDEX].id == F08_ID
    assert recipe.families[F08_INDEX].method == METHOD == _F08_METHOD
    assert recipe.families[F08_INDEX].method_version == 1
    assert set(DECLARED_CODES) == set(_VOCAB)


def test_available_publishes_eight_arrays_without_masks() -> None:
    """Готовый результат публикует восемь массивов без масок и без причин."""
    mapped, arrays = _build(_available())
    assert mapped.family_id == F08_ID
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert mapped.qc.passed is True
    assert mapped.method == _F08_METHOD
    assert mapped.units == (Unit.S, Unit.V, Unit.V2_S, Unit.COUNT, Unit.HZ, Unit.RATIO)
    assert tuple(ref.array_id for ref in mapped.array_refs) == _ARRAY_IDS
    assert all(ref.validity_mask_id is None for ref in mapped.array_refs)
    assert not any(name.endswith("_valid") for name in arrays)
    assert set(arrays) == set(_ARRAY_IDS)


def test_array_values_and_dtypes_equal_result_tuples() -> None:
    """Значения и типы массивов повторяют кортежи результата один в один."""
    result = _available()
    _, arrays = _build(result)
    by_id = {ref.array_id: ref for ref in _build(result)[0].array_refs}
    for array_id in _ARRAY_IDS:
        expected = [value for value in _source(result, array_id) if value is not None]
        assert arrays[array_id].tolist() == expected
        assert arrays[array_id].dtype == (np.int64 if array_id == "f08_n_zc" else np.float64)
        assert by_id[array_id].dtype == arrays[array_id].dtype.name
        assert by_id[array_id].shape == (3,)
    assert by_id["f08_v2_s"].unit is Unit.V2_S
    assert by_id["f08_n_zc"].unit is Unit.COUNT
    assert by_id["f08_f_d_hz"].unit is Unit.HZ
    assert by_id["f08_zeta"].unit is Unit.RATIO
    assert all(by_id[array_id].role for array_id in _ARRAY_IDS)


def test_partial_publishes_per_array_validity_masks() -> None:
    """Частичный результат объявляет маску единиц на каждый массив (идиома F02)."""
    mapped, arrays = _build(_partial())
    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (SINGLE_EXPONENTIAL_POOR,)
    assert mapped.qc.passed is False
    for ref in mapped.array_refs:
        mask_id = f"{ref.array_id}_valid"
        assert ref.validity_mask_id == mask_id
        assert arrays[mask_id].dtype == np.uint8
        assert arrays[mask_id].shape == arrays[ref.array_id].shape
        assert arrays[mask_id].tolist() == [1] * arrays[ref.array_id].size


def test_partial_fit_group_is_shorter_than_measured_group() -> None:
    """Группа фита короче прямой группы: у отклонённого события фита нет."""
    mapped, arrays = _build(_partial())
    by_id = {ref.array_id: ref for ref in mapped.array_refs}
    for array_id in _MEASURED_IDS:
        assert arrays[array_id].size == 3
        assert by_id[array_id].shape == (3,)
    for array_id in _FITTED_IDS:
        assert arrays[array_id].size == 2
        assert by_id[array_id].shape == (2,)
        assert arrays[f"{array_id}_valid"].shape == (2,)


def test_none_quantity_never_becomes_a_fabricated_number() -> None:
    """None не превращается в число: элемент исключён, а не заменён нулём или NaN."""
    result = _partial()
    _, arrays = _build(result)
    for array_id in _ARRAY_IDS:
        stored = arrays[array_id]
        expected = [value for value in _source(result, array_id) if value is not None]
        assert stored.size == len(expected)
        assert stored.tolist() == expected
        assert bool(np.all(np.isfinite(stored)))
        assert 0.0 not in stored.tolist()
        assert 0 not in stored.tolist()
    assert arrays["f08_f_d_hz"].tolist() == [_F_D_HZ[0], _F_D_HZ[1]]
    assert arrays["f08_n_zc"].tolist() == list(_N_ZC)


def test_unavailable_publishes_no_arrays_and_zero_support() -> None:
    """Отказ не публикует ни массивов, ни сводок, поддержка нулевая."""
    mapped, arrays = _build(_unavailable(TOO_FEW_SAMPLES))
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (TOO_FEW_SAMPLES,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert mapped.qc.passed is False
    assert arrays == {}
    support = mapped.support
    assert (support.sample_count, support.observation_count) == (0, 0)
    assert (support.missing_count, support.stored_count) == (0, 0)
    assert support.duration_s == pytest.approx(0.0)
    assert mapped.n == 0


def test_overlapping_events_refusal_keeps_inventory_out_of_support() -> None:
    """Отказ всего инвентаря: кортежи полны None, поддержка всё равно нулевая."""
    mapped, arrays = _build(_unavailable(OVERLAPPING_EVENTS, events=4))
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (OVERLAPPING_EVENTS,)
    assert arrays == {}
    assert mapped.support.sample_count == 0


def test_every_declared_code_maps_to_unavailable() -> None:
    """Каждый объявленный код проходит, словарь F08 закрыт."""
    assert set(_VOCAB) == {
        "clipped",
        "single_exponential_poor",
        "below_snr",
        "too_few_samples",
        "overlapping_events",
        "multimode",
    }
    for code in _VOCAB:
        mapped, arrays = _build(_unavailable(code))
        assert mapped.status is Status.UNAVAILABLE
        assert mapped.reason_codes == (code,)
        assert arrays == {}


def test_reason_codes_are_sorted_and_unique() -> None:
    """Несколько кодов публикуются отсортированным множеством."""
    result = _replace(_partial(), reason_codes=(SINGLE_EXPONENTIAL_POOR, "clipped", "below_snr"))
    mapped, _ = _build(result)
    assert mapped.reason_codes == ("below_snr", "clipped", "single_exponential_poor")


def test_undeclared_reason_code_is_refused() -> None:
    """Код вне объявленного словаря F08 отвергается."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_partial(), reason_codes=("not_an_f08_code",)))


def test_duplicate_reason_code_is_refused() -> None:
    """Повтор кода в причинах отвергается."""
    broken = _replace(_partial(), reason_codes=(SINGLE_EXPONENTIAL_POOR,) * 2)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_empty_reason_code_is_refused() -> None:
    """Пустая строка вместо кода отвергается."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_partial(), reason_codes=("",)))


def test_available_with_reasons_is_refused() -> None:
    """Готовый результат с причинами противоречит инварианту статуса."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_available(), reason_codes=("clipped",)))


def test_partial_without_reasons_is_refused() -> None:
    """Частичный результат без причин отвергается."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_partial(), reason_codes=()))


def test_unavailable_without_reasons_is_refused() -> None:
    """Отказ без кодов отвергается."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_unavailable(TOO_FEW_SAMPLES), reason_codes=()))


def test_available_with_unfitted_event_is_refused() -> None:
    """AVAILABLE обязан подогнать каждое измеренное событие (F08-19)."""
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(_replace(_partial(), status=Status.AVAILABLE, reason_codes=()))


def test_capped_tail_stays_available_and_visible_in_support() -> None:
    """Хвост за maximum_events не понижает статус, но виден в учёте поддержки."""
    # Движок дописывает снятый капом хвост как None в каждый кортеж (F08-19).
    result = _replace(
        _available(),
        t_rise_s=(*_T_RISE_S, None, None),
        v_peak_v=(*_V_PEAK_V, None, None),
        v2_s=(*_V2_S, None, None),
        n_zc=(*_N_ZC, None, None),
        f_d_hz=(*_F_D_HZ, None, None),
        tau_d_s=(*_TAU_D_S, None, None),
        zeta=(*_ZETA, None, None),
        residual_fraction=(*_RHO, None, None),
        omitted_event_count=2,
    )
    mapped, arrays = _build(result)
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert all(ref.validity_mask_id is None for ref in mapped.array_refs)
    assert arrays["f08_f_d_hz"].size == 3
    assert mapped.support.sample_count == 5
    assert mapped.support.observation_count == 3
    assert mapped.support.missing_count == 2
    assert mapped.support.stored_count == 3
    summary = {item.name: item.value for item in mapped.comparison_summary}
    assert summary["f08_evaluated_event_count"] == 3.0
    assert summary["f08_omitted_event_count"] == 2.0
    assert summary["f08_fitted_event_count"] == 3.0


def test_capped_tail_with_refused_fit_is_partial() -> None:
    """Снятый хвост и один отклонённый фит дают PARTIAL с масками на каждый массив."""
    result = _replace(
        _partial(),
        t_rise_s=(*_T_RISE_S, None, None),
        v_peak_v=(*_V_PEAK_V, None, None),
        v2_s=(*_V2_S, None, None),
        n_zc=(*_N_ZC, None, None),
        f_d_hz=(_F_D_HZ[0], _F_D_HZ[1], None, None, None),
        tau_d_s=(_TAU_D_S[0], _TAU_D_S[1], None, None, None),
        zeta=(_ZETA[0], _ZETA[1], None, None, None),
        residual_fraction=(_RHO[0], _RHO[1], None, None, None),
        omitted_event_count=2,
    )
    mapped, arrays = _build(result)
    assert mapped.status is Status.PARTIAL
    assert mapped.support.sample_count == 5
    assert mapped.support.observation_count == 3
    assert mapped.support.missing_count == 2
    assert arrays["f08_t_rise_s"].size == 3
    assert arrays["f08_f_d_hz"].size == 2
    assert arrays["f08_f_d_hz_valid"].tolist() == [1, 1]


def test_published_without_fitted_event_is_refused() -> None:
    """Без единого фита движок даёт UNAVAILABLE: публикация отвергается."""
    broken = _replace(
        _partial(),
        status=Status.PARTIAL,
        f_d_hz=(None, None, None, None),
        tau_d_s=(None, None, None, None),
        zeta=(None, None, None, None),
        residual_fraction=(None, None, None, None),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_misaligned_measured_group_is_refused() -> None:
    """Разный рисунок None внутри прямой группы ломает инвариант."""
    broken = _replace(_partial(), v_peak_v=(_V_PEAK_V[0], None, _V_PEAK_V[2], None))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_fit_without_measured_span_is_refused() -> None:
    """Параметр фита без измеренного спана невозможен.

    Обе группы внутри себя выровнены, поэтому срабатывает ровно проверка
    вложенности индексов, а не проверка общего рисунка ``None``.
    """
    broken = _replace(
        _partial(),
        t_rise_s=(_T_RISE_S[0], _T_RISE_S[1], None, None),
        v_peak_v=(_V_PEAK_V[0], _V_PEAK_V[1], None, None),
        v2_s=(_V2_S[0], _V2_S[1], None, None),
        n_zc=(_N_ZC[0], _N_ZC[1], None, None),
        f_d_hz=(_F_D_HZ[0], None, _F_D_HZ[2], None),
        tau_d_s=(_TAU_D_S[0], None, _TAU_D_S[2], None),
        zeta=(_ZETA[0], None, _ZETA[2], None),
        residual_fraction=(_RHO[0], None, _RHO[2], None),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_negative_event_counts_are_refused_by_support() -> None:
    """Отрицательный счётчик инвентаря отвергает сама поддержка."""
    broken = _replace(_available(), evaluated_event_count=-1)
    with pytest.raises(CharacterizationError):
        _build(broken)


def test_tuple_length_mismatch_is_refused() -> None:
    """Длина кортежей обязана равняться полному инвентарю событий."""
    broken = _replace(_available(), omitted_event_count=1)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_window_is_the_record_and_support_counts_the_inventory() -> None:
    """Окно это запись, поддержка считает полный инвентарь и снятый остаток."""
    result = _partial()
    mapped, _ = _build(result)
    assert mapped.window.kind == "record"
    assert mapped.window.duration_s == pytest.approx(_RECORD_S)
    assert mapped.window.sample_count is None
    assert mapped.window.overlap_fraction == pytest.approx(0.0)
    support = mapped.support
    assert support.sample_count == result.evaluated_event_count + result.omitted_event_count == 4
    assert support.observation_count == 3
    assert support.missing_count == 1
    assert support.stored_count == 3
    assert support.selection_rule == "all"
    assert mapped.n == 3
    assert mapped.missing_rule == "exclude_and_count"
    assert mapped.filter.kind == "none"
    assert mapped.inference.population_inference == "withheld"


def test_support_interval_is_not_invented() -> None:
    """Позиций событий в результате нет, поэтому интервал поддержки вырожден."""
    mapped, _ = _build(_available())
    assert mapped.support.start_s == pytest.approx(0.0)
    assert mapped.support.end_s == pytest.approx(0.0)
    assert mapped.support.duration_s == pytest.approx(0.0)


def test_summaries_carry_declared_counters() -> None:
    """Сводки повторяют счётчики инвентаря и число опубликованных фитов."""
    result = _partial()
    mapped, _ = _build(result)
    summary = {item.name: item for item in mapped.comparison_summary}
    assert set(summary) == {
        "f08_evaluated_event_count",
        "f08_omitted_event_count",
        "f08_fitted_event_count",
    }
    assert summary["f08_evaluated_event_count"].value == float(result.evaluated_event_count) == 3.0
    assert summary["f08_omitted_event_count"].value == float(result.omitted_event_count) == 1.0
    assert summary["f08_fitted_event_count"].value == 2.0
    assert all(item.unit is Unit.COUNT for item in mapped.comparison_summary)


def test_measured_channel_selects_signal_plane() -> None:
    """Канал измерения выбирает плоскость сигнала конверта."""
    assert _build(_available(), measured_channel="ch2")[0].signal_plane == (
        "ch2_transformer_secondary"
    )
    assert _build(_available())[0].signal_plane == "ch1_scope_input"


def test_wrong_family_slot_is_refused() -> None:
    """Маппер F08 принимает только объявленное семейство F08."""
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=_recipe().families[F08_INDEX - 1])


def test_partial_family_round_trips_through_the_codec() -> None:
    """Частичное семейство с масками переживает кодирование и загрузку."""
    bundle, arrays = _full_bundle(_partial())
    files = encode_bundle(
        bundle, arrays, {}, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )
    loaded = load_bundle(files)
    assert loaded.bundle.families[F08_INDEX] == bundle.families[F08_INDEX]
    assert set(loaded.arrays) == {*_ARRAY_IDS, *(f"{name}_valid" for name in _ARRAY_IDS)}
    for array_id, values in arrays.items():
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == {}


def test_available_family_round_trips_through_the_codec() -> None:
    """Готовое семейство переживает кодирование без масок частичности."""
    bundle, arrays = _full_bundle(_available())
    files = encode_bundle(
        bundle, arrays, {}, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )
    loaded = load_bundle(files)
    assert loaded.bundle == bundle
    assert set(loaded.arrays) == set(_ARRAY_IDS)
    for array_id, values in arrays.items():
        assert np.array_equal(loaded.arrays[array_id], values)


def test_unavailable_family_round_trips_through_the_codec() -> None:
    """Отказ кодируется пустым NPZ и не теряет объявленную причину."""
    bundle, arrays = _full_bundle(_unavailable(OVERLAPPING_EVENTS, events=2))
    files = encode_bundle(
        bundle, arrays, {}, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )
    loaded = load_bundle(files)
    assert loaded.bundle == bundle
    assert loaded.bundle.families[F08_INDEX].reason_codes == (OVERLAPPING_EVENTS,)
    assert dict(loaded.arrays) == {}
