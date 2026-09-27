"""F18 persistence mapper: triad domain, masked absence, and locked metadata."""

from __future__ import annotations

import dataclasses
import functools
from pathlib import Path
from typing import TYPE_CHECKING, Final

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_store.characterization_settings import ResourceLimits, StftSettings
from lnt.characterization import (
    FAMILY_IDS,
    CharacterizationBundle,
    CharacterizationError,
    Status,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.event_models import (
    RootEvents,
    RootEventSettings,
    RootTimelineItem,
)
from lnt.characterization.f18_bundle import (
    F18_ID,
    F18_INDEX,
    F18_METADATA_TABLE_ID,
    build_f18_family,
    decode_f18_result,
)
from lnt.characterization.f18_contract import (
    ADJUSTED_P_NAME,
    ARTIFACT_LIMIT,
    BASE_FREQUENCIES_HZ,
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    CLAIM_BOUNDARY,
    DECLARED_CODES,
    DUAL_P_NAME,
    IAAFT_NOT_CONVERGED,
    IAAFT_P_NAME,
    IAAFT_SURROGATE_COUNT,
    INSUFFICIENT_FRAMES,
    METHOD,
    PHASE_RANDOMIZED_P_NAME,
    PHASE_REFERENCE_UNAVAILABLE,
    SPEC_GAPS,
    SURROGATE_SEED,
    TRIAD_ABOVE_NYQUIST,
    TRIAD_HIGH_NAME,
    TRIAD_LOW_NAME,
    TRIAD_OFF_GRID,
    TRIAD_SUM_NAME,
    segment_samples_for,
)
from lnt.characterization.f18_engine import compute_f18_bicoherence_triads
from lnt.characterization.f18_result import F18Declarations, F18Result
from lnt.characterization.f18_tables import (
    BIPHASE_MASK,
    PERSISTED_QUANTITIES,
    SIGNIFICANT_NAME,
    TRIAD_AVAILABLE_NAME,
)
from lnt.characterization.f18_triads import build_triad_grid
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Band, validate_unit_name
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_OFF_GRID_SAMPLE_RATE_HZ: Final = 48_000_000.0
# 1.024 МГц: сегмент round(0.001 * 1024000) = 1024 отсчёта, поэтому шаг сетки равен
# 1000 Hz и все 15 declared триад измеримы. 32 кадра — ровно locked minimum_frames.
_EXACT_GRID_SAMPLE_RATE_HZ: Final = 1_024_000.0
_EXACT_GRID_SEGMENT: Final = 1_024
_SAMPLES: Final = _EXACT_GRID_SEGMENT + 31 * (_EXACT_GRID_SEGMENT // 2)
_FRAMES: Final = 32
_ARRAY_IDS: Final = (
    TRIAD_LOW_NAME,
    TRIAD_HIGH_NAME,
    TRIAD_SUM_NAME,
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    PHASE_RANDOMIZED_P_NAME,
    IAAFT_P_NAME,
    DUAL_P_NAME,
    ADJUSTED_P_NAME,
    TRIAD_AVAILABLE_NAME,
    SIGNIFICANT_NAME,
    "f18_frame_support",
)
_MEASUREMENT_IDS: Final = (
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    PHASE_RANDOMIZED_P_NAME,
    IAAFT_P_NAME,
    DUAL_P_NAME,
    ADJUSTED_P_NAME,
)
_RESULT_FIELDS: Final = tuple(field.name for field in dataclasses.fields(F18Result))


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F18_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=262_144,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=199,
        deterministic_seed=SURROGATE_SEED,
    )


def _settings() -> StftSettings:
    return StftSettings(
        window="hann_periodic",
        segment_samples=_EXACT_GRID_SEGMENT,
        overlap_fraction=0.5,
        detrend="constant",
        analysis_low_hz=3_000.0,
        analysis_high_hz=200_000.0,
        nyquist_fraction_max=0.45,
    )


def _inventory(sample_count: int) -> RootEvents:
    """Пустой измеренный инвентарь: F18 считает gaps, а не сами события."""

    def replay(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        return iter(())

    settings = RootEventSettings(
        recipe_sha256="test",
        detector="existing_event_inventory",
        noise_window_samples=2_048,
        noise_step_samples=1_024,
        minimum_noise_samples=1_024,
        threshold_sigma=5.0,
        max_gap_samples=4,
        minimum_event_samples=1,
        minimum_snr_db=10.0,
        minimum_snr_ratio=3.9810717055349722,
        dead_time_s=0.001,
        dead_time_samples=10,
        chunk_samples=4_096,
        fft_max_samples=1_048_576,
        clipping_low_v=None,
        clipping_high_v=None,
        clipping_reason_code="not_applicable",
        dead_time_handling="exclude_intervals",
        gap_handling="exclude_crossing_intervals",
    )
    return RootEvents(
        sample_rate_hz=_EXACT_GRID_SAMPLE_RATE_HZ,
        sample_count=sample_count,
        events=(),
        gaps=(),
        exclusions=(),
        candidate_count=0,
        snr_rejected_count=0,
        accepted_count=0,
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=0,
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=replay,
    )


def _phase() -> PhaseCycles:
    step = round(_EXACT_GRID_SAMPLE_RATE_HZ / 50.0)
    starts = np.arange(0, _SAMPLES, step, dtype=np.float64)
    ends = np.append(starts[1:], float(_SAMPLES))
    return PhaseCycles(
        sample_rate_hz=_EXACT_GRID_SAMPLE_RATE_HZ,
        sample_count=_SAMPLES,
        cycle_start_samples=starts,
        cycle_end_samples=ends,
        cycle_valid=np.ones(ends.size, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _means() -> PhaseMeans:
    return PhaseMeans(
        means_v=np.zeros(64, dtype=np.float64),
        counts=np.full(64, 1_024, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _coupled_record() -> np.ndarray:
    time = np.arange(_SAMPLES, dtype=np.float64) / _EXACT_GRID_SAMPLE_RATE_HZ
    values = np.zeros(_SAMPLES, dtype=np.float64)
    for low, high, phase in ((3_000.0, 5_000.0, 0.7), (10_000.0, 20_000.0, -0.4)):
        values += np.cos(2.0 * np.pi * low * time)
        values += np.cos(2.0 * np.pi * high * time)
        values += 0.5 * np.cos(2.0 * np.pi * (low + high) * time + phase)
    values += np.cos(2.0 * np.pi * 50_000.0 * time)
    values += 0.5 * np.cos(2.0 * np.pi * 60_000.0 * time + 1.1)
    values += 0.5 * np.cos(2.0 * np.pi * 70_000.0 * time - 1.6)
    return values


@functools.lru_cache(maxsize=1)
def _available_result() -> F18Result:
    """Exact-grid 1.024 MHz fixture: все 15 triad измеримы и BH даёт значимые."""
    return compute_f18_bicoherence_triads(
        _coupled_record(),
        _phase(),
        _means(),
        _inventory(_SAMPLES),
        F18Declarations.locked(),
        settings=_settings(),
        resources=_resources(),
    )


def _partial_result() -> F18Result:
    return dataclasses.replace(
        _available_result(),
        status=Status.PARTIAL,
        reason_codes=(IAAFT_NOT_CONVERGED,),
        iaaft_converged_count=IAAFT_SURROGATE_COUNT - 1,
    )


def _unavailable(reason: str, sample_rate_hz: float) -> F18Result:
    empty_float = np.empty(0, dtype=np.float64)
    return F18Result(
        status=Status.UNAVAILABLE,
        reason_codes=(reason,),
        triad_low_hz=empty_float,
        triad_high_hz=empty_float,
        triad_sum_hz=empty_float,
        bicoherence_squared=empty_float,
        biphase_rad=empty_float,
        phase_randomized_p_value=empty_float,
        iaaft_p_value=empty_float,
        dual_null_p_value=empty_float,
        adjusted_p_value=empty_float,
        triad_available=np.empty(0, dtype=np.bool_),
        significant=np.empty(0, dtype=np.bool_),
        frame_support=np.empty(0, dtype=np.int64),
        sample_count=_SAMPLES,
        qualified_sample_count=0,
        analysis_rate_hz=sample_rate_hz,
        segment_samples=segment_samples_for(sample_rate_hz),
        frame_count=0,
        declared_triad_count=0,
        measurable_triad_count=0,
        off_grid_triad_count=0,
        above_nyquist_triad_count=0,
        dropped_triad_count=0,
        iaaft_converged_count=0,
    )


def _build(
    result: F18Result,
    *,
    family: CharacterizationFamily | None = None,
    record_duration_s: float = 2.4,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f18_family(
        result,
        _family() if family is None else family,
        _band(),
        record_duration_s=record_duration_s,
    )


def _full_bundle(
    mapped: FamilyResult, arrays: dict[str, np.ndarray], tables: dict[str, TableBlock]
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    recipe = _recipe()
    band = _band()
    families = tuple(
        mapped if index == F18_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def _round_trip(
    result: F18Result,
) -> tuple[F18Result, dict[str, np.ndarray], dict[str, TableBlock]]:
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
    restored = decode_f18_result(loaded.bundle.families[F18_INDEX], loaded.arrays, loaded.tables)
    return restored, dict(loaded.arrays), dict(loaded.tables)


def _without_validation(result: F18Result, **fields: object) -> F18Result:
    broken = object.__new__(F18Result)
    for field in dataclasses.fields(F18Result):
        object.__setattr__(broken, field.name, getattr(result, field.name))
    for name, value in fields.items():
        object.__setattr__(broken, name, value)
    return broken


def _assert_result_equal(actual: F18Result, expected: F18Result) -> None:
    for name in _RESULT_FIELDS:
        left = getattr(actual, name)
        right = getattr(expected, name)
        if isinstance(right, np.ndarray):
            assert isinstance(left, np.ndarray)
            assert left.dtype == right.dtype
            assert left.shape == right.shape
            assert np.array_equal(left, right, equal_nan=True)
        else:
            assert left == right


def test_off_grid_48mhz_unavailable_publishes_empty_domains() -> None:
    """48 MHz path stays UNAVAILABLE and never publishes zero-filled F18 output."""
    result = _unavailable(TRIAD_OFF_GRID, _OFF_GRID_SAMPLE_RATE_HZ)
    mapped, arrays, tables = _build(result, record_duration_s=_SAMPLES / _OFF_GRID_SAMPLE_RATE_HZ)
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, arrays, tables)
    loaded = load_bundle(
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    )

    assert F18_ID == "f18_bicoherence_triads"
    assert F18_INDEX == 17
    assert FAMILY_IDS[F18_INDEX] == F18_ID
    assert METHOD == "declared_normalized_bicoherence_dual_surrogate"
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (TRIAD_OFF_GRID,)
    assert mapped.array_refs == mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert arrays == tables == {}
    assert loaded.bundle.families[F18_INDEX] == mapped
    assert dict(loaded.arrays) == dict(loaded.tables) == {}
    assert F18_METADATA_TABLE_ID == "f18_bicoherence_metadata"


def test_8k_nyquist_clamp_unavailable_uses_above_nyquist_reason() -> None:
    """8 kHz clamp gives effective_high=3600 Hz, below smallest 6000 Hz sum."""
    mapped, arrays, tables = _build(
        _unavailable(TRIAD_ABOVE_NYQUIST, 8_000.0), record_duration_s=_SAMPLES / 8_000.0
    )

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (TRIAD_ABOVE_NYQUIST,)
    assert arrays == tables == {}


def test_exact_grid_available_codec_round_trip_restores_every_field() -> None:
    """1.024 MHz fixture переживает encode/load/decode без потери dtype или values."""
    result = _available_result()
    mapped, arrays, tables = _build(result)
    restored, loaded_arrays, loaded_tables = _round_trip(result)

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.frame_count == _FRAMES
    assert result.declared_triad_count == 15
    assert tuple(reference.array_id for reference in mapped.array_refs) == _ARRAY_IDS
    assert set(tables) == {F18_METADATA_TABLE_ID}
    assert set(loaded_arrays) == set(arrays)
    assert loaded_tables == tables
    _assert_result_equal(restored, result)
    for array_id, values in arrays.items():
        assert loaded_arrays[array_id].dtype == values.dtype
        assert loaded_arrays[array_id].shape == values.shape
        np.testing.assert_array_equal(loaded_arrays[array_id], values)


def test_persisted_array_schema_has_exact_ids_dtypes_shapes_and_order() -> None:
    """Каждый F18 array остаётся в полном declared-triad index space."""
    mapped, arrays, _ = _build(_available_result())

    assert mapped.array_refs[0].shape == (15,)
    assert mapped.array_refs[-1].shape == (15,)
    assert [reference.dtype for reference in mapped.array_refs] == [
        "float64",
        "float64",
        "float64",
        "float64",
        "float64",
        "float64",
        "float64",
        "float64",
        "float64",
        "uint8",
        "uint8",
        "int64",
    ]
    assert arrays[BICOHERENCE_NAME].dtype == np.dtype(np.float64)
    assert arrays[BIPHASE_NAME].dtype == np.dtype(np.float64)
    assert arrays[TRIAD_AVAILABLE_NAME].dtype == np.dtype(np.uint8)
    assert arrays[SIGNIFICANT_NAME].dtype == np.dtype(np.uint8)
    assert arrays["f18_frame_support"].dtype == np.dtype(np.int64)
    assert all(values.shape == (15,) for values in arrays.values())
    assert all(
        validate_unit_name(reference.array_id, reference.unit) is None
        for reference in mapped.array_refs
    )


def test_structural_biphase_absence_uses_zero_filler_and_significance_mask() -> None:
    """Masked-out biphase хранит только 0.0; decode возвращает structural NaN."""
    result = _available_result()
    mapped, arrays, _ = _build(result)
    restored, _, _ = _round_trip(result)
    absent = ~result.significant

    assert bool(np.any(absent))
    assert arrays[BIPHASE_MASK].dtype == np.dtype(np.uint8)
    np.testing.assert_array_equal(arrays[BIPHASE_MASK], result.significant.astype(np.uint8))
    assert np.all(arrays[BIPHASE_NAME][absent] == 0.0)
    assert np.all(np.isfinite(arrays[BIPHASE_NAME]))
    assert np.all(np.isnan(restored.biphase_rad[absent]))
    assert restored.status is Status.AVAILABLE
    assert all(
        validate_unit_name(reference.array_id, reference.unit) is None
        for reference in mapped.array_refs
    )


def test_zero_radian_is_a_real_measurement_not_an_absence_sentinel() -> None:
    """Значимая biphase=0.0 остаётся измерением под mask и не исчезает."""
    result = _available_result()
    zero_phase = dataclasses.replace(
        result,
        biphase_rad=np.where(result.significant, 0.0, np.nan),
    )
    mapped, arrays, _ = _build(zero_phase)
    restored, _, _ = _round_trip(zero_phase)

    assert mapped.status is Status.AVAILABLE
    assert np.any(result.significant)
    assert np.all(arrays[BIPHASE_NAME][result.significant] == 0.0)
    assert np.all(restored.biphase_rad[result.significant] == 0.0)
    assert np.all(np.isnan(restored.biphase_rad[~result.significant]))


def test_partial_structural_absence_does_not_degrade_available_support() -> None:
    """98 IAAFT surrogates дают PARTIAL/reason, но все 15 triad остаются измеримыми."""
    result = _partial_result()
    mapped, arrays, _ = _build(result)
    restored, _, _ = _round_trip(result)

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (IAAFT_NOT_CONVERGED,)
    assert mapped.reason_codes == (IAAFT_NOT_CONVERGED,)
    assert int(np.count_nonzero(result.triad_available)) == 15
    assert np.count_nonzero(arrays[TRIAD_AVAILABLE_NAME]) == 15
    assert all(reference.validity_mask_id is not None for reference in mapped.array_refs)
    _assert_result_equal(restored, result)


def test_declared_axis_maps_through_distinct_bins_and_rows_without_compaction() -> None:
    """Persisted axes полные 15 rows; compact distinct bins остаются engine-only."""
    result = _available_result()
    grid = build_triad_grid(
        BASE_FREQUENCIES_HZ,
        segment_samples=_EXACT_GRID_SEGMENT,
        sample_rate_hz=_EXACT_GRID_SAMPLE_RATE_HZ,
        analysis_low_hz=3_000.0,
        analysis_high_hz=200_000.0,
        nyquist_fraction_max=0.45,
        maximum_triads=4_096,
    )
    _, arrays, _ = _build(result)
    frequency_axis = np.fft.rfftfreq(_EXACT_GRID_SEGMENT, d=1.0 / _EXACT_GRID_SAMPLE_RATE_HZ)

    assert grid.distinct_bins.ndim == 1
    assert grid.rows.shape == (15, 3)
    assert arrays[TRIAD_LOW_NAME].shape == grid.low_hz.shape == (15,)
    assert arrays[TRIAD_HIGH_NAME].shape == grid.high_hz.shape == (15,)
    assert arrays[TRIAD_SUM_NAME].shape == grid.sum_hz.shape == (15,)
    np.testing.assert_array_equal(arrays[TRIAD_AVAILABLE_NAME], grid.measurable.astype(np.uint8))
    for triad_index, row in enumerate(grid.rows):
        low_bin, high_bin, sum_bin = (int(grid.distinct_bins[value]) for value in row)
        assert arrays[TRIAD_LOW_NAME][triad_index] == frequency_axis[low_bin]
        assert arrays[TRIAD_HIGH_NAME][triad_index] == frequency_axis[high_bin]
        assert arrays[TRIAD_SUM_NAME][triad_index] == frequency_axis[sum_bin]
    assert "f18_distinct_bins" not in arrays
    assert "f18_rows" not in arrays


def test_metadata_table_carries_full_locked_truth_in_one_row() -> None:
    """Одна metadata row сохраняет identity, recipe, conventions, gaps и quantities."""
    _, _, tables = _build(_available_result())
    table = tables[F18_METADATA_TABLE_ID]
    metadata = dict(zip((column.name for column in table.columns), table.rows[0], strict=True))

    assert table.row_count == table.stored_count == 1
    assert table.selection_rule == "all"
    assert metadata["family_id"] == F18_ID
    assert metadata["family_index"] == F18_INDEX
    assert metadata["method"] == METHOD
    assert metadata["method_version"] == 1
    assert metadata["claim_boundary"] == CLAIM_BOUNDARY
    assert metadata["bicoherence_convention"] == "squared_normalized_bicoherence_in_zero_one"
    assert metadata["biphase_availability"] == "significant_triad_with_nonzero_bispectrum_magnitude"
    assert (
        metadata["triad_cap_convention"] == "maximum_triads_bounds_the_candidate_count_not_the_rule"
    )
    assert metadata["frequency_mapping"] == "exact_fft_bins"
    # Обе формы сегмента опубликованы: объявленная длительность и выведенные
    # движком отсчёты, поэтому decoder может восстановить rate-зависимое поле.
    assert metadata["segment_duration_s"] == 0.001
    assert metadata["segment_samples"] == _EXACT_GRID_SEGMENT == 1_024
    # Частота анализа опубликована вместе с сегментом: она и есть причина, по которой
    # отсчёты сегмента rate-зависимы, поэтому артефакт не должен молчать о ней.
    assert metadata["analysis_rate_hz"] == _EXACT_GRID_SAMPLE_RATE_HZ == 1_024_000.0
    assert len(table.columns) == len(table.rows[0]) == 74
    assert tuple(metadata[f"spec_gap_{index}"] for index in range(1, 7)) == SPEC_GAPS
    for _, name, unit in PERSISTED_QUANTITIES:
        assert metadata[f"{name}_quantity_name"] == name
        assert metadata[f"{name}_unit"] == unit.value


def test_iaaft_non_convergence_finding_is_published_verbatim_in_the_decoded_artifact() -> None:
    """F18-6 обязана дойти до артефакта байт-в-байт: находка опубликована, не закомментирована.

    Клетка берётся из ДЕКОДИРОВАННОГО артефакта, а не из таблицы сборки: encode_bundle +
    load_bundle проходят и запись, и декодер, поэтому равенство cell == SPEC_GAPS[5] доказывает,
    что находка пережила публикацию целиком. Пересказ (paraphrase) здесь не проходит — сравнение
    точное.
    """
    _, _, tables = _round_trip(_available_result())
    table = tables[F18_METADATA_TABLE_ID]
    metadata = dict(zip((column.name for column in table.columns), table.rows[0], strict=True))
    cell = metadata["spec_gap_6"]
    assert isinstance(cell, str)

    assert len(SPEC_GAPS) == 6
    assert cell == SPEC_GAPS[5]
    assert cell.startswith("F18-6: the IAAFT iteration does not converge")
    # Находка говорит ровно измеренное: итерация не сходится, а опубликованная
    # статистика не двигается — обе половины обязаны пережить публикацию.
    assert "flat at about 1.35 from iteration 1 to iteration 200" in cell
    assert "produced_err is about 3e-16 on every iteration" in cell
    assert "identical to 4 decimal places at 1, 2, 10 and 100 iterations" in cell
    assert "correlation 1.000" in cell
    assert "maximum deviation 3.3e-2 at max|x| = 0.807" in cell
    assert "not declared invalid" in cell


def test_claim_boundary_and_spec_gap_tamper_are_rejected() -> None:
    """Metadata нельзя пересказать: boundary и последний F18-gap должны быть exact."""
    mapped, arrays, tables = _build(_available_result())
    table = tables[F18_METADATA_TABLE_ID]
    for column_name in ("claim_boundary", "spec_gap_6"):
        row = list(table.rows[0])
        index = next(
            index for index, column in enumerate(table.columns) if column.name == column_name
        )
        row[index] = "paraphrased"
        changed = dict(tables)
        changed[F18_METADATA_TABLE_ID] = dataclasses.replace(table, rows=(tuple(row),))
        with pytest.raises(CharacterizationError, match="metadata"):
            decode_f18_result(mapped, arrays, changed)


def test_changed_dtype_shape_member_set_and_ref_order_are_rejected() -> None:
    """Persisted reference geometry и exact member set fail closed."""
    mapped, arrays, tables = _build(_available_result())
    changed = dict(arrays)
    changed[BICOHERENCE_NAME] = changed[BICOHERENCE_NAME].astype(np.float32)
    with pytest.raises(CharacterizationError, match="dtype"):
        decode_f18_result(mapped, changed, tables)

    changed = dict(arrays)
    changed[TRIAD_HIGH_NAME] = changed[TRIAD_HIGH_NAME][:-1]
    with pytest.raises(CharacterizationError, match="shape"):
        decode_f18_result(mapped, changed, tables)

    changed = dict(arrays)
    changed["f18_extra"] = np.zeros(1, dtype=np.uint8)
    with pytest.raises(CharacterizationError, match="members"):
        decode_f18_result(mapped, changed, tables)

    reversed_refs = dataclasses.replace(mapped, array_refs=tuple(reversed(mapped.array_refs)))
    with pytest.raises(CharacterizationError, match="references"):
        decode_f18_result(reversed_refs, arrays, tables)


def test_changed_mask_reference_and_frozen_axis_are_rejected() -> None:
    """Mask ref и low/high/sum axes нельзя менять независимо от engine result."""
    mapped, arrays, tables = _build(_available_result())
    references = list(mapped.array_refs)
    references[0] = dataclasses.replace(references[0], validity_mask_id=BIPHASE_MASK)
    broken = dataclasses.replace(mapped, array_refs=tuple(references))
    with pytest.raises(CharacterizationError, match="references"):
        decode_f18_result(broken, arrays, tables)

    changed = dict(arrays)
    axis = changed[TRIAD_LOW_NAME].copy()
    axis[0] += 1_000.0
    changed[TRIAD_LOW_NAME] = axis
    with pytest.raises(CharacterizationError, match="ax"):
        decode_f18_result(mapped, changed, tables)


def test_masked_out_measurement_must_be_exact_zero_filler() -> None:
    """Двусторонний invariant: masked-out value обязан быть ровно 0.0."""
    mapped, arrays, tables = _build(_available_result())
    changed = dict(arrays)
    values = changed[BIPHASE_NAME].copy()
    values[~_available_result().significant] = 0.25
    changed[BIPHASE_NAME] = values

    with pytest.raises(CharacterizationError, match="zero-under-mask"):
        decode_f18_result(mapped, changed, tables)


@pytest.mark.parametrize("array_id", _MEASUREMENT_IDS)
def test_global_finite_only_codec_rejects_nonfinite_measurements(array_id: str) -> None:
    """Mapper boundary не ослабляет общий finite-only NPZ codec."""
    mapped, arrays, tables = _build(_available_result())
    changed = dict(arrays)
    values = changed[array_id].copy()
    values[0] = np.nan
    changed[array_id] = values
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, changed, tables)

    with pytest.raises(CharacterizationError, match="array_finite"):
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )


def test_reason_vocabulary_order_duplicates_and_status_matrix_are_rejected() -> None:
    """Codes closed, sorted, unique; AVAILABLE без reasons, PARTIAL/unavailable с reasons."""
    available = _available_result()
    cases = (
        _without_validation(available, reason_codes=("invented",)),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(IAAFT_NOT_CONVERGED, IAAFT_NOT_CONVERGED),
        ),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(TRIAD_OFF_GRID, IAAFT_NOT_CONVERGED),
        ),
        _without_validation(available, reason_codes=(IAAFT_NOT_CONVERGED,)),
        _without_validation(available, status=Status.PARTIAL, reason_codes=()),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(PHASE_REFERENCE_UNAVAILABLE,),
        ),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(INSUFFICIENT_FRAMES,),
        ),
        _without_validation(
            available,
            status=Status.PARTIAL,
            reason_codes=(ARTIFACT_LIMIT,),
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)
    assert len(DECLARED_CODES) == len(set(DECLARED_CODES)) == 8


def test_cap_is_count_only_and_cannot_hide_unreported_dropped_content() -> None:
    """Locked base set has no cap overflow; fabricated dropped count cannot round-trip."""
    broken = _without_validation(
        _available_result(),
        status=Status.PARTIAL,
        reason_codes=(ARTIFACT_LIMIT,),
        dropped_triad_count=1,
    )

    with pytest.raises(CharacterizationError, match=r"axis|count-cap"):
        _build(broken)


def test_engine_mask_invariant_and_axis_dtype_are_checked_before_persistence() -> None:
    """Encode boundary отвергает mask mismatch и wrong dtype без reshape или cast."""
    result = _available_result()
    cases = (
        _without_validation(
            result,
            triad_available=np.ones(14, dtype=np.bool_),
        ),
        _without_validation(
            result,
            triad_low_hz=result.triad_low_hz.astype(np.float32),
        ),
        _without_validation(
            result,
            triad_sum_hz=result.triad_sum_hz + 1.0,
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_persisted_summary_and_support_accounting_must_match() -> None:
    """Counters, n, support и canonical summary order должны восстанавливаться точно."""
    mapped, arrays, tables = _build(_available_result())
    summaries = tuple(
        dataclasses.replace(item, value=item.value + 1.0)
        if item.name == "f18_frame_count"
        else item
        for item in mapped.comparison_summary
    )
    broken = dataclasses.replace(mapped, comparison_summary=summaries)

    with pytest.raises(CharacterizationError, match=r"summary|accounting|framed support"):
        decode_f18_result(broken, arrays, tables)


def test_wrong_recipe_slot_method_version_or_declaration_is_rejected() -> None:
    """Mapper принимает только frozen slot 17 и exact recipe surface."""
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available_result(), family=_recipe().families[F18_INDEX - 1])
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available_result(), family=dataclasses.replace(_family(), method_version=2))
    parameters = tuple(
        ("surrogate_seed", SURROGATE_SEED + 1) if name == "surrogate_seed" else (name, value)
        for name, value in _family().parameters
    )
    with pytest.raises(CharacterizationError, match="declarations"):
        _build(_available_result(), family=dataclasses.replace(_family(), parameters=parameters))


def test_nonpositive_record_duration_is_rejected() -> None:
    """Record span остаётся positive finite boundary для built и unavailable."""
    for duration in (0.0, -1.0, float("inf"), float("nan")):
        with pytest.raises(CharacterizationError, match="duration"):
            _build(
                _unavailable(TRIAD_OFF_GRID, _OFF_GRID_SAMPLE_RATE_HZ), record_duration_s=duration
            )


def test_decoder_rejects_unavailable_and_revalidates_engine_result() -> None:
    """UNAVAILABLE не имеет decodable domain; built result проходит engine validator."""
    mapped, arrays, tables = _build(_unavailable(TRIAD_OFF_GRID, _OFF_GRID_SAMPLE_RATE_HZ))
    with pytest.raises(CharacterizationError, match="no decodable domain"):
        decode_f18_result(mapped, arrays, tables)

    restored, _, _ = _round_trip(_available_result())
    assert restored.status is Status.AVAILABLE
    assert restored.declared_triad_count == 15
    assert restored.iaaft_converged_count == IAAFT_SURROGATE_COUNT
