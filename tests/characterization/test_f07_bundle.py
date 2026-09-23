"""Покрытие маппера F07: ручные скалярные фикстуры, статусы, поддержка, кодек."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import (
    CharacterizationBundle,
    CharacterizationError,
    Status,
    Unit,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f07_bundle import F07_ID, F07_INDEX, build_f07_family
from lnt.characterization.f07_result import DECLARED_CODES, METHOD, F07Result
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F07_METHOD = "two_window_real_cepstrum_and_sideband_symmetry"
_FFT_SAMPLES = 16_384
_FS_HZ = 8000.0
_RECORD_S = 2.4
_SHORT_RECORD_S = 0.5
_DF_HZ = 250.0
_SYM_DB = -1.25
_Q_S = 0.004
_QUEFRENCY_AMPLITUDE = 3.75
_CARRIER_BIN = 33
_NAMES = (
    "f07_df_hz",
    "f07_sym_db",
    "f07_q_s",
    "f07_quefrency_amplitude",
    "f07_carrier_bin",
)
_VOCAB = (
    "below_resolution",
    "harmonic_comb_only",
    "log_floor_unstable",
    "no_dominant_quefrency",
    "window_dependent",
)


def _recipe() -> CharacterizationRecipe:
    """Рецепт-пример из репозитория, семейство F07 берётся по индексу."""
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    """Объявленное семейство F07 из рецепта."""
    return _recipe().families[F07_INDEX]


def _family_with(**overrides: object) -> CharacterizationFamily:
    """Копия объявленного семейства с подменённым параметром."""
    family = _family()
    parameters = tuple((name, overrides.get(name, value)) for name, value in family.parameters)
    return dataclasses.replace(family, parameters=parameters)


def _band() -> Band:
    """Полоса анализа из настроек STFT рецепта."""
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _available() -> F07Result:
    """Готовый скалярный результат без снятий: счётчики по F07-9."""
    return F07Result(
        status=Status.AVAILABLE, reason_codes=(), df_hz=_DF_HZ, sym_db=_SYM_DB, q_s=_Q_S,
        quefrency_amplitude=_QUEFRENCY_AMPLITUDE, carrier_bin=_CARRIER_BIN,
        sample_count=1, observation_count=1, missing_count=0, stored_count=1
    )  # fmt: skip


def _refusal(code: str) -> F07Result:
    """Отказ без выдуманных скаляров с одним объявленным кодом."""
    return F07Result(
        status=Status.UNAVAILABLE, reason_codes=(code,), df_hz=None, sym_db=None, q_s=None,
        quefrency_amplitude=None, carrier_bin=None,
        sample_count=1, observation_count=0, missing_count=1, stored_count=0
    )  # fmt: skip


def _replace(result: F07Result, **fields: object) -> F07Result:
    """Копия фикстуры с подменёнными полями без движка."""
    return dataclasses.replace(result, **fields)


def _build(
    result: F07Result,
    *,
    family: CharacterizationFamily | None = None,
    measured_channel: str = "ch1",
    record_duration_s: float = _RECORD_S,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Конверт F07 и словарь массивов для заданной ручной фикстуры."""
    return build_f07_family(
        result,
        _family() if family is None else family,
        _band(),
        measured_channel=measured_channel,
        record_duration_s=record_duration_s,
        sample_rate_hz=_FS_HZ,
    )


def _full_bundle(result: F07Result) -> tuple[CharacterizationBundle, dict[str, np.ndarray]]:
    """Полный бандл из 18 семейств для прогона через кодек."""
    band = _band()
    mapped, arrays = _build(result)
    families = tuple(
        mapped if index == F07_INDEX else not_computed_family(item, band)
        for index, item in enumerate(_recipe().families)
    )
    return CharacterizationBundle(families=families), arrays


def test_constants_match_recipe_slot() -> None:
    """Индекс, идентификатор, метод и словарь кодов совпадают с рецептом."""
    recipe = _recipe()
    assert F07_INDEX == 6
    assert F07_ID == "f07_comb_sideband_cepstrum"
    assert recipe.families[F07_INDEX].id == F07_ID
    assert recipe.families[F07_INDEX].method == METHOD == _F07_METHOD
    assert set(DECLARED_CODES) == set(_VOCAB)
    raw = recipe.families[F07_INDEX].value("fft_samples")
    assert not isinstance(raw, bool)
    assert isinstance(raw, int)
    assert raw == _FFT_SAMPLES


def test_available_publishes_five_scalars_and_no_arrays() -> None:
    """Скалярное семейство публикует пять сводок и ни одного массива."""
    mapped, arrays = _build(_available())
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert arrays == {}
    assert tuple(item.name for item in mapped.comparison_summary) == _NAMES
    assert tuple(item.unit for item in mapped.comparison_summary) == (
        Unit.HZ,
        Unit.RATIO,
        Unit.S,
        Unit.RATIO,
        Unit.COUNT,
    )
    assert mapped.units == (Unit.HZ, Unit.RATIO, Unit.S, Unit.COUNT)
    assert mapped.qc.passed is True
    assert mapped.method == _F07_METHOD


def test_summary_values_equal_result_fields() -> None:
    """Сводки повторяют скаляры результата один в один."""
    result = _available()
    mapped, _ = _build(result)
    summary = {item.name: item.value for item in mapped.comparison_summary}
    assert summary["f07_df_hz"] == result.df_hz == _DF_HZ
    assert summary["f07_sym_db"] == result.sym_db == _SYM_DB
    assert summary["f07_q_s"] == result.q_s == _Q_S
    assert summary["f07_quefrency_amplitude"] == result.quefrency_amplitude == _QUEFRENCY_AMPLITUDE
    carrier = result.carrier_bin
    assert carrier is not None
    assert summary["f07_carrier_bin"] == float(carrier) == float(_CARRIER_BIN)


