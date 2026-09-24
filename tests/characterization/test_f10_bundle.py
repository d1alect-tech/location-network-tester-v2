"""Покрытие маппера F10: ручные фикстуры поверхности, статусы, поддержка, кодек."""

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
from lnt.characterization.f10_bundle import F10_ID, F10_INDEX, build_f10_family
from lnt.characterization.f10_result import DECLARED_CODES, METHOD, F10Episode, F10Result
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_SIGMAS = (3.0, 5.0, 8.0, 12.0)
_DURATIONS = (0.0, 2e-05, 1e-04, 1e-03, 1e-02)
_QUANTILES = (0.5, 0.9, 0.99)
_BINS = 64
_CELL = (len(_SIGMAS), len(_DURATIONS), _BINS)
_QUANTILE_CELL = (*_CELL, len(_QUANTILES))
_CELL_COUNT = len(_SIGMAS) * len(_DURATIONS) * _BINS
_RECORD_S = 2.4
_SAMPLES = 240_000
_OBSERVED = 239_000
_QUALIFIED_PER_BIN = _OBSERVED // _BINS
_VALID_CELLS = ((0, 0, 8), (1, 0, 8))
_SURFACE_IDS = (
    "f10_occupancy",
    "f10_episode_count",
    "f10_total_v2_s",
    "f10_retained_samples",
    "f10_truncated_samples",
)
_QUANTILE_IDS = ("f10_duration_quantile_s", "f10_episode_quantile_v2_s")
_EPISODE_IDS = (
    "f10_episode_sigma",
    "f10_episode_phase_bin",
    "f10_episode_start_time_s",
    "f10_episode_duration_s",
    "f10_episode_v2_s",
)
_AXIS_IDS = (
    "f10_threshold_sigma",
    "f10_minimum_duration_s",
    "f10_phase_bin",
    "f10_quantile_level",
)
_SUMMARY_NAMES = (
    "f10_qualified_cycles",
    "f10_full_episode_count",
    "f10_truncated_episode_count",
    "f10_stored_episode_count",
    "f10_omitted_episode_count",
)


def _recipe() -> CharacterizationRecipe:
    """Рецепт-пример из репозитория: семейство F10 берётся по объявленному индексу."""
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    """Объявленное семейство F10 из рецепта."""
    return _recipe().families[F10_INDEX]


def _band() -> Band:
    """Полоса анализа из настроек STFT рецепта."""
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _episodes() -> tuple[F10Episode, ...]:
    """Два хранимых полных эпизода: ровно те ячейки, где квантиль определён."""
    return tuple(
        F10Episode(
            sigma=_SIGMAS[sigma_index],
            phase_bin=phase_bin,
            start_time_s=0.001 * (index + 1),
            duration_s=0.0002 * (index + 1),
            v2_s=0.025 * (index + 1),
        )
        for index, (sigma_index, _, phase_bin) in enumerate(_VALID_CELLS)
    )


def _valid_mask() -> np.ndarray:
    """Домен квантилей движка: True только в ячейках с полным эпизодом."""
    valid = np.zeros(_CELL, dtype=np.bool_)
    for sigma_index, duration_index, phase_bin in _VALID_CELLS:
        valid[sigma_index, duration_index, phase_bin] = True
    return valid


def _quantiles(fill: float) -> np.ndarray:
    """Квантили движка: нули вне домена, значение внутри него."""
    values = np.zeros(_QUANTILE_CELL, dtype=np.float64)
    for index, (sigma_index, duration_index, phase_bin) in enumerate(_VALID_CELLS):
        values[sigma_index, duration_index, phase_bin, :] = fill * (index + 1)
    return values


