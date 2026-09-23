"""Сборка бандла F04: маппинг F04Result в FamilyResult с масками на массив."""

from __future__ import annotations

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
from lnt.characterization.f04_bundle import F04_ID, F04_INDEX, build_f04_family
from lnt.characterization.f04_periodicity import DECLARED_CODES, F04Result
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RECORD_S = 2.4
_TAU = (0.02, 0.04, 0.08, 0.16)
_MAINS = (1.1e-4, 9.0e-5, 7.5e-5, 6.0e-5)
_CARRIER = (2.2e-6, 1.9e-6, 1.7e-6, 1.5e-6)
_LAGS = (1, 2, 3, 4, 5, 6)
_ACF = (0.9, 0.7, 0.5, 0.3, 0.2, 0.1)


def _recipe() -> CharacterizationRecipe:
    """Рецепт из примера: контракт движка и семейства сверяются с ним."""
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    """Объявленное семейство F04 из рецепта."""
    recipe = _recipe()
    assert recipe.families[F04_INDEX].id == F04_ID
    return recipe.families[F04_INDEX]


def _band() -> Band:
    """Полоса из STFT-рецепта, общая для всех семейств."""
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _available_result() -> F04Result:
    """Полный доступный результат: сетка tau и лаги АКФ разной длины."""
    return F04Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        tau_s=np.array(_TAU, dtype=np.float64),
        adev_mains=np.array(_MAINS, dtype=np.float64),
        adev_carrier=np.array(_CARRIER, dtype=np.float64),
        acf_lag_cycles=np.array(_LAGS, dtype=np.int64),
        cycle_acf=np.array(_ACF, dtype=np.float64),
        carrier_to_mains_ratio=600.0,
        phase_slip_cycles=0.05,
        sample_count=120,
        observation_count=110,
        missing_count=10,
        stored_count=110,
        start_s=0.0,
        end_s=2.2,
    )


def _carrier_missing_result() -> F04Result:
    """Несущая недоступна: частичный результат без массива несущей."""
    base = _available_result()
    return F04Result(
        status=Status.PARTIAL,
        reason_codes=("carrier_unavailable",),
        tau_s=np.array(base.tau_s, dtype=np.float64),
        adev_mains=np.array(base.adev_mains, dtype=np.float64),
        adev_carrier=None,
        acf_lag_cycles=np.array(base.acf_lag_cycles, dtype=np.int64),
        cycle_acf=np.array(base.cycle_acf, dtype=np.float64),
        carrier_to_mains_ratio=None,
        phase_slip_cycles=base.phase_slip_cycles,
        sample_count=base.sample_count,
        observation_count=base.observation_count,
        missing_count=base.missing_count,
        stored_count=base.stored_count,
        start_s=base.start_s,
        end_s=base.end_s,
    )


def _carrier_values(base: F04Result) -> np.ndarray:
    """Массив несущей доступного результата без двусмысленного `or` на ndarray."""
    assert base.adev_carrier is not None
    return np.array(base.adev_carrier, dtype=np.float64)


def _truncated_result() -> F04Result:
    """Усечённая сетка tau: частичный результат с полным набором массивов."""
    base = _available_result()
    return F04Result(
        status=Status.PARTIAL,
        reason_codes=("record_too_short_for_tau",),
        tau_s=np.array(base.tau_s, dtype=np.float64),
        adev_mains=np.array(base.adev_mains, dtype=np.float64),
        adev_carrier=_carrier_values(base),
        acf_lag_cycles=np.array(base.acf_lag_cycles, dtype=np.int64),
        cycle_acf=np.array(base.cycle_acf, dtype=np.float64),
        carrier_to_mains_ratio=base.carrier_to_mains_ratio,
        phase_slip_cycles=base.phase_slip_cycles,
        sample_count=base.sample_count,
        observation_count=base.observation_count,
        missing_count=base.missing_count,
        stored_count=base.stored_count,
        start_s=base.start_s,
        end_s=base.end_s,
    )