def test_sym_db_none_omits_only_that_summary() -> None:
    """F07-14: пустая агрегация боковых снимает одну сводку, статус не меняется."""
    mapped, arrays = _build(_replace(_available(), sym_db=None))
    names = {item.name for item in mapped.comparison_summary}
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert "f07_sym_db" not in names
    assert names == set(_NAMES) - {"f07_sym_db"}
    assert arrays == {}


def test_window_is_the_declared_frame_and_support_is_one_scalar() -> None:
    """Окно это ведущий кадр fft_samples, поддержка копирует счётчики движка."""
    mapped, _ = _build(_available())
    frame_s = _FFT_SAMPLES / _FS_HZ
    assert mapped.window.kind == "fixed"
    assert mapped.window.sample_count is None
    assert mapped.window.duration_s == pytest.approx(frame_s)
    assert mapped.window.overlap_fraction == pytest.approx(0.0)
    assert mapped.support.start_s == pytest.approx(0.0)
    assert mapped.support.end_s == pytest.approx(frame_s)
    assert mapped.support.duration_s == pytest.approx(frame_s)
    assert mapped.support.sample_count == 1
    assert mapped.support.observation_count == 1
    assert mapped.support.missing_count == 0
    assert mapped.support.stored_count == 1
    assert mapped.support.selection_rule == "all"
    assert mapped.n == 1
    assert mapped.missing_rule == "exclude_and_count"
    assert mapped.filter.kind == "none"


def test_short_record_bounds_the_support_interval() -> None:
    """Запись короче кадра: наблюдённый интервал не длиннее записи."""
    mapped, _ = _build(_available(), record_duration_s=_SHORT_RECORD_S)
    assert mapped.support.start_s == pytest.approx(0.0)
    assert mapped.support.end_s == pytest.approx(_SHORT_RECORD_S)
    assert mapped.support.duration_s == pytest.approx(_SHORT_RECORD_S)
    assert mapped.window.duration_s == pytest.approx(_FFT_SAMPLES / _FS_HZ)


def test_every_declared_code_maps_to_unavailable_with_zero_support() -> None:
    """Каждый объявленный код это отказ без публикаций и с нулевой поддержкой."""
    for code in _VOCAB:
        mapped, arrays = _build(_refusal(code))
        assert mapped.status is Status.UNAVAILABLE
        assert mapped.reason_codes == (code,)
        assert mapped.array_refs == ()
        assert mapped.comparison_summary == ()
        assert mapped.qc.passed is False
        assert arrays == {}
        support = mapped.support
        assert (
            support.sample_count,
            support.observation_count,
            support.missing_count,
            support.stored_count,
        ) == (0, 0, 0, 0)
        assert support.duration_s == pytest.approx(0.0)
        assert mapped.n == 0


def test_partial_from_engine_is_refused() -> None:
    """Движок F07 частичности не знает: PARTIAL это нарушение статуса."""
    broken = _replace(_available(), status=Status.PARTIAL, reason_codes=("below_resolution",))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_available_with_reasons_is_refused() -> None:
    """Готовый результат с кодами отвергается."""
    broken = _replace(_available(), reason_codes=("below_resolution",))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_unavailable_without_reasons_is_refused() -> None:
    """Отказ без кодов отвергается."""
    broken = _replace(_refusal("below_resolution"), reason_codes=())
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_duplicate_reason_codes_are_refused() -> None:
    """Повтор кода в причинах отвергается."""
    broken = _replace(
        _refusal("below_resolution"), reason_codes=("below_resolution", "below_resolution")
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_undeclared_reason_code_is_refused() -> None:
    """Код вне объявленного словаря F07 отвергается."""
    broken = _replace(_refusal("below_resolution"), reason_codes=("not_an_f07_code",))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_wrong_family_slot_is_refused() -> None:
    """Маппер F07 принимает только объявленное семейство F07."""
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=_recipe().families[F07_INDEX - 1])


def test_non_integer_fft_samples_is_refused() -> None:
    """Объявленная длина кадра читается строго: нецелое и неположительное отвергаются."""
    for bad in (16_384.5, "16384", 0, True, None):
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(_available(), family=_family_with(fft_samples=bad))


def test_broken_support_counts_are_refused() -> None:
    """Расхождение счётчиков поддержки ломает инвариант."""
    for broken in (_replace(_available(), sample_count=2), _replace(_available(), stored_count=0)):
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_measured_channel_selects_signal_plane() -> None:
    """Канал измерения выбирает плоскость сигнала."""
    mapped, _ = _build(_available(), measured_channel="ch2")
    assert mapped.signal_plane == "ch2_transformer_secondary"


def test_f07_family_round_trips_through_the_codec() -> None:
    """Скалярное семейство переживает кодирование и загрузку без массивов."""
    bundle, arrays = _full_bundle(_available())
    files = encode_bundle(
        bundle, arrays, {}, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )
    loaded = load_bundle(files)
    assert loaded.bundle.families[F07_INDEX] == bundle.families[F07_INDEX]
    assert loaded.bundle.families[F07_INDEX].comparison_summary == (
        bundle.families[F07_INDEX].comparison_summary
    )
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}