def _available() -> F10Result:
    """Полный доступный результат: поверхность 4×5×64 и два хранимых эпизода."""
    counts = np.zeros(_CELL, dtype=np.int64)
    for sigma_index, duration_index, phase_bin in _VALID_CELLS:
        counts[sigma_index, duration_index, phase_bin] = 1
    return F10Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        threshold_sigma=np.array(_SIGMAS, dtype=np.float64),
        minimum_duration_s=np.array(_DURATIONS, dtype=np.float64),
        quantiles=np.array(_QUANTILES, dtype=np.float64),
        occupancy=np.full(_CELL, 0.125, dtype=np.float64),
        episode_count=counts,
        total_v2_s=np.full(_CELL, 0.05, dtype=np.float64),
        retained_samples=np.full(_CELL, 4, dtype=np.int64),
        truncated_samples=np.zeros(_CELL, dtype=np.int64),
        qualified_samples=np.full(_BINS, _QUALIFIED_PER_BIN, dtype=np.int64),
        qualified_cycles=120,
        duration_quantile_s=_quantiles(0.001),
        episode_quantile_v2_s=_quantiles(0.025),
        quantile_valid=_valid_mask(),
        episodes=_episodes(),
        sample_count=_SAMPLES,
        observation_count=_OBSERVED,
        missing_count=_SAMPLES - _OBSERVED,
        episode_total=len(_VALID_CELLS),
        truncated_episode_total=1,
        stored_count=len(_VALID_CELLS),
        omitted_count=0,
    )