def _unavailable_result() -> F04Result:
    """Отказ движка: пустые сетки и интервалы None."""
    return F04Result(
        status=Status.UNAVAILABLE,
        reason_codes=("not_enough_samples",),
        tau_s=np.empty(0, dtype=np.float64),
        adev_mains=None,
        adev_carrier=None,
        acf_lag_cycles=np.empty(0, dtype=np.int64),
        cycle_acf=np.empty(0, dtype=np.float64),
        carrier_to_mains_ratio=None,
        phase_slip_cycles=None,
        sample_count=120,
        observation_count=100,
        missing_count=20,
        stored_count=100,
        start_s=None,
        end_s=None,
    )


def _build(
    result: F04Result,
) -> tuple[FamilyResult, dict[str, np.ndarray]]:
    """Маппинг одного семейства поверх объявленных семейства и полосы."""
    return build_f04_family(
        result, _family(), _band(), measured_channel="ch1", record_duration_s=_RECORD_S
    )


def _full_bundle(
    family: FamilyResult, arrays: dict[str, np.ndarray]
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Полный бандл из 18 семейств: F04 в своём слоте, остальное not_computed."""
    recipe = _recipe()
    band = _band()
    families = tuple(
        family if index == F04_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), {}


def test_constants_match_recipe_and_contract() -> None:
    """Индекс и идентификатор берутся из рецепта, а не выдумываются."""
    recipe = _recipe()
    assert F04_INDEX == 3
    assert F04_ID == "f04_multicycle_periodicity"
    assert FAMILY_IDS[F04_INDEX] == F04_ID
    assert recipe.families[F04_INDEX].id == F04_ID
    assert (
        recipe.families[F04_INDEX].method == "overlapping_allan_deviation_and_cycle_autocorrelation"
    )
    assert recipe.families[F04_INDEX].method_version == 1


def test_available_publishes_all_arrays_without_masks() -> None:
    """Доступный результат публикует пять массивов без масок и причин."""
    family, arrays = _build(_available_result())

    assert family.family_id == F04_ID
    assert family.status is Status.AVAILABLE
    assert family.reason_codes == ()
    assert family.units == (Unit.S, Unit.RATIO, Unit.COUNT)
    assert {ref.array_id for ref in family.array_refs} == {
        "f04_tau_s",
        "f04_adev_mains",
        "f04_adev_carrier",
        "f04_acf_lag_cycles",
        "f04_cycle_acf",
    }
    assert all(ref.validity_mask_id is None for ref in family.array_refs)
    assert not any(name.endswith("_valid") for name in arrays)
    assert np.array_equal(arrays["f04_tau_s"], np.array(_TAU, dtype=np.float64))
    assert np.array_equal(arrays["f04_adev_mains"], np.array(_MAINS, dtype=np.float64))
    assert np.array_equal(arrays["f04_adev_carrier"], np.array(_CARRIER, dtype=np.float64))
    assert np.array_equal(arrays["f04_acf_lag_cycles"], np.array(_LAGS, dtype=np.int64))
    assert np.array_equal(arrays["f04_cycle_acf"], np.array(_ACF, dtype=np.float64))


def test_carrier_none_is_partial_without_carrier_array() -> None:
    """Без несущей массив несущей отсутствует, а отношение несущей не публикуется."""
    family, arrays = _build(_carrier_missing_result())

    assert family.status is Status.PARTIAL
    assert family.reason_codes == ("carrier_unavailable",)
    assert "f04_adev_carrier" not in arrays
    assert {ref.array_id for ref in family.array_refs} == {
        "f04_tau_s",
        "f04_adev_mains",
        "f04_acf_lag_cycles",
        "f04_cycle_acf",
    }
    assert all(ref.validity_mask_id == f"{ref.array_id}_valid" for ref in family.array_refs)
    assert "f04_carrier_to_mains_ratio" not in {item.name for item in family.comparison_summary}


def test_truncated_tau_is_partial_with_per_array_masks() -> None:
    """Усечённая сетка публикуется частичной с маской на каждом массиве."""
    family, arrays = _build(_truncated_result())

    assert family.status is Status.PARTIAL
    assert family.reason_codes == ("record_too_short_for_tau",)
    for ref in family.array_refs:
        mask_id = f"{ref.array_id}_valid"
        assert ref.validity_mask_id == mask_id
        assert arrays[mask_id].dtype == np.uint8
        assert arrays[mask_id].shape == ref.shape
        assert set(np.unique(arrays[mask_id]).tolist()) <= {0, 1}
        assert int(np.count_nonzero(arrays[mask_id])) == ref.shape[0]


def test_unavailable_publishes_no_arrays_with_zero_support() -> None:
    """Отказ не публикует ни массивов, ни сводок, поддержка нулевая."""
    family, arrays = _build(_unavailable_result())

    assert family.status is Status.UNAVAILABLE
    assert family.reason_codes == ("not_enough_samples",)
    assert family.array_refs == ()
    assert family.comparison_summary == ()
    assert arrays == {}
    assert family.support.observation_count == 0
    assert family.support.stored_count == 0
    assert family.support.duration_s == 0.0


def test_different_length_grids_coexist_with_own_masks() -> None:
    """Сетка tau и лаги АКФ разной длины живут рядом со своими масками."""
    family, arrays = _build(_truncated_result())
    by_id = {ref.array_id: ref for ref in family.array_refs}

    assert by_id["f04_tau_s"].shape == (len(_TAU),)
    assert by_id["f04_acf_lag_cycles"].shape == (len(_LAGS),)
    assert len(_TAU) != len(_LAGS)
    assert arrays["f04_tau_s_valid"].shape == (len(_TAU),)
    assert arrays["f04_acf_lag_cycles_valid"].shape == (len(_LAGS),)
    assert arrays["f04_tau_s_valid"].shape != arrays["f04_acf_lag_cycles_valid"].shape


def test_summaries_carry_declared_units_and_values() -> None:
    """Сводки публикуются только при значениях не None, с единицами из словаря."""
    family, _ = _build(_available_result())
    summaries = {item.name: item for item in family.comparison_summary}

    assert summaries["f04_phase_slip_cycles"].value == pytest.approx(0.05)
    assert summaries["f04_phase_slip_cycles"].unit is Unit.COUNT
    assert summaries["f04_carrier_to_mains_ratio"].value == pytest.approx(600.0)
    assert summaries["f04_carrier_to_mains_ratio"].unit is Unit.RATIO


def test_window_and_support_follow_the_record() -> None:
    """Окно это запись, поддержка копирует счётчики результата один в один."""
    result = _available_result()
    family, _ = _build(result)

    assert family.window.kind == "record"
    assert family.window.duration_s == _RECORD_S
    assert family.window.overlap_fraction == 0.0
    start_raw = result.start_s
    end_raw = result.end_s
    assert start_raw is not None
    assert end_raw is not None
    assert family.support.start_s == pytest.approx(start_raw)
    assert family.support.end_s == pytest.approx(end_raw)
    assert family.support.duration_s == pytest.approx(end_raw - start_raw)
    assert family.support.sample_count == result.sample_count
    assert family.support.observation_count == result.observation_count
    assert family.support.missing_count == result.missing_count
    assert family.support.stored_count == result.stored_count
    assert family.support.selection_rule == "all"
    assert family.n == result.observation_count


def test_measured_channel_selects_signal_plane() -> None:
    """Канал измерения выбирает плоскость сигнала конверта."""
    family, _ = build_f04_family(
        _available_result(),
        _family(),
        _band(),
        measured_channel="ch2",
        record_duration_s=_RECORD_S,
    )

    assert family.signal_plane == "ch2_transformer_secondary"


def test_family_round_trips_through_the_codec() -> None:
    """Семейство с масками переживает кодирование и загрузку без потерь."""
    family, arrays = _build(_truncated_result())
    bundle, bundle_arrays, tables = _full_bundle(family, arrays)
    files = encode_bundle(
        bundle,
        bundle_arrays,
        tables,
        max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
    )

    loaded = load_bundle(files)

    assert loaded.bundle.families[F04_INDEX] == family
    for array_id, values in arrays.items():
        assert np.array_equal(loaded.arrays[array_id], values)


def test_reason_codes_stay_within_declared_vocabulary() -> None:
    """Все опубликованные коды принадлежат объявленному словарю движка."""
    for codes in ((), ("carrier_unavailable",), ("record_too_short_for_tau",)):
        assert all(code in DECLARED_CODES for code in codes)
    assert set(DECLARED_CODES) == {
        "record_too_short_for_tau",
        "carrier_unavailable",
        "phase_unwrap_failed",
        "not_enough_samples",
        "grid_unstable",
    }
    family, _ = _build(_truncated_result())
    assert all(code in DECLARED_CODES for code in family.reason_codes)


def test_unknown_reason_code_is_rejected() -> None:
    """Чужой код причины отвергается, а не просачивается в конверт."""
    base = _available_result()
    broken = F04Result(
        status=Status.PARTIAL,
        reason_codes=("not_computed",),
        tau_s=np.array(base.tau_s, dtype=np.float64),
        adev_mains=np.array(base.adev_mains, dtype=np.float64),
        adev_carrier=_carrier_values(base),
        acf_lag_cycles=np.array(base.acf_lag_cycles, dtype=np.int64),
        cycle_acf=np.array(base.cycle_acf, dtype=np.float64),
        carrier_to_mains_ratio=base.carrier_to_mains_ratio,
        phase_slip_cycles=base.phase_slip_cycles,
        sample_count=base.sample_count,
        observation_count=base.observation_count,
        missing_count=base.missing_count,
        stored_count=base.stored_count,
        start_s=base.start_s,
        end_s=base.end_s,
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_available_with_reasons_is_rejected() -> None:
    """Доступный результат с причинами противоречит инварианту статуса."""
    base = _available_result()
    broken = F04Result(
        status=Status.AVAILABLE,
        reason_codes=("carrier_unavailable",),
        tau_s=np.array(base.tau_s, dtype=np.float64),
        adev_mains=np.array(base.adev_mains, dtype=np.float64),
        adev_carrier=_carrier_values(base),
        acf_lag_cycles=np.array(base.acf_lag_cycles, dtype=np.int64),
        cycle_acf=np.array(base.cycle_acf, dtype=np.float64),
        carrier_to_mains_ratio=base.carrier_to_mains_ratio,
        phase_slip_cycles=base.phase_slip_cycles,
        sample_count=base.sample_count,
        observation_count=base.observation_count,
        missing_count=base.missing_count,
        stored_count=base.stored_count,
        start_s=base.start_s,
        end_s=base.end_s,
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_stored_count_mismatch_is_rejected() -> None:
    """Расхождение хранимого и наблюдаемого учёта отвергается до конверта."""
    base = _available_result()
    broken = F04Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        tau_s=np.array(base.tau_s, dtype=np.float64),
        adev_mains=np.array(base.adev_mains, dtype=np.float64),
        adev_carrier=_carrier_values(base),
        acf_lag_cycles=np.array(base.acf_lag_cycles, dtype=np.int64),
        cycle_acf=np.array(base.cycle_acf, dtype=np.float64),
        carrier_to_mains_ratio=base.carrier_to_mains_ratio,
        phase_slip_cycles=base.phase_slip_cycles,
        sample_count=base.sample_count,
        observation_count=base.observation_count,
        missing_count=base.missing_count,
        stored_count=base.observation_count - 1,
        start_s=base.start_s,
        end_s=base.end_s,
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)
