"""Покрытие маппера F03: ручные фикстуры, статусы, маски, кодек."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import (
    Band,
    CharacterizationBundle,
    CharacterizationError,
    Status,
    Unit,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f03_bundle import F03_ID, F03_INDEX, build_f03_family
from lnt.characterization.f03_result import METHOD, F03Result
from lnt.characterization.family_envelope import not_computed_family
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F03_METHOD = "synchronous_bin_nearest_neighbor_tracks"
_WINDOW_S = 0.2
_EVALUATED = 12
_VOCAB = (
    "below_resolution",
    "grid_unstable",
    "leakage_ambiguous",
    "peak_not_observed",
    "track_too_short",
)
_ARRAY_IDS = (
    "f03_f_hz",
    "f03_a_v",
    "f03_df_hz",
    "f03_t_life_s",
    "f03_windows_observed",
    "f03_windows_missing",
)


def _recipe() -> CharacterizationRecipe:
    """Рецепт-пример из репозитория, семейство F03 берётся по индексу."""
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    """Объявленное семейство F03 из рецепта."""
    return _recipe().families[F03_INDEX]


def _band() -> Band:
    """Полоса анализа из настроек STFT рецепта."""
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _vectors(n: int) -> dict[str, np.ndarray]:
    """Детерминированные векторы треков длиной n."""
    idx = np.arange(n, dtype=np.float64)
    return {
        "f_hz": 125.0 + 50.0 * idx,
        "a_v": 0.35 - 0.05 * idx,
        "df_hz": np.full(n, 5.0),
        "t_life_s": np.full(n, 2.4),
        "obs": np.full(n, _EVALUATED, dtype=np.int64),
        "miss": np.zeros(n, dtype=np.int64),
    }


def _available(n: int = 2) -> F03Result:
    """Готовый результат без снятий."""
    v = _vectors(n)
    return F03Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        f_hz=np.asarray(v["f_hz"], dtype=np.float64),
        a_v=np.asarray(v["a_v"], dtype=np.float64),
        df_hz=np.asarray(v["df_hz"], dtype=np.float64),
        t_life_s=np.asarray(v["t_life_s"], dtype=np.float64),
        windows_observed=np.asarray(v["obs"], dtype=np.int64),
        windows_missing=np.asarray(v["miss"], dtype=np.int64),
        evaluated_window_count=_EVALUATED,
        candidate_track_count=n,
        omitted_track_count=0,
        sample_count=n,
        observation_count=n,
        missing_count=0,
        stored_count=n,
    )


def _partial() -> F03Result:
    """Два трека при одном снятом: частичный учёт с масками."""
    v = _vectors(2)
    return F03Result(
        status=Status.PARTIAL,
        reason_codes=("leakage_ambiguous", "peak_not_observed"),
        f_hz=np.asarray(v["f_hz"], dtype=np.float64),
        a_v=np.asarray(v["a_v"], dtype=np.float64),
        df_hz=np.asarray(v["df_hz"], dtype=np.float64),
        t_life_s=np.asarray(v["t_life_s"], dtype=np.float64),
        windows_observed=np.asarray(v["obs"], dtype=np.int64),
        windows_missing=np.asarray(v["miss"], dtype=np.int64),
        evaluated_window_count=_EVALUATED,
        candidate_track_count=3,
        omitted_track_count=1,
        sample_count=3,
        observation_count=2,
        missing_count=1,
        stored_count=2,
    )


def _unavailable(code: str) -> F03Result:
    """Отказ без треков с одним объявленным кодом."""
    empty_f = np.empty(0, dtype=np.float64)
    empty_i = np.empty(0, dtype=np.int64)
    return F03Result(
        status=Status.UNAVAILABLE,
        reason_codes=(code,),
        f_hz=empty_f,
        a_v=empty_f.copy(),
        df_hz=empty_f.copy(),
        t_life_s=empty_f.copy(),
        windows_observed=empty_i,
        windows_missing=empty_i.copy(),
        evaluated_window_count=_EVALUATED,
        candidate_track_count=2,
        omitted_track_count=0,
        sample_count=2,
        observation_count=0,
        missing_count=2,
        stored_count=0,
    )


def _replace(result: F03Result, **fields: object) -> F03Result:
    """Копия фикстуры с подменёнными полями без движка."""
    return dataclasses.replace(result, **fields)


def _build_full(result: F03Result) -> tuple[CharacterizationBundle, dict[str, np.ndarray]]:
    """Полный бандл из 18 семейств для прогона через кодек."""
    recipe = _recipe()
    band = _band()
    mapped, arrays = build_f03_family(
        result, recipe.families[F03_INDEX], band, measured_channel="ch1", window_s=_WINDOW_S
    )
    families = tuple(
        mapped if i == F03_INDEX else not_computed_family(item, band)
        for i, item in enumerate(recipe.families)
    )
    return CharacterizationBundle(families=families), arrays


def test_constants_match_recipe_slot() -> None:
    """Индекс и идентификатор совпадают с рецептом и контрактом."""
    recipe = _recipe()
    assert F03_INDEX == 2
    assert F03_ID == "f03_interharmonic_tracking"
    assert recipe.families[F03_INDEX].id == F03_ID
    assert recipe.families[F03_INDEX].method == METHOD == _F03_METHOD
    raw_window = recipe.families[F03_INDEX].value("window_s")
    assert not isinstance(raw_window, bool)
    assert isinstance(raw_window, float | int)
    assert float(raw_window) == pytest.approx(_WINDOW_S)


def test_available_maps_vectors_to_arrays() -> None:
    """Векторы результата лежат в массивах без искажений."""
    result = _available()
    mapped, arrays = build_f03_family(
        result, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S
    )
    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert {ref.array_id for ref in mapped.array_refs} == set(_ARRAY_IDS)
    assert np.array_equal(arrays["f03_f_hz"], result.f_hz)
    assert np.array_equal(arrays["f03_a_v"], result.a_v)
    assert np.array_equal(arrays["f03_df_hz"], result.df_hz)
    assert np.array_equal(arrays["f03_t_life_s"], result.t_life_s)
    assert np.array_equal(arrays["f03_windows_observed"], result.windows_observed)
    assert np.array_equal(arrays["f03_windows_missing"], result.windows_missing)
    assert mapped.units == (Unit.HZ, Unit.V, Unit.S, Unit.COUNT)


def test_summaries_equal_result_fields() -> None:
    """Сводки повторяют счётчики результата один в один."""
    result = _partial()
    mapped, _ = build_f03_family(
        result, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S
    )
    summary = {item.name: item for item in mapped.comparison_summary}
    assert summary["f03_track_count"].value == float(result.observation_count) == 2.0
    assert summary["f03_omitted_track_count"].value == float(result.omitted_track_count) == 1.0
    assert summary["f03_track_count"].unit is Unit.COUNT
    assert summary["f03_omitted_track_count"].unit is Unit.COUNT


def test_window_and_support_fields() -> None:
    """Окно фиксировано, поддержка копирует учёт результата."""
    result = _available()
    mapped, _ = build_f03_family(
        result, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S
    )
    assert mapped.window.kind == "fixed"
    assert mapped.window.sample_count is None
    assert mapped.window.duration_s == pytest.approx(_WINDOW_S)
    assert mapped.window.overlap_fraction == pytest.approx(0.0)
    assert mapped.support.start_s == pytest.approx(0.0)
    assert mapped.support.end_s == pytest.approx(_EVALUATED * _WINDOW_S)
    assert mapped.support.duration_s == pytest.approx(_EVALUATED * _WINDOW_S)
    assert mapped.support.sample_count == result.sample_count
    assert mapped.support.observation_count == result.observation_count
    assert mapped.support.missing_count == result.missing_count
    assert mapped.support.stored_count == result.stored_count
    assert mapped.support.selection_rule == "all"
    assert mapped.n == result.observation_count


def test_partial_carries_per_array_valid_masks() -> None:
    """Частичный результат объявляет маску единиц на каждый массив."""
    result = _partial()
    mapped, arrays = build_f03_family(
        result, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S
    )
    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == ("leakage_ambiguous", "peak_not_observed")
    for ref in mapped.array_refs:
        mask_id = f"{ref.array_id}_valid"
        assert ref.validity_mask_id == mask_id
        assert arrays[mask_id].dtype == np.uint8
        assert arrays[mask_id].shape == arrays[ref.array_id].shape
        assert arrays[mask_id].tolist() == [1] * arrays[ref.array_id].size


def test_unavailable_publishes_no_arrays_and_zero_support() -> None:
    """Отказ не публикует ни массивов, ни сводок, поддержка нулевая."""
    result = _unavailable("peak_not_observed")
    mapped, arrays = build_f03_family(
        result, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S
    )
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == ("peak_not_observed",)
    assert mapped.array_refs == ()
    assert mapped.comparison_summary == ()
    assert arrays == {}
    assert mapped.support.observation_count == 0
    assert mapped.support.stored_count == 0
    assert mapped.support.sample_count == 0


def test_below_resolution_maps_to_unavailable() -> None:
    """Неразрешённая энергия окон это отказ с тем же кодом."""
    mapped, arrays = build_f03_family(
        _unavailable("below_resolution"),
        _family(),
        _band(),
        measured_channel="ch1",
        window_s=_WINDOW_S,
    )
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == ("below_resolution",)
    assert arrays == {}


def test_peak_not_observed_maps_to_unavailable() -> None:
    """Пустые окна без пиков это отказ с тем же кодом."""
    mapped, arrays = build_f03_family(
        _unavailable("peak_not_observed"),
        _family(),
        _band(),
        measured_channel="ch1",
        window_s=_WINDOW_S,
    )
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == ("peak_not_observed",)
    assert arrays == {}


def test_track_too_short_maps_to_unavailable() -> None:
    """Короткие треки не публикуются, код едет в конверт."""
    mapped, arrays = build_f03_family(
        _unavailable("track_too_short"),
        _family(),
        _band(),
        measured_channel="ch1",
        window_s=_WINDOW_S,
    )
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == ("track_too_short",)
    assert arrays == {}


def test_leakage_ambiguous_partial_keeps_tracks() -> None:
    """Спорные по утечке треки сняты, уцелевшие едут с кодом."""
    mapped, arrays = build_f03_family(
        _partial(), _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S
    )
    assert mapped.status is Status.PARTIAL
    assert "leakage_ambiguous" in mapped.reason_codes
    assert arrays["f03_f_hz"].size == 2


def test_grid_unstable_maps_to_unavailable() -> None:
    """Без сетки F01 собственной оценки нет."""
    mapped, arrays = build_f03_family(
        _unavailable("grid_unstable"),
        _family(),
        _band(),
        measured_channel="ch1",
        window_s=_WINDOW_S,
    )
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == ("grid_unstable",)
    assert arrays == {}


def test_measured_channel_selects_signal_plane() -> None:
    """Канал измерения выбирает плоскость сигнала."""
    mapped, _ = build_f03_family(
        _available(), _family(), _band(), measured_channel="ch2", window_s=_WINDOW_S
    )
    assert mapped.signal_plane == "ch2_transformer_secondary"


def test_closed_vocabulary_covers_every_declared_code() -> None:
    """Каждый код словаря F03 проходит, чужой отвергается."""
    assert set(_VOCAB) == {
        "below_resolution",
        "grid_unstable",
        "leakage_ambiguous",
        "peak_not_observed",
        "track_too_short",
    }
    for code in _VOCAB:
        mapped, _ = build_f03_family(
            _unavailable(code), _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S
        )
        assert mapped.reason_codes == (code,)
    broken = _replace(_unavailable("peak_not_observed"), reason_codes=("not_a_f03_code",))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f03_family(broken, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S)


def test_stored_mismatch_is_rejected() -> None:
    """Расхождение stored и observation ломает инвариант поддержки."""
    broken = _replace(_available(), stored_count=3)
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f03_family(broken, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S)


def test_available_with_reasons_is_rejected() -> None:
    """Готовый результат с кодами отвергается."""
    broken = _replace(_available(), reason_codes=("peak_not_observed",))
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f03_family(broken, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S)


def test_unavailable_without_reasons_is_rejected() -> None:
    """Отказ без кодов отвергается."""
    broken = _replace(_unavailable("peak_not_observed"), reason_codes=())
    with pytest.raises(CharacterizationError, match="status_invariant"):
        build_f03_family(broken, _family(), _band(), measured_channel="ch1", window_s=_WINDOW_S)


def test_f03_family_round_trips_through_the_codec() -> None:
    """Семейство переживает кодирование вместе с масками частичности."""
    bundle, arrays = _build_full(_partial())
    files = encode_bundle(
        bundle, arrays, {}, max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes
    )
    loaded = load_bundle(files)
    assert loaded.bundle.families[F03_INDEX] == bundle.families[F03_INDEX]
    for array_id in (*_ARRAY_IDS, "f03_f_hz_valid"):
        assert np.array_equal(loaded.arrays[array_id], arrays[array_id])
    assert loaded.tables == {}