def _build(
    result: F10Result, *, channel: str = "ch1"
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Маппинг одного семейства поверх объявленных семейства и полосы."""
    return build_f10_family(
        result, _family(), _band(), measured_channel=channel, record_duration_s=_RECORD_S
    )


def _full_bundle(
    family: FamilyResult, arrays: dict[str, np.ndarray]
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Полный бандл из 18 семейств: F10 в своём слоте, остальное not_computed."""
    recipe = _recipe()
    band = _band()
    families = tuple(
        family if index == F10_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), {}


def test_constants_match_recipe_and_contract() -> None:
    """Индекс и идентификатор берутся из контракта, а не выдумываются."""
    recipe = _recipe()
    assert F10_INDEX == 9
    assert F10_ID == "f10_threshold_episode_surface"
    assert FAMILY_IDS[F10_INDEX] == F10_ID
    assert recipe.families[F10_INDEX].id == F10_ID
    assert recipe.families[F10_INDEX].method == METHOD
    assert recipe.families[F10_INDEX].method_version == 1


def test_available_publishes_the_surface_with_its_true_three_dimensional_shape() -> None:
    """Поверхность публикуется настоящей формой 4×5×64, ось за осью, без уплощения."""
    family, arrays = _build(_available())
    by_id = {ref.array_id: ref for ref in family.array_refs}

    assert family.family_id == F10_ID
    assert family.status is Status.AVAILABLE
    assert family.reason_codes == ()
    assert family.units == (Unit.RATIO, Unit.S, Unit.COUNT, Unit.V2_S)
    for array_id in _SURFACE_IDS:
        assert by_id[array_id].shape == _CELL
        assert arrays[array_id].shape == _CELL
        assert arrays[array_id].size == _CELL_COUNT
    assert by_id["f10_qualified_samples"].shape == (_BINS,)


def test_axis_arrays_keep_every_cell_addressable_by_value() -> None:
    """Координаты всех четырёх осей опубликованы: ячейка адресуется значением."""
    family, arrays = _build(_available())
    by_id = {ref.array_id: ref for ref in family.array_refs}

    assert set(_AXIS_IDS) <= set(by_id)
    assert np.array_equal(arrays["f10_threshold_sigma"], np.array(_SIGMAS, dtype=np.float64))
    assert np.array_equal(arrays["f10_minimum_duration_s"], np.array(_DURATIONS, dtype=np.float64))
    assert np.array_equal(arrays["f10_quantile_level"], np.array(_QUANTILES, dtype=np.float64))
    assert np.array_equal(arrays["f10_phase_bin"], np.arange(_BINS, dtype=np.int64))
    assert by_id["f10_threshold_sigma"].shape == (len(_SIGMAS),)
    assert by_id["f10_minimum_duration_s"].shape == (len(_DURATIONS),)
    assert by_id["f10_quantile_level"].shape == (len(_QUANTILES),)
    assert by_id["f10_phase_bin"].shape == (_BINS,)
    assert by_id["f10_phase_bin"].unit is Unit.COUNT


def test_quantile_arrays_carry_their_own_level_axis() -> None:
    """Квантили не схлопнуты в сводку: четвёртая ось уровня объявлена и опубликована."""
    family, arrays = _build(_available())
    by_id = {ref.array_id: ref for ref in family.array_refs}

    for array_id in _QUANTILE_IDS:
        assert by_id[array_id].shape == _QUANTILE_CELL
        assert arrays[array_id].shape == _QUANTILE_CELL
    assert by_id["f10_duration_quantile_s"].unit is Unit.S
    assert by_id["f10_episode_quantile_v2_s"].unit is Unit.V2_S
    assert arrays["f10_duration_quantile_s"][0, 0, 8, 2] == pytest.approx(0.001)


def test_undefined_quantiles_are_masked_and_never_readable_as_a_measurement() -> None:
    """Ячейка без полного эпизода закрыта нулевой маской, а не выдуманным нулём."""
    family, arrays = _build(_available())
    by_id = {ref.array_id: ref for ref in family.array_refs}
    mask = arrays["f10_quantile_valid"]

    assert mask.dtype == np.uint8
    assert mask.shape == _QUANTILE_CELL
    assert set(np.unique(mask).tolist()) <= {0, 1}
    for array_id in _QUANTILE_IDS:
        assert by_id[array_id].validity_mask_id == "f10_quantile_valid"
    assert mask[0, 0, 0, 0] == 0
    assert mask[0, 0, 8, 0] == 1
    assert int(np.count_nonzero(mask)) == len(_VALID_CELLS) * len(_QUANTILES)
    # Нуль вне домена не читается как измерение: потребитель обязан идти через маску.
    assert all(mask[index] == 0 for index in ((0, 0, 0, 0), (3, 4, 63, 2)))


def test_v2_s_arrays_never_claim_an_energy_unit() -> None:
    """`v2_s` публикуется в объявленной единице V²s, не в джоулях и не в ваттах."""
    family, _ = _build(_available())
    by_id = {ref.array_id: ref for ref in family.array_refs}

    assert Unit.V2_S.value == "V^2 s"
    assert by_id["f10_total_v2_s"].unit is Unit.V2_S
    assert by_id["f10_episode_quantile_v2_s"].unit is Unit.V2_S
    assert by_id["f10_episode_v2_s"].unit is Unit.V2_S
    assert by_id["f10_occupancy"].unit is Unit.RATIO


def test_available_publishes_no_partial_masks_beyond_the_quantile_domain() -> None:
    """Доступный результат не плодит маски-единицы: домен квантилей несёт информацию."""
    family, arrays = _build(_available())

    assert not any(name != "f10_quantile_valid" and name.endswith("_valid") for name in arrays)
    assert "f10_quantile_valid" in arrays
    masked = [ref.array_id for ref in family.array_refs if ref.validity_mask_id is not None]
    assert sorted(masked) == sorted(_QUANTILE_IDS)


def test_partial_publishes_a_mask_on_every_array_reference() -> None:
    """Частичный результат объявляет маску на каждую ссылку, uint8 той же формы."""
    result = dataclasses.replace(_available(), status=Status.PARTIAL, reason_codes=("clipped",))
    family, arrays = _build(result)

    assert family.status is Status.PARTIAL
    assert family.reason_codes == ("clipped",)
    for ref in family.array_refs:
        assert ref.validity_mask_id is not None
        mask = arrays[ref.validity_mask_id]
        assert mask.dtype == np.uint8
        assert mask.shape == ref.shape
        assert set(np.unique(mask).tolist()) <= {0, 1}
    # Домен квантилей не подменяется единицами: он остаётся настоящим.
    assert int(np.count_nonzero(arrays["f10_quantile_valid"])) == len(_VALID_CELLS) * len(
        _QUANTILES
    )
    assert np.all(arrays["f10_occupancy_valid"] == 1)


def test_unavailable_publishes_no_arrays_and_zero_support() -> None:
    """Отказ не публикует ни массивов, ни сводок, поддержка нулевая."""
    result = dataclasses.replace(
        _available(),
        status=Status.UNAVAILABLE,
        reason_codes=("phase_reference_unavailable",),
    )
    family, arrays = _build(result)

    assert family.status is Status.UNAVAILABLE
    assert family.reason_codes == ("phase_reference_unavailable",)
    assert family.array_refs == ()
    assert family.comparison_summary == ()
    assert arrays == {}
    assert family.support.observation_count == 0
    assert family.support.stored_count == 0
    assert family.support.duration_s == 0.0
    assert family.n == 0


@pytest.mark.parametrize("code", sorted(DECLARED_CODES))
def test_every_declared_code_publishes(code: str) -> None:
    """Каждый код объявленного словаря проходит через маппер в частичном результате."""
    result = dataclasses.replace(_available(), status=Status.PARTIAL, reason_codes=(code,))
    family, arrays = _build(result)

    assert family.status is Status.PARTIAL
    assert family.reason_codes == (code,)
    assert arrays


def test_declared_codes_publish_sorted_and_unique() -> None:
    """Несколько кодов публикуются отсортированными и без повторов."""
    result = dataclasses.replace(
        _available(), status=Status.PARTIAL, reason_codes=("clipped", "artifact_limit")
    )
    family, _ = _build(result)

    assert family.reason_codes == ("artifact_limit", "clipped")
    assert family.qc.reason_codes == ("artifact_limit", "clipped")
    assert family.qc.passed is False


def test_unknown_reason_code_is_rejected() -> None:
    """Чужой код причины отвергается, а не просачивается в конверт."""
    result = dataclasses.replace(
        _available(), status=Status.PARTIAL, reason_codes=("not_computed",)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result)


def test_duplicate_reason_code_is_rejected() -> None:
    """Повторный код отвергается: словарь причин уникален."""
    result = dataclasses.replace(
        _available(), status=Status.PARTIAL, reason_codes=("clipped", "clipped")
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result)


def test_available_with_reasons_is_rejected() -> None:
    """Доступный результат с причинами противоречит инварианту статуса."""
    result = dataclasses.replace(_available(), reason_codes=("clipped",))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result)


