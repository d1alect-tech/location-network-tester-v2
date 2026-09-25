"""Persistence mapper F17: off-grid UNAVAILABLE, masked absence и claim boundary."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Final

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization import (
    FAMILY_IDS,
    CharacterizationBundle,
    CharacterizationError,
    Status,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f16_bundle import F16_INDEX
from lnt.characterization.f17_arrays import CELL_AVAILABLE_ID
from lnt.characterization.f17_bundle import (
    COHERENCE_TABLE_ID,
    F17_ID,
    F17_INDEX,
    build_f17_family,
    decode_f17_result,
)
from lnt.characterization.f17_contract import (
    ARTIFACT_LIMIT,
    BH_P_VALUE_NAME,
    CHANNEL_PRODUCT_CONVENTION,
    CLAIM_BOUNDARY,
    COHERENCE_NAME,
    CYCLE_CONCATENATION_CONVENTION,
    CYCLIC_FREQUENCIES_HZ,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_FREQUENCY_OFF_GRID,
    CYCLIC_SPECTRUM_NAME,
    DECLARED_CODES,
    FALSE_DISCOVERY_RATE,
    FREQUENCY_MAPPING,
    FREQUENCY_NAME,
    INSUFFICIENT_FRAMES,
    MAXIMUM_STORED_CELLS,
    METHOD,
    NO_SIGNIFICANT_CELL,
    NULL_PERMUTATION_CONVENTION,
    PHASE_REFERENCE_UNAVAILABLE,
    RAW_P_VALUE_NAME,
    SEGMENT_SUPPORT_NAME,
    SPEC_GAPS,
    ZERO_DENOMINATOR,
    F17Declarations,
)
from lnt.characterization.f17_engine import compute_f17_cyclic_spectral_coherence
from lnt.characterization.f17_frequency import build_frequency_grid
from lnt.characterization.f17_result import F17Result, unavailable_f17
from lnt.characterization.f17_tables import coherence_metadata
from lnt.characterization.f17_validation import validate_f17_result
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Band, validate_unit_name
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RECORD_S: Final = 2.4
_FREQUENCIES: Final = np.asarray([3_000.0, 3_100.0, 3_200.0, 3_300.0, 3_400.0, 3_500.0])
_GRID: Final = (len(CYCLIC_FREQUENCIES_HZ), _FREQUENCIES.size)
_FRAMES: Final = 39
_CYCLES: Final = 40
_QUALIFIED: Final = 81_920
_ALPHA_COUNT: Final = len(CYCLIC_FREQUENCIES_HZ)
_EXACT_GRID_HZ: Final = 102_400.0
_CYCLE_SAMPLES: Final = 2_048
_CANONICAL_HZ: Final = 500_000.0
_MEASURED_IDS: Final = (
    CYCLIC_SPECTRUM_NAME,
    COHERENCE_NAME,
    RAW_P_VALUE_NAME,
    BH_P_VALUE_NAME,
)
_ARRAY_IDS: Final = (
    FREQUENCY_NAME,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_SPECTRUM_NAME,
    COHERENCE_NAME,
    RAW_P_VALUE_NAME,
    BH_P_VALUE_NAME,
    SEGMENT_SUPPORT_NAME,
    "f17_significant",
    "f17_stored_alpha_hz",
    "f17_stored_frequency_hz",
    "f17_stored_cyclic_spectrum_v2",
    "f17_stored_coherence",
    "f17_stored_raw_p_value",
    "f17_stored_bh_p_value",
    "f17_stored_segment_support",
)
_SUMMARIES: Final = (
    "f17_sample_count",
    "f17_qualified_sample_count",
    "f17_qualified_cycle_count",
    "f17_frame_count",
    "f17_tested_cell_count",
    "f17_significant_cell_count",
    "f17_stored_cell_count",
    "f17_omitted_cell_count",
)
_ARRAY_FIELDS: Final = (
    "cyclic_frequencies_hz",
    "frequencies_hz",
    "cyclic_spectrum",
    "coherence",
    "raw_p_value",
    "bh_p_value",
    "segment_support",
    "cell_available",
    "significant",
    "stored_alpha_hz",
    "stored_frequency_hz",
    "stored_cyclic_spectrum",
    "stored_coherence",
    "stored_raw_p_value",
    "stored_bh_p_value",
    "stored_segment_support",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F17_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _build(
    result: F17Result,
    *,
    family: CharacterizationFamily | None = None,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f17_family(
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
        mapped if index == F17_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), dict(arrays), dict(tables)


def _load(
    mapped: FamilyResult,
    arrays: dict[str, np.ndarray],
    tables: dict[str, TableBlock],
) -> F17Result:
    bundle, bundle_arrays, bundle_tables = _full_bundle(mapped, arrays, tables)
    loaded = load_bundle(
        encode_bundle(
            bundle,
            bundle_arrays,
            bundle_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )
    )
    assert loaded.bundle.families[F17_INDEX] == mapped
    return decode_f17_result(loaded.bundle.families[F17_INDEX], loaded.arrays, loaded.tables)


def _without_validation(result: F17Result, **fields: object) -> F17Result:
    """Обойти только dataclass-валидацию для проверки mapper-шов."""
    broken = object.__new__(F17Result)
    for field in dataclasses.fields(F17Result):
        object.__setattr__(broken, field.name, getattr(result, field.name))
    for name, value in fields.items():
        object.__setattr__(broken, name, value)
    return broken


def _assert_result_equal(actual: F17Result, expected: F17Result) -> None:
    for name in _ARRAY_FIELDS:
        left = getattr(actual, name)
        right = getattr(expected, name)
        assert left.dtype == right.dtype, name
        assert left.shape == right.shape, name
        np.testing.assert_array_equal(left, right, err_msg=name)
    for name in _SUMMARIES:
        assert getattr(actual, name.removeprefix("f17_")) == getattr(
            expected, name.removeprefix("f17_")
        ), name
    assert actual.status is expected.status
    assert actual.reason_codes == expected.reason_codes


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=8_192,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=199,
        deterministic_seed=6_022,
    )


def _phase(sample_count: int, sample_rate_hz: float, cycle_samples: int) -> PhaseCycles:
    starts = np.arange(0, sample_count, cycle_samples, dtype=np.float64)
    return PhaseCycles(
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        cycle_start_samples=starts,
        cycle_end_samples=starts + cycle_samples,
        cycle_valid=np.ones(starts.size, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _means() -> PhaseMeans:
    return PhaseMeans(
        means_v=np.zeros(64, dtype=np.float64),
        counts=np.full(64, 1_000, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _engine_result(sample_rate_hz: float, cycle_samples: int, coherent: bool) -> F17Result:
    """Прогнать настоящий движок на declared rate и declared segment length."""
    count = _CYCLES * cycle_samples
    local = np.arange(cycle_samples, dtype=np.float64)
    first = np.empty(count, dtype=np.float64)
    second = np.empty(count, dtype=np.float64)
    for cycle in range(_CYCLES):
        start = cycle * cycle_samples
        time = (start + local) / sample_rate_hz
        drift = 0.071 * cycle
        first[start : start + cycle_samples] = np.cos(
            2.0 * np.pi * 10_000.0 * time + drift
        ) + 0.8 * np.cos(2.0 * np.pi * 10_050.0 * time + drift)
        if coherent:
            second[start : start + cycle_samples] = first[start : start + cycle_samples]
        else:
            other = 0.37 * np.sin(0.9 * cycle)
            second[start : start + cycle_samples] = np.cos(
                2.0 * np.pi * 10_000.0 * time + other
            ) + 0.8 * np.cos(2.0 * np.pi * 10_050.0 * time - other)
    return compute_f17_cyclic_spectral_coherence(
        ch1_samples=first,
        ch2_samples=second,
        phase=_phase(count, sample_rate_hz, cycle_samples),
        ch1_means=_means(),
        ch2_means=_means(),
        declarations=F17Declarations.locked(),
        resources=_resources(),
    )


def _stored_prefix(
    significance: np.ndarray,
    spectra: np.ndarray,
    coherence: np.ndarray,
    raw_p: np.ndarray,
    adjusted: np.ndarray,
    support: np.ndarray,
) -> dict[str, np.ndarray]:
    """Собрать compact stored rows через явные grid-координаты, не через select_stored_cells."""
    flat = np.flatnonzero(significance.ravel())
    width = _FREQUENCIES.size
    return {
        "stored_alpha_hz": np.asarray(CYCLIC_FREQUENCIES_HZ, dtype=np.float64)[flat // width],
        "stored_frequency_hz": _FREQUENCIES[flat % width],
        "stored_cyclic_spectrum": spectra.ravel()[flat],
        "stored_coherence": coherence.ravel()[flat],
        "stored_raw_p_value": raw_p.ravel()[flat],
        "stored_bh_p_value": adjusted.ravel()[flat],
        "stored_segment_support": support.ravel()[flat],
    }


def _built_result(
    *,
    cell_available: np.ndarray,
    coherence: np.ndarray,
    raw_p: np.ndarray,
    adjusted: np.ndarray,
    status: Status,
    reason_codes: tuple[str, ...],
) -> F17Result:
    """Собрать валидный построенный F17Result из явной сетки и явной маски."""
    support = np.where(cell_available, _FRAMES, 0).astype(np.int64)
    spectra = np.where(
        cell_available,
        1.0e-9 * (1.0 + np.arange(_GRID[0] * _GRID[1]).reshape(_GRID) * 1j),
        np.nan + 1j * np.nan,
    ).astype(np.complex128)
    significant = cell_available & (adjusted <= FALSE_DISCOVERY_RATE)
    stored = _stored_prefix(significant, spectra, coherence, raw_p, adjusted, support)
    significant_count = int(np.count_nonzero(significant))
    return F17Result(
        status=status,
        reason_codes=reason_codes,
        cyclic_frequencies_hz=np.asarray(CYCLIC_FREQUENCIES_HZ, dtype=np.float64),
        frequencies_hz=_FREQUENCIES.copy(),
        cyclic_spectrum=spectra,
        coherence=coherence,
        raw_p_value=raw_p,
        bh_p_value=adjusted,
        segment_support=support,
        cell_available=cell_available,
        significant=significant,
        stored_alpha_hz=stored["stored_alpha_hz"],
        stored_frequency_hz=stored["stored_frequency_hz"],
        stored_cyclic_spectrum=stored["stored_cyclic_spectrum"],
        stored_coherence=stored["stored_coherence"],
        stored_raw_p_value=stored["stored_raw_p_value"],
        stored_bh_p_value=stored["stored_bh_p_value"],
        stored_segment_support=stored["stored_segment_support"],
        sample_count=_QUALIFIED,
        qualified_sample_count=_QUALIFIED,
        qualified_cycle_count=_CYCLES,
        frame_count=_FRAMES,
        tested_cell_count=int(np.count_nonzero(cell_available)),
        significant_cell_count=significant_count,
        stored_cell_count=int(stored["stored_coherence"].size),
        omitted_cell_count=0,
    )


def _available_result() -> F17Result:
    """AVAILABLE: пять BH-значимых ячеек, разбросанных по всем четырём alpha."""
    adjusted = np.full(_GRID, 0.4, dtype=np.float64)
    for flat_index, value in ((2, 0.01), (5, 0.02), (6, 0.03), (15, 0.04), (19, 0.049)):
        adjusted[flat_index // _FREQUENCIES.size, flat_index % _FREQUENCIES.size] = value
    return _built_result(
        cell_available=np.ones(_GRID, dtype=np.bool_),
        coherence=np.full(_GRID, 0.5, dtype=np.float64),
        raw_p=np.full(_GRID, 0.005, dtype=np.float64),
        adjusted=adjusted,
        status=Status.AVAILABLE,
        reason_codes=(),
    )


def _partial_result() -> F17Result:
    """PARTIAL: две структурно отсутствующие ячейки и ни одного открытия."""
    available = np.ones(_GRID, dtype=np.bool_)
    available[0, 0] = False
    available[3, 5] = False
    coherence = np.full(_GRID, 0.25, dtype=np.float64)
    coherence[~available] = np.nan
    raw_p = np.full(_GRID, 0.2, dtype=np.float64)
    raw_p[~available] = np.nan
    adjusted = np.full(_GRID, 0.3, dtype=np.float64)
    adjusted[~available] = np.nan
    return _built_result(
        cell_available=available,
        coherence=coherence,
        raw_p=raw_p,
        adjusted=adjusted,
        status=Status.PARTIAL,
        reason_codes=(NO_SIGNIFICANT_CELL, ZERO_DENOMINATOR),
    )


def test_canonical_500khz_record_is_unavailable_off_grid_with_empty_domains() -> None:
    """Канонические 500 кГц: declared alpha вне сетки FFT, поэтому F17 недоступна."""
    result = _engine_result(_CANONICAL_HZ, 10_000, coherent=True)

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

    grid = build_frequency_grid(F17Declarations.locked(), _CANONICAL_HZ)
    assert grid.alpha_offsets.tolist() == [-1, -1, -1, -1]
    assert not np.any(grid.alpha_on_grid)
    assert "122.0703" in SPEC_GAPS[0]
    # Условие точности — шаг делит альфа/2, поэтому offsets равны alpha/(2*step).
    assert "0.2048/0.4096/0.6144/0.8192" in SPEC_GAPS[0]
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (CYCLIC_FREQUENCY_OFF_GRID,)
    assert result.sample_count == _CYCLES * 10_000
    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (CYCLIC_FREQUENCY_OFF_GRID,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert mapped.n == 0
    assert arrays == {}
    assert tables == {}
    assert loaded.bundle.families[F17_INDEX] == mapped
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}


def test_exact_grid_engine_result_round_trips_with_declared_cell_cap() -> None:
    """102.4 кГц: точная сетка, 4096 сохранённых ячеек и явный artifact_limit."""
    result = _engine_result(_EXACT_GRID_HZ, _CYCLE_SAMPLES, coherent=True)

    mapped, arrays, tables = _build(result)
    restored = _load(mapped, arrays, tables)

    validate_f17_result(restored)
    assert result.status is Status.PARTIAL
    assert result.reason_codes == (ARTIFACT_LIMIT,)
    assert result.stored_cell_count == MAXIMUM_STORED_CELLS
    assert result.omitted_cell_count == result.significant_cell_count - MAXIMUM_STORED_CELLS
    assert result.omitted_cell_count > 0
    assert result.cell_available.all()
    assert result.coherence.shape == (4, 1_724)
    assert tuple(reference.array_id for reference in mapped.array_refs) == _ARRAY_IDS
    assert set(tables) == {COHERENCE_TABLE_ID}
    assert np.all(np.isfinite(arrays[CYCLIC_SPECTRUM_NAME]))
    _assert_result_equal(restored, result)


def test_exact_grid_without_discovery_is_partial_and_publishes_empty_stored_domain() -> None:
    """Независимые каналы при точной сетке дают no_significant_cell, а не нули."""
    result = _engine_result(_EXACT_GRID_HZ, _CYCLE_SAMPLES, coherent=False)

    mapped, arrays, _tables = _build(result)
    restored = _load(mapped, arrays, _tables)

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (NO_SIGNIFICANT_CELL,)
    assert not np.any(result.significant)
    assert arrays["f17_stored_coherence"].size == 0
    assert arrays["f17_stored_segment_support"].size == 0
    assert mapped.support.observation_count == result.qualified_sample_count
    _assert_result_equal(restored, result)


def test_available_round_trip_restores_every_field_dtype_and_orientation() -> None:
    """AVAILABLE сохраняет все поля, dtypes и ориентацию alpha x frequency."""
    result = _available_result()

    mapped, arrays, tables = _build(result)
    restored = _load(mapped, arrays, tables)

    assert mapped.status is Status.AVAILABLE
    assert mapped.reason_codes == ()
    assert arrays[CYCLIC_SPECTRUM_NAME].shape == _GRID
    assert arrays[CYCLIC_SPECTRUM_NAME].dtype == np.dtype(np.complex128)
    assert arrays[COHERENCE_NAME].dtype == np.dtype(np.float64)
    assert arrays[SEGMENT_SUPPORT_NAME].dtype == np.dtype(np.int64)
    assert arrays["f17_significant"].dtype == np.dtype(np.uint8)
    assert arrays[CELL_AVAILABLE_ID].dtype == np.dtype(np.uint8)
    assert arrays[CELL_AVAILABLE_ID].tolist() == [[1] * 6] * 4
    for reference in mapped.array_refs:
        assert validate_unit_name(reference.array_id, reference.unit) is None
    _assert_result_equal(restored, result)


def test_persisted_cell_identity_is_grid_coordinate_not_compact_row() -> None:
    """Stored rows хранят grid-координаты (alpha, f), а не номера строк сетки."""
    result = _available_result()
    flat = np.flatnonzero(result.significant.ravel())

    mapped, arrays, _tables = _build(result)
    restored = _load(mapped, arrays, _tables)

    assert flat.tolist() == [2, 5, 6, 15, 19]
    assert arrays["f17_stored_alpha_hz"].tolist() == [50.0, 50.0, 100.0, 150.0, 200.0]
    assert arrays["f17_stored_frequency_hz"].tolist() == [
        3_200.0,
        3_500.0,
        3_000.0,
        3_300.0,
        3_100.0,
    ]
    # Координаты выведены из grid-индексов независимо от движка, а не из номера строки.
    assert arrays["f17_stored_alpha_hz"].tolist() == [
        CYCLIC_FREQUENCIES_HZ[index // _FREQUENCIES.size] for index in flat
    ]
    assert arrays["f17_stored_frequency_hz"].tolist() == [
        float(_FREQUENCIES[index % _FREQUENCIES.size]) for index in flat
    ]
    np.testing.assert_array_equal(arrays["f17_stored_coherence"], result.coherence.ravel()[flat])
    assert arrays["f17_stored_alpha_hz"].tolist() != sorted(flat)
    assert np.array_equal(
        arrays["f17_stored_segment_support"],
        np.full(flat.size, _FRAMES, dtype=np.int64),
    )
    assert restored.stored_alpha_hz.tolist() == arrays["f17_stored_alpha_hz"].tolist()
    assert restored.stored_frequency_hz.tolist() == arrays["f17_stored_frequency_hz"].tolist()
    assert mapped.array_refs[8].shape == (5,)


def test_masked_absence_persists_as_finite_fill_plus_validity_mask() -> None:
    """NaN движка публикуется как 0.0 под явной uint8-маской, absence несёт mask."""
    result = _partial_result()

    mapped, arrays, tables = _build(result)
    restored = _load(mapped, arrays, tables)

    assert result.status is Status.PARTIAL
    assert mapped.status is Status.PARTIAL
    assert mapped.reason_codes == (NO_SIGNIFICANT_CELL, ZERO_DENOMINATOR)
    assert arrays[CELL_AVAILABLE_ID][0, 0] == 0
    assert arrays[CELL_AVAILABLE_ID][3, 5] == 0
    for array_id in _MEASURED_IDS:
        assert np.all(np.isfinite(arrays[array_id])), array_id
        assert arrays[array_id][0, 0] == 0.0, array_id
        assert arrays[array_id][3, 5] == 0.0, array_id
    assert np.all(arrays[SEGMENT_SUPPORT_NAME][~result.cell_available] == 0)
    assert np.all(arrays["f17_significant"] == 0)
    assert all(np.all(np.isfinite(value)) for value in arrays.values())
    assert np.isnan(restored.coherence[0, 0])
    assert np.isnan(restored.bh_p_value[3, 5])
    assert np.isnan(restored.cyclic_spectrum[0, 0])
    assert restored.segment_support[0, 0] == 0
    _assert_result_equal(restored, result)


def test_structural_absence_does_not_degrade_family_status() -> None:
    """Маскированные ячейки не превращают частично измеренную сетку в недоступную."""
    result = _partial_result()

    mapped, arrays, _tables = _build(result)

    assert mapped.status is Status.PARTIAL
    assert mapped.qc.passed is False
    assert mapped.reason_codes != (ZERO_DENOMINATOR,)
    assert int(np.count_nonzero(arrays[CELL_AVAILABLE_ID])) == _GRID[0] * _GRID[1] - 2
    assert np.any(arrays[COHERENCE_NAME][arrays[CELL_AVAILABLE_ID].astype(bool)] > 0.0)
    assert not np.any(mapped.array_refs[3].validity_mask_id is None)


def test_zero_tested_cells_is_rejected_by_bundle_but_accepted_by_engine() -> None:
    """Bundle строже движка: построенная сетка обязана что-то протестировать."""
    result = _available_result()
    empty = np.zeros(_GRID, dtype=np.bool_)
    zeroed = _without_validation(
        result,
        status=Status.PARTIAL,
        reason_codes=(NO_SIGNIFICANT_CELL,),
        cyclic_spectrum=np.full(_GRID, np.nan + 1j * np.nan, dtype=np.complex128),
        coherence=np.full(_GRID, np.nan, dtype=np.float64),
        raw_p_value=np.full(_GRID, np.nan, dtype=np.float64),
        bh_p_value=np.full(_GRID, np.nan, dtype=np.float64),
        segment_support=np.zeros(_GRID, dtype=np.int64),
        cell_available=empty,
        significant=empty,
        stored_alpha_hz=np.empty(0, dtype=np.float64),
        stored_frequency_hz=np.empty(0, dtype=np.float64),
        stored_cyclic_spectrum=np.empty(0, dtype=np.complex128),
        stored_coherence=np.empty(0, dtype=np.float64),
        stored_raw_p_value=np.empty(0, dtype=np.float64),
        stored_bh_p_value=np.empty(0, dtype=np.float64),
        stored_segment_support=np.empty(0, dtype=np.int64),
        tested_cell_count=0,
        significant_cell_count=0,
        stored_cell_count=0,
    )
    validate_f17_result(zeroed)

    with pytest.raises(CharacterizationError, match="tested F17 cell"):
        _build(zeroed)


def test_frame_count_above_qualified_samples_is_rejected() -> None:
    """Frame count не может превышать compact record: это выдуманная опора."""
    result = _available_result()
    inflated = _QUALIFIED + 1
    broken = _without_validation(
        result,
        frame_count=inflated,
        segment_support=np.full(_GRID, inflated, dtype=np.int64),
        stored_segment_support=np.full(5, inflated, dtype=np.int64),
    )
    validate_f17_result(broken)

    with pytest.raises(CharacterizationError, match="frame support"):
        _build(broken)


def test_persisted_measurement_rejects_finite_value_outside_mask() -> None:
    """Masked-out ячейка обязана быть ровно declared fill 0.0."""
    mapped, arrays, tables = _build(_partial_result())
    changed = dict(arrays)
    values = changed[COHERENCE_NAME].copy()
    values[0, 0] = 0.25
    changed[COHERENCE_NAME] = values

    with pytest.raises(CharacterizationError, match="zero-under-mask"):
        decode_f17_result(mapped, changed, tables)


@pytest.mark.parametrize("array_id", _MEASURED_IDS)
def test_nonfinite_persisted_measurement_is_rejected_by_codec(array_id: str) -> None:
    """Ни один persisted F17 measurement array не принимает NaN."""
    mapped, arrays, tables = _build(_partial_result())
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
    """Mapper принимает только frozen F17 slot 16 и exact recipe surface."""
    result = _available_result()
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=_recipe().families[F16_INDEX])
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=dataclasses.replace(_family(), method="wrong_method"))
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(result, family=dataclasses.replace(_family(), method_version=2))
    parameters = tuple(
        ("segment_samples", 4_095) if name == "segment_samples" else (name, value)
        for name, value in _family().parameters
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result, family=dataclasses.replace(_family(), parameters=parameters))


def test_misaligned_engine_arrays_are_rejected_without_reshape() -> None:
    """Locked geometry проверяется до persistence; транспонирование запрещено."""
    result = _available_result()
    cases = (
        _without_validation(result, coherence=np.zeros((_GRID[1], _GRID[0]), dtype=np.float64)),
        _without_validation(result, frequencies_hz=_FREQUENCIES[:-1].copy()),
        _without_validation(result, cyclic_frequencies_hz=np.asarray([50.0, 100.0, 150.0, 250.0])),
        _without_validation(result, stored_coherence=np.zeros(4, dtype=np.float64)),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_persisted_dtype_shape_and_reference_order_are_canonical() -> None:
    """Изменённые dtype, shape или порядок ссылок не проходят decode."""
    mapped, arrays, tables = _build(_available_result())
    downcast = dict(arrays)
    downcast[COHERENCE_NAME] = arrays[COHERENCE_NAME].astype(np.float32)
    with pytest.raises(CharacterizationError, match="dtype or shape"):
        decode_f17_result(mapped, downcast, tables)

    reshaped = dict(arrays)
    reshaped[COHERENCE_NAME] = arrays[COHERENCE_NAME].reshape(-1)
    with pytest.raises(CharacterizationError, match="dtype or shape"):
        decode_f17_result(mapped, reshaped, tables)

    reversed_refs = dataclasses.replace(mapped, array_refs=tuple(reversed(mapped.array_refs)))
    with pytest.raises(CharacterizationError, match="canonical"):
        decode_f17_result(reversed_refs, arrays, tables)


def test_persisted_mask_reference_and_mask_shape_are_canonical() -> None:
    """Mask ref и mask shape нельзя переставить или сузить."""
    mapped, arrays, tables = _build(_available_result())
    narrowed = dict(arrays)
    narrowed[CELL_AVAILABLE_ID] = np.ones((_GRID[0], _GRID[1] - 1), dtype=np.uint8)
    with pytest.raises(CharacterizationError, match="dtype or shape"):
        decode_f17_result(mapped, narrowed, tables)

    dropped = {key: value for key, value in arrays.items() if key != CELL_AVAILABLE_ID}
    with pytest.raises(CharacterizationError, match="is missing"):
        decode_f17_result(mapped, dropped, tables)

    swapped = tuple(
        dataclasses.replace(reference, validity_mask_id=None)
        if reference.array_id == COHERENCE_NAME
        else reference
        for reference in mapped.array_refs
    )
    with pytest.raises(CharacterizationError, match="validity reference"):
        decode_f17_result(dataclasses.replace(mapped, array_refs=swapped), arrays, tables)


def test_partial_structural_mask_must_stay_fully_valid() -> None:
    """Синтезированная all-ones маска оси не может таить частичное отсутствие."""
    mapped, arrays, tables = _build(_partial_result())
    axis_mask = f"{FREQUENCY_NAME}_valid"
    assert axis_mask in arrays
    changed = dict(arrays)
    values = changed[axis_mask].copy()
    values[0] = 0
    changed[axis_mask] = values

    with pytest.raises(CharacterizationError, match="fully valid"):
        decode_f17_result(mapped, changed, tables)


def test_frozen_alpha_axis_tamper_is_rejected_by_engine_invariant() -> None:
    """Декодер заново запускает validate_f17_result и отвергает сдвинутую alpha-ось."""
    mapped, arrays, tables = _build(_available_result())
    changed = dict(arrays)
    changed[CYCLIC_FREQUENCY_NAME] = np.asarray([50.0, 100.0, 150.0, 250.0], dtype=np.float64)

    with pytest.raises(CharacterizationError, match="locked method"):
        decode_f17_result(mapped, changed, tables)


def test_claim_metadata_tamper_is_rejected() -> None:
    """Claim boundary и conventions нельзя пересказать в persisted table."""
    mapped, arrays, tables = _build(_available_result())
    table = tables[COHERENCE_TABLE_ID]
    row = list(table.rows[0])
    row[-1] = "population causation established"
    changed = dict(tables)
    changed[COHERENCE_TABLE_ID] = dataclasses.replace(table, rows=(tuple(row),))

    with pytest.raises(CharacterizationError, match="metadata"):
        decode_f17_result(mapped, arrays, changed)

    with pytest.raises(CharacterizationError, match="metadata"):
        decode_f17_result(mapped, arrays, {})


def test_metadata_table_carries_conventions_identity_quantity_names_and_spec_gap() -> None:
    """Метаданные несут conventions, identity, quantity names и зафиксированный пробел."""
    _mapped, arrays, tables = _build(_partial_result())
    table = tables[COHERENCE_TABLE_ID]

    assert table.table_id == COHERENCE_TABLE_ID
    assert table.row_count == 1
    assert table.stored_count == 1
    assert table.selection_rule == "all"
    assert len(table.columns) == 39
    metadata = dict(zip((column.name for column in table.columns), table.rows[0], strict=True))
    assert metadata["family_id"] == F17_ID
    assert FAMILY_IDS[F17_INDEX] == F17_ID
    assert metadata["family_index"] == F17_INDEX == 16
    assert metadata["method"] == METHOD
    assert metadata["method_version"] == 1
    assert metadata["cycle_concatenation_convention"] == CYCLE_CONCATENATION_CONVENTION
    assert metadata["null_permutation_convention"] == NULL_PERMUTATION_CONVENTION
    assert metadata["channel_product_convention"] == CHANNEL_PRODUCT_CONVENTION
    assert metadata["frequency_mapping"] == FREQUENCY_MAPPING
    assert metadata["claim_boundary"] == CLAIM_BOUNDARY
    assert metadata["spec_gap_f17_1"] == SPEC_GAPS[0]
    assert metadata["frequency_quantity_name"] == FREQUENCY_NAME
    assert metadata["cyclic_frequency_quantity_name"] == CYCLIC_FREQUENCY_NAME
    assert metadata["cyclic_spectrum_quantity_name"] == CYCLIC_SPECTRUM_NAME
    assert metadata["segment_support_quantity_name"] == SEGMENT_SUPPORT_NAME
    assert metadata["stored_cyclic_spectrum_quantity_name"] == ("f17_stored_cyclic_spectrum_v2")
    assert table == coherence_metadata(F17Declarations.locked())
    assert set(tables) == {COHERENCE_TABLE_ID}
    assert len(arrays) > len(_ARRAY_IDS)


def test_unavailable_publishes_no_domains_and_round_trips_codec() -> None:
    """UNAVAILABLE не публикует axes, arrays, tables или summaries."""
    result = unavailable_f17((INSUFFICIENT_FRAMES,), _QUALIFIED)
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

    assert mapped.status is Status.UNAVAILABLE
    assert mapped.reason_codes == (INSUFFICIENT_FRAMES,)
    assert mapped.array_refs == ()
    assert mapped.table_refs == ()
    assert mapped.comparison_summary == ()
    assert mapped.support.sample_count == 0
    assert arrays == {}
    assert tables == {}
    assert dict(loaded.arrays) == {}
    assert dict(loaded.tables) == {}


def test_unavailable_rejects_partial_only_reason_codes() -> None:
    """Bundle строже движка: UNAVAILABLE не несёт код, объявленный только для PARTIAL."""
    result = unavailable_f17((NO_SIGNIFICANT_CELL,), _QUALIFIED)
    validate_f17_result(result)

    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result)


def test_reason_vocabulary_order_duplicates_and_status_matrix_are_rejected() -> None:
    """Codes closed, sorted, unique; status matrix и terminal reasons строги."""
    available = _available_result()
    partial = _partial_result()
    cases = (
        _without_validation(available, status=Status.PARTIAL, reason_codes=()),
        _without_validation(available, reason_codes=(ARTIFACT_LIMIT,)),
        _without_validation(available, status=Status.PARTIAL, reason_codes=("not_computed",)),
        _without_validation(
            partial, reason_codes=(ZERO_DENOMINATOR, NO_SIGNIFICANT_CELL, ZERO_DENOMINATOR)
        ),
        _without_validation(
            partial,
            status=Status.PARTIAL,
            reason_codes=(NO_SIGNIFICANT_CELL, PHASE_REFERENCE_UNAVAILABLE),
        ),
        _without_validation(
            partial, status=Status.UNAVAILABLE, reason_codes=(NO_SIGNIFICANT_CELL,)
        ),
    )
    for broken in cases:
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)
    assert {ARTIFACT_LIMIT, NO_SIGNIFICANT_CELL, ZERO_DENOMINATOR} <= set(DECLARED_CODES)


def test_persisted_summary_accounting_must_match_support() -> None:
    """Persisted qualified count не может расходиться с FamilyResult support."""
    mapped, arrays, tables = _build(_partial_result())
    summaries = tuple(
        dataclasses.replace(item, value=item.value + 1.0)
        if item.name == "f17_qualified_sample_count"
        else item
        for item in mapped.comparison_summary
    )
    broken = dataclasses.replace(mapped, comparison_summary=summaries)

    with pytest.raises(CharacterizationError, match="accounting"):
        decode_f17_result(broken, arrays, tables)


def test_record_duration_must_be_positive_and_finite() -> None:
    """Нулевая длительность записи не публикуется как измеренная опора."""
    with pytest.raises(CharacterizationError, match="duration"):
        build_f17_family(_available_result(), _family(), _band(), record_duration_s=0.0)
    with pytest.raises(CharacterizationError, match="duration"):
        build_f17_family(_available_result(), _family(), _band(), record_duration_s=float("nan"))