def test_partial_without_reasons_is_rejected() -> None:
    """Частичный результат без причин противоречит инварианту статуса."""
    result = dataclasses.replace(_available(), status=Status.PARTIAL)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result)


def test_unavailable_without_reasons_is_rejected() -> None:
    """Отказ без причин не публикуется: причина обязательна."""
    result = dataclasses.replace(_available(), status=Status.UNAVAILABLE)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result)


def test_wrong_recipe_slot_is_rejected() -> None:
    """Чужой слот рецепта отвергается кодом family_order."""
    recipe = _recipe()
    with pytest.raises(CharacterizationError, match="family_order"):
        build_f10_family(
            _available(),
            recipe.families[F10_INDEX - 1],
            _band(),
            measured_channel="ch1",
            record_duration_s=_RECORD_S,
        )


def test_misaligned_cell_array_is_rejected() -> None:
    """Массив ячеек чужой формы отвергается: раскладка потребляется F15 и F11."""
    broken = dataclasses.replace(
        _available(), episode_count=np.zeros((len(_SIGMAS), len(_DURATIONS), 8), dtype=np.int64)
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_quantile_domain_of_the_wrong_shape_is_rejected() -> None:
    """Домен квантилей чужой формы отвергается, а не растягивается молча."""
    broken = dataclasses.replace(_available(), quantile_valid=np.zeros(_CELL[:2], dtype=np.bool_))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_episode_accounting_that_does_not_add_up_is_rejected() -> None:
    """`episode_total` обязан равняться сумме хранимых и опущенных эпизодов."""
    broken = dataclasses.replace(_available(), episode_total=7)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_window_and_support_follow_the_record() -> None:
    """Окно это запись; поддержка копирует счётчики отсчётов один в один."""
    result = _available()
    family, _ = _build(result)

    assert family.window.kind == "record"
    assert family.window.duration_s == _RECORD_S
    assert family.window.sample_count is None
    assert family.window.overlap_fraction == 0.0
    assert family.support.start_s == 0.0
    assert family.support.end_s == _RECORD_S
    assert family.support.duration_s == _RECORD_S
    assert family.support.sample_count == result.sample_count
    assert family.support.observation_count == result.observation_count
    assert family.support.missing_count == result.missing_count
    assert family.support.stored_count == result.observation_count
    assert family.support.selection_rule == "all"
    assert family.n == result.observation_count
    assert family.missing_rule == "exclude_and_count"


def test_summaries_equal_result_counters() -> None:
    """Сводки это готовые счётчики результата; новых чисел маппер не выводит."""
    result = _available()
    family, _ = _build(result)
    summaries = {item.name: item for item in family.comparison_summary}

    assert tuple(summaries) == _SUMMARY_NAMES
    expected = {
        "f10_qualified_cycles": result.qualified_cycles,
        "f10_full_episode_count": result.episode_total,
        "f10_truncated_episode_count": result.truncated_episode_total,
        "f10_stored_episode_count": result.stored_count,
        "f10_omitted_episode_count": result.omitted_count,
    }
    for name, value in expected.items():
        assert summaries[name].value == pytest.approx(float(value))
        assert summaries[name].unit is Unit.COUNT


def test_stored_episodes_publish_as_aligned_arrays_without_padding() -> None:
    """Хранимые эпизоды выровнены, длина равна числу записей, пустых строк нет."""
    result = _available()
    family, arrays = _build(result)
    by_id = {ref.array_id: ref for ref in family.array_refs}
    stored = len(result.episodes)

    for array_id in _EPISODE_IDS:
        assert by_id[array_id].shape == (stored,)
        assert arrays[array_id].shape == (stored,)
    assert arrays["f10_episode_sigma"].tolist() == [item.sigma for item in result.episodes]
    assert arrays["f10_episode_phase_bin"].dtype == np.int64
    assert arrays["f10_episode_phase_bin"].tolist() == [item.phase_bin for item in result.episodes]
    assert arrays["f10_episode_v2_s"].tolist() == [item.v2_s for item in result.episodes]


def test_episode_storage_cap_is_declared_not_fabricated() -> None:
    """Кап хранения виден в сводках и в длине массивов, а не в выдуманных строках."""
    result = dataclasses.replace(
        _available(),
        status=Status.PARTIAL,
        reason_codes=("artifact_limit",),
        episodes=_episodes()[:1],
        episode_total=5,
        stored_count=1,
        omitted_count=4,
    )
    family, arrays = _build(result)
    summaries = {item.name: item for item in family.comparison_summary}

    assert arrays["f10_episode_sigma"].shape == (1,)
    assert summaries["f10_stored_episode_count"].value == pytest.approx(1.0)
    assert summaries["f10_omitted_episode_count"].value == pytest.approx(4.0)
    assert summaries["f10_full_episode_count"].value == pytest.approx(5.0)
    assert family.reason_codes == ("artifact_limit",)


def test_stored_episode_records_that_disagree_with_the_counter_are_rejected() -> None:
    """Расхождение числа записей и `stored_count` отвергается до конверта."""
    broken = dataclasses.replace(_available(), stored_count=5, episode_total=5)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_measured_channel_selects_signal_plane() -> None:
    """Канал измерения выбирает плоскость сигнала конверта."""
    family, _ = _build(_available(), channel="ch2")

    assert family.signal_plane == "ch2_transformer_secondary"


def test_dtypes_survive_the_unit_vocabulary() -> None:
    """Счётчики остаются int64, величины float64: dtype публикуется в ссылке."""
    family, arrays = _build(_available())
    by_id = {ref.array_id: ref for ref in family.array_refs}

    for array_id, ref in by_id.items():
        assert arrays[array_id].dtype.name == ref.dtype
    assert arrays["f10_episode_count"].dtype == np.int64
    assert arrays["f10_qualified_samples"].dtype == np.int64
    assert arrays["f10_occupancy"].dtype == np.float64
    assert arrays["f10_total_v2_s"].dtype == np.float64


def test_family_round_trips_through_the_codec() -> None:
    """Семейство с масками переживает кодирование и загрузку без потерь формы и dtype."""
    result = dataclasses.replace(
        _available(), status=Status.PARTIAL, reason_codes=("clipped", "artifact_limit")
    )
    family, arrays = _build(result)
    bundle, bundle_arrays, tables = _full_bundle(family, arrays)
    files = encode_bundle(
        bundle,
        bundle_arrays,
        tables,
        max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
    )

    loaded = load_bundle(files)

    assert loaded.bundle.families[F10_INDEX] == family
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert loaded.arrays[array_id].shape == values.shape
        assert np.array_equal(loaded.arrays[array_id], values)


def test_available_family_round_trips_through_the_codec() -> None:
    """Доступный результат тоже переживает кодек: форма поверхности сохраняется."""
    family, arrays = _build(_available())
    bundle, bundle_arrays, tables = _full_bundle(family, arrays)
    files = encode_bundle(
        bundle,
        bundle_arrays,
        tables,
        max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
    )

    loaded = load_bundle(files)

    assert loaded.bundle.families[F10_INDEX] == family
    assert loaded.arrays["f10_occupancy"].shape == _CELL
    assert loaded.arrays["f10_duration_quantile_s"].shape == _QUANTILE_CELL
    assert loaded.arrays["f10_quantile_valid"].dtype == np.uint8
