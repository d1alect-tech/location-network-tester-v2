"""Persistence tests for F11 conditional distributions.

Fixtures build F11Result values by hand. Assertions therefore describe persisted
behavior, not equality with a second mapper implementation.
"""

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
    TableReference,
    Unit,
    encode_bundle,
    load_bundle,
)
from lnt.characterization.f11_bundle import F11_ID, F11_INDEX, build_f11_family
from lnt.characterization.f11_result import (
    BIN_EMPTY,
    CDF_PROBABILITIES,
    DECLARED_CODES,
    EVENT_LIMIT,
    INSUFFICIENT_SUPPORT,
    MAXIMUM_EVENTS,
    PERSISTED_QUANTITY_NAMES,
    QUANTILES,
    QUANTITIES,
    F11Cell,
    F11QuantityResult,
    F11Result,
)
from lnt.characterization.family_envelope import not_computed_family
from lnt.characterization.records import Band
from lnt.context.json_codec import decode_object

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RECORD_S = 2.4
_PHASE_BINS = 16
_BANDS = ((3000.0, 10000.0), (10000.0, 50000.0), (50000.0, 200000.0))
_LABELS = ("mode_0", "mode_1", "mode_2", "mode_3")
_CELL_SHAPE = (_PHASE_BINS, len(_BANDS), len(_LABELS))
_CELL_COUNT = _PHASE_BINS * len(_BANDS) * len(_LABELS)
_CDF_SHAPE = (_CELL_COUNT, CDF_PROBABILITIES.size)
_QUANTILE_SHAPE = (_CELL_COUNT, len(QUANTILES))
_TABLE_ID = "f11_cells"
_ARRAY_IDS = (
    "f11_phase_bin",
    "f11_phase_bin_edges_rad",
    "f11_band_index",
    "f11_band_low_hz",
    "f11_band_high_hz",
    "f11_mode_index",
    "f11_quantile_level",
    "f11_cdf_probability",
    "f11_cell_support_count",
    "f11_cell_positive_count",
    "f11_cell_negative_count",
    *PERSISTED_QUANTITY_NAMES,
    "f11_cdf_absolute_peak_v",
    "f11_cdf_duration_s",
    "f11_cdf_dominant_frequency_hz",
    "f11_cdf_v2_s",
    "f11_cdf_grid_absolute_peak_v",
    "f11_cdf_grid_duration_s",
    "f11_cdf_grid_dominant_frequency_hz",
    "f11_cdf_grid_v2_s",
)
_QUANTILE_IDS = PERSISTED_QUANTITY_NAMES
_CDF_IDS = (
    "f11_cdf_absolute_peak_v",
    "f11_cdf_duration_s",
    "f11_cdf_dominant_frequency_hz",
    "f11_cdf_v2_s",
)
_GRID_IDS = (
    "f11_cdf_grid_absolute_peak_v",
    "f11_cdf_grid_duration_s",
    "f11_cdf_grid_dominant_frequency_hz",
    "f11_cdf_grid_v2_s",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[F11_INDEX]


def _band() -> Band:
    recipe = _recipe()
    return Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)


def _build(
    result: F11Result,
    *,
    family: CharacterizationFamily | None = None,
    channel: str = "ch1",
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    return build_f11_family(
        result,
        _family() if family is None else family,
        _band(),
        measured_channel=channel,
        record_duration_s=_RECORD_S,
    )


def _cdf(first: float = 0.05, middle: float = 0.5, last: float = 1.0) -> tuple[float, ...]:
    values = [0.25] * CDF_PROBABILITIES.size
    values[0] = first
    values[len(values) // 2] = middle
    values[-1] = last
    return tuple(values)


def _absent_frequency(quantity: str, support_count: int) -> F11QuantityResult:
    assert quantity == "dominant_frequency_hz"
    return F11QuantityResult(
        quantity=quantity,
        observed_count=0,
        missing_count=support_count,
        status=Status.UNAVAILABLE,
        reason_codes=(INSUFFICIENT_SUPPORT,),
        quantiles=(None,) * len(QUANTILES),
        cdf_probabilities=None,
    )


def _available_distribution(quantity: str, count: int = 20) -> F11QuantityResult:
    if quantity == "dominant_frequency_hz":
        return _absent_frequency(quantity, count)
    if quantity == "absolute_peak_v":
        quantiles = (2.9, 5.75, 10.5, 15.25, 18.1, 19.81)
    elif quantity == "duration_s":
        quantiles = (0.0029, 0.00575, 0.0105, 0.01525, 0.0181, 0.01981)
    else:
        quantiles = (1.45, 2.875, 5.25, 7.625, 9.05, 9.905)
    selected = (
        quantiles if count == 20 else tuple(float(index + 1) for index in range(len(QUANTILES)))
    )
    return F11QuantityResult(
        quantity=quantity,
        observed_count=count,
        missing_count=0,
        status=Status.AVAILABLE,
        reason_codes=(),
        quantiles=selected,
        cdf_probabilities=_cdf(),
    )


def _empty_distribution(quantity: str) -> F11QuantityResult:
    if quantity == "dominant_frequency_hz":
        return _absent_frequency(quantity, 0)
    return F11QuantityResult(
        quantity=quantity,
        observed_count=0,
        missing_count=0,
        status=Status.UNAVAILABLE,
        reason_codes=(BIN_EMPTY,),
        quantiles=(None,) * len(QUANTILES),
        cdf_probabilities=None,
    )


def _supported_cell(
    phase_bin: int,
    band_index: int,
    mode_label: str,
    *,
    support: int = 20,
    available: bool = True,
) -> F11Cell:
    distributions = tuple(
        _absent_frequency(quantity, support)
        if quantity == "dominant_frequency_hz"
        else _available_distribution(quantity, support)
        if available
        else F11QuantityResult(
            quantity=quantity,
            observed_count=support,
            missing_count=0,
            status=Status.UNAVAILABLE,
            reason_codes=(INSUFFICIENT_SUPPORT,),
            quantiles=(None,) * len(QUANTILES),
            cdf_probabilities=None,
        )
        for quantity in QUANTITIES[:-1]
    )
    return F11Cell(
        phase_bin=phase_bin,
        band_index=band_index,
        mode_label=mode_label,
        support_count=support,
        positive_count=support // 2,
        negative_count=support - support // 2,
        status=Status.AVAILABLE if available else Status.UNAVAILABLE,
        reason_codes=() if available else (INSUFFICIENT_SUPPORT,),
        distributions=distributions,
    )


def _empty_cell(phase_bin: int, band_index: int, mode_label: str) -> F11Cell:
    return F11Cell(
        phase_bin=phase_bin,
        band_index=band_index,
        mode_label=mode_label,
        support_count=0,
        positive_count=0,
        negative_count=0,
        status=Status.UNAVAILABLE,
        reason_codes=(BIN_EMPTY,),
        distributions=tuple(_empty_distribution(quantity) for quantity in QUANTITIES[:-1]),
    )


def _cells(
    supported: dict[tuple[int, int, str], F11Cell] | None = None,
) -> tuple[F11Cell, ...]:
    supported = {} if supported is None else supported
    return tuple(
        supported.get((phase, band, label), _empty_cell(phase, band, label))
        for phase in range(_PHASE_BINS)
        for band in range(len(_BANDS))
        for label in _LABELS
    )


def _grids() -> tuple[tuple[float, ...], ...]:
    grid = tuple(float(value) for value in np.linspace(1.0, 20.0, CDF_PROBABILITIES.size))
    return grid, grid, (), grid


def _available() -> F11Result:
    first = _supported_cell(0, 0, _LABELS[0])
    return F11Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        cells=_cells({(first.phase_bin, first.band_index, first.mode_label): first}),
        phase_bin_edges_rad=tuple(2.0 * np.pi * index / _PHASE_BINS for index in range(17)),
        bands_hz=_BANDS,
        mode_labels=_LABELS,
        quantiles=QUANTILES,
        cdf_probabilities=tuple(float(value) for value in CDF_PROBABILITIES),
        cdf_grids=_grids(),
        event_count=20,
        evaluated_event_count=20,
        omitted_event_count=0,
        n_missing=0,
        n_mode_missing=0,
        n_dominant_band_unavailable=0,
        n_phase_unavailable=0,
    )


def _partial_support() -> F11Result:
    weak = _supported_cell(0, 0, _LABELS[0], support=19, available=False)
    strong = _supported_cell(0, 0, _LABELS[1])
    return F11Result(
        status=Status.PARTIAL,
        reason_codes=(INSUFFICIENT_SUPPORT,),
        cells=_cells(
            {
                (weak.phase_bin, weak.band_index, weak.mode_label): weak,
                (strong.phase_bin, strong.band_index, strong.mode_label): strong,
            }
        ),
        phase_bin_edges_rad=tuple(2.0 * np.pi * index / _PHASE_BINS for index in range(17)),
        bands_hz=_BANDS,
        mode_labels=_LABELS,
        quantiles=QUANTILES,
        cdf_probabilities=tuple(float(value) for value in CDF_PROBABILITIES),
        cdf_grids=_grids(),
        event_count=39,
        evaluated_event_count=39,
        omitted_event_count=0,
        n_missing=0,
        n_mode_missing=0,
        n_dominant_band_unavailable=0,
        n_phase_unavailable=0,
    )


def _event_cap() -> F11Result:
    cell = _supported_cell(0, 0, _LABELS[0], support=MAXIMUM_EVENTS)
    return F11Result(
        status=Status.PARTIAL,
        reason_codes=(EVENT_LIMIT,),
        cells=_cells({(cell.phase_bin, cell.band_index, cell.mode_label): cell}),
        phase_bin_edges_rad=tuple(2.0 * np.pi * index / _PHASE_BINS for index in range(17)),
        bands_hz=_BANDS,
        mode_labels=_LABELS,
        quantiles=QUANTILES,
        cdf_probabilities=tuple(float(value) for value in CDF_PROBABILITIES),
        cdf_grids=_grids(),
        event_count=MAXIMUM_EVENTS + 7,
        evaluated_event_count=MAXIMUM_EVENTS,
        omitted_event_count=7,
        n_missing=0,
        n_mode_missing=0,
        n_dominant_band_unavailable=0,
        n_phase_unavailable=0,
    )


def _unavailable() -> F11Result:
    return F11Result(
        status=Status.UNAVAILABLE,
        reason_codes=("mode_unavailable",),
        cells=(),
        phase_bin_edges_rad=tuple(2.0 * np.pi * index / _PHASE_BINS for index in range(17)),
        bands_hz=_BANDS,
        mode_labels=_LABELS,
        quantiles=QUANTILES,
        cdf_probabilities=tuple(float(value) for value in CDF_PROBABILITIES),
        cdf_grids=((), (), (), ()),
        event_count=20,
        evaluated_event_count=0,
        omitted_event_count=0,
        n_missing=0,
        n_mode_missing=0,
        n_dominant_band_unavailable=0,
        n_phase_unavailable=0,
    )


def _replace(result: F11Result, **fields: object) -> F11Result:
    return dataclasses.replace(result, **fields)


def _full_bundle(
    family: FamilyResult, arrays: dict[str, np.ndarray], tables: dict[str, TableBlock]
) -> tuple[CharacterizationBundle, dict[str, np.ndarray], dict[str, TableBlock]]:
    recipe = _recipe()
    band = _band()
    families = tuple(
        family if index == F11_INDEX else not_computed_family(recipe.families[index], band)
        for index in range(len(recipe.families))
    )
    return CharacterizationBundle(families=families), arrays, tables


def test_constants_match_recipe_and_contract() -> None:
    recipe = _recipe()
    assert F11_INDEX == 10
    assert F11_ID == "f11_conditional_distributions"
    assert FAMILY_IDS[F11_INDEX] == F11_ID
    assert recipe.families[F11_INDEX].id == F11_ID
    assert recipe.families[F11_INDEX].method == "fixed_phase_band_f15_mode_empirical_distributions"
    assert recipe.families[F11_INDEX].method_version == 1
    assert recipe.families[F11_INDEX].value("mode_source_family_id") == "f15_interpretable_modes"


def test_available_maps_family_axes_cells_and_table() -> None:
    family, arrays, tables = _build(_available())
    refs = {ref.array_id: ref for ref in family.array_refs}

    assert family.family_id == F11_ID
    assert family.status is Status.AVAILABLE
    assert family.reason_codes == ()
    assert family.units == (Unit.V, Unit.S, Unit.HZ, Unit.V2_S, Unit.COUNT, Unit.RATIO, Unit.RAD)
    assert family.window.kind == "record"
    assert family.window.duration_s == _RECORD_S
    assert family.support.observation_count == 20
    assert family.support.missing_count == 0
    assert family.support.stored_count == 20
    assert family.n == 20
    assert family.table_refs == (TableReference(table_id=_TABLE_ID, role="conditional_cells"),)
    assert set(arrays) >= set(_ARRAY_IDS)
    assert set(tables) == {_TABLE_ID}
    assert tables[_TABLE_ID].row_count == _CELL_COUNT
    assert tables[_TABLE_ID].stored_count == _CELL_COUNT
    assert tables[_TABLE_ID].selection_rule == "all"
    for array_id in _ARRAY_IDS:
        assert array_id in refs
        assert refs[array_id].shape == arrays[array_id].shape
        assert refs[array_id].dtype == arrays[array_id].dtype.name


def test_axes_and_one_pooled_grid_per_quantity_make_cdfs_addressable() -> None:
    result = _available()
    family, arrays, _ = _build(result)
    refs = {ref.array_id: ref for ref in family.array_refs}

    assert np.array_equal(arrays["f11_phase_bin"], np.arange(_PHASE_BINS, dtype=np.int64))
    assert np.array_equal(arrays["f11_band_index"], np.arange(len(_BANDS), dtype=np.int64))
    assert np.array_equal(arrays["f11_mode_index"], np.arange(len(_LABELS), dtype=np.int64))
    assert np.array_equal(arrays["f11_quantile_level"], np.asarray(QUANTILES))
    assert np.array_equal(arrays["f11_cdf_probability"], np.asarray(CDF_PROBABILITIES))
    assert arrays["f11_cdf_grid_absolute_peak_v"].shape == (CDF_PROBABILITIES.size,)
    assert arrays["f11_cdf_grid_duration_s"].shape == (CDF_PROBABILITIES.size,)
    assert arrays["f11_cdf_grid_dominant_frequency_hz"].shape == (0,)
    assert arrays["f11_cdf_grid_v2_s"].shape == (CDF_PROBABILITIES.size,)
    assert refs["f11_cdf_absolute_peak_v"].shape == _CDF_SHAPE
    assert refs["f11_cdf_dominant_frequency_hz"].shape == (_CELL_COUNT, 0)
    assert refs["f11_absolute_peak_v"].shape == _QUANTILE_SHAPE
    assert np.array_equal(arrays["f11_cdf_grid_absolute_peak_v"], result.cdf_grids[0])
    assert np.array_equal(arrays["f11_cdf_grid_v2_s"], result.cdf_grids[3])


def test_frequency_quantity_is_absent_at_every_cell_without_degrading_status() -> None:
    """Given supported cells, when frequency is structural absence, then masks and table say so."""
    family, arrays, tables = _build(_available())
    table = tables[_TABLE_ID]
    columns = {column.name: index for index, column in enumerate(table.columns)}

    assert family.status is Status.AVAILABLE
    assert np.count_nonzero(arrays["f11_dominant_frequency_hz_valid"]) == 0
    assert arrays["f11_cdf_dominant_frequency_hz"].shape == (_CELL_COUNT, 0)
    assert arrays["f11_cdf_grid_dominant_frequency_hz"].shape == (0,)
    for row, support in zip(table.rows, arrays["f11_cell_support_count"].flat, strict=True):
        assert row[columns["f11_dominant_frequency_observed_count"]] == 0
        assert row[columns["f11_dominant_frequency_missing_count"]] == support
        assert row[columns["f11_dominant_frequency_status"]] == Status.UNAVAILABLE.value
        assert row[columns["f11_dominant_frequency_reason_code"]] == INSUFFICIENT_SUPPORT


def test_every_cell_is_explicit_and_empty_cells_keep_bin_empty() -> None:
    _, arrays, tables = _build(_available())
    table = tables[_TABLE_ID]
    reason_index = next(
        index for index, column in enumerate(table.columns) if column.name == "cell_reason_code"
    )
    rows = table.rows

    assert len(rows) == _CELL_COUNT
    assert sum(row[reason_index] == BIN_EMPTY for row in rows) == _CELL_COUNT - 1
    assert sum(isinstance(row[3], int) and row[3] > 0 for row in rows) == 1
    assert arrays["f11_cell_support_count"].shape == _CELL_SHAPE
    assert int(np.count_nonzero(arrays["f11_cell_support_count"])) == 1
    assert arrays["f11_absolute_peak_v_valid"].shape == _QUANTILE_SHAPE
    assert int(np.count_nonzero(arrays["f11_absolute_peak_v_valid"])) == len(QUANTILES)
    assert int(np.count_nonzero(arrays["f11_cdf_absolute_peak_v_valid"])) == CDF_PROBABILITIES.size


def test_under_supported_cell_has_absent_quantiles_and_cdf_with_explicit_code() -> None:
    _, arrays, tables = _build(_partial_support())
    weak_index = 0
    assert arrays["f11_absolute_peak_v_valid"][weak_index].tolist() == [0] * len(QUANTILES)
    assert (
        arrays["f11_cdf_absolute_peak_v_valid"][weak_index].tolist() == [0] * CDF_PROBABILITIES.size
    )
    assert np.all(arrays["f11_absolute_peak_v"][weak_index] == 0.0)
    assert np.all(arrays["f11_cdf_absolute_peak_v"][weak_index] == 0.0)
    table = tables[_TABLE_ID]
    reason_index = next(
        index for index, column in enumerate(table.columns) if column.name == "cell_reason_code"
    )
    quantity_reason_index = next(
        index
        for index, column in enumerate(table.columns)
        if column.name == "f11_absolute_peak_reason_code"
    )
    assert table.rows[weak_index][reason_index] == INSUFFICIENT_SUPPORT
    assert table.rows[weak_index][quantity_reason_index] == INSUFFICIENT_SUPPORT


def test_unavailable_result_publishes_empty_domains() -> None:
    family, arrays, tables = _build(_unavailable())

    assert family.status is Status.UNAVAILABLE
    assert family.reason_codes == ("mode_unavailable",)
    assert family.array_refs == ()
    assert family.table_refs == ()
    assert family.comparison_summary == ()
    assert arrays == {}
    assert tables == {}
    assert family.support.sample_count == 0
    assert family.support.observation_count == 0
    assert family.support.missing_count == 0
    assert family.support.stored_count == 0
    assert family.n == 0


def test_event_cap_is_visible_in_summary_and_support() -> None:
    result = _event_cap()
    family, _, _ = _build(result)
    summaries = {item.name: item for item in family.comparison_summary}

    assert summaries["f11_maximum_events"].value == float(MAXIMUM_EVENTS)
    assert summaries["f11_omitted_event_count"].value == 7.0
    assert summaries["f11_evaluated_event_count"].value == float(MAXIMUM_EVENTS)
    assert family.support.sample_count == MAXIMUM_EVENTS + 7
    assert family.support.observation_count == MAXIMUM_EVENTS
    assert family.support.missing_count == 7
    assert family.reason_codes == (EVENT_LIMIT,)


def test_dtypes_and_units_survive_persistence_vocabulary() -> None:
    family, arrays, _ = _build(_available())
    refs = {ref.array_id: ref for ref in family.array_refs}

    assert arrays["f11_cell_support_count"].dtype == np.int64
    assert arrays["f11_absolute_peak_v"].dtype == np.float64
    assert arrays["f11_cdf_absolute_peak_v"].dtype == np.float64
    assert arrays["f11_absolute_peak_v_valid"].dtype == np.uint8
    assert refs["f11_v2_s"].unit is Unit.V2_S
    assert refs["f11_cdf_v2_s"].unit is Unit.RATIO
    assert refs["f11_cdf_grid_v2_s"].unit is Unit.V2_S
    assert refs["f11_phase_bin_edges_rad"].unit is Unit.RAD
    assert all(ref.array_id != "f11_bipolar_count" for ref in family.array_refs)


def test_round_trip_preserves_family_arrays_tables_and_dtypes() -> None:
    family, arrays, tables = _build(_partial_support())
    bundle, all_arrays, all_tables = _full_bundle(family, arrays, tables)
    files = encode_bundle(
        bundle,
        all_arrays,
        all_tables,
        max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
    )

    loaded = load_bundle(files)

    assert loaded.bundle.families[F11_INDEX] == family
    assert set(loaded.arrays) == set(arrays)
    for array_id, values in arrays.items():
        assert loaded.arrays[array_id].dtype == values.dtype
        assert loaded.arrays[array_id].shape == values.shape
        assert np.array_equal(loaded.arrays[array_id], values)
    assert dict(loaded.tables) == tables
    loaded_table = loaded.tables[_TABLE_ID]
    assert loaded_table is not None
    assert loaded_table.rows == tables[_TABLE_ID].rows
    columns = {column.name: index for index, column in enumerate(loaded_table.columns)}
    for row, support in zip(
        loaded_table.rows, all_arrays["f11_cell_support_count"].flat, strict=True
    ):
        assert row[columns["f11_dominant_frequency_observed_count"]] == 0
        assert row[columns["f11_dominant_frequency_missing_count"]] == support
        assert row[columns["f11_dominant_frequency_status"]] == Status.UNAVAILABLE.value
        assert row[columns["f11_dominant_frequency_reason_code"]] == INSUFFICIENT_SUPPORT
    assert np.count_nonzero(loaded.arrays["f11_dominant_frequency_hz_valid"]) == 0
    assert loaded.arrays["f11_cdf_dominant_frequency_hz"].shape == (_CELL_COUNT, 0)
    assert loaded.arrays["f11_cdf_grid_dominant_frequency_hz"].shape == (0,)


def test_wrong_recipe_slot_is_rejected() -> None:
    with pytest.raises(CharacterizationError, match="family_order"):
        _build(_available(), family=_recipe().families[F11_INDEX - 1])


@pytest.mark.parametrize(
    "result",
    [
        _replace(_available(), reason_codes=("event_limit",)),
        _replace(_available(), status=Status.PARTIAL),
        _replace(_unavailable(), reason_codes=()),
        _replace(_unavailable(), reason_codes=("not_an_f11_code",)),
        _replace(_unavailable(), reason_codes=("mode_unavailable", "mode_unavailable")),
        _replace(_unavailable(), reason_codes=("mode_unavailable", "insufficient_support")),
    ],
)
def test_family_status_and_reason_invariants_are_rejected(result: F11Result) -> None:
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(result)


def test_misaligned_distribution_arrays_are_rejected() -> None:
    result = _available()
    cell = result.cells[0]
    distribution = cell.distributions[0]
    broken = dataclasses.replace(
        result,
        cells=(
            dataclasses.replace(
                cell,
                distributions=(
                    dataclasses.replace(distribution, quantiles=distribution.quantiles[:-1]),
                    *cell.distributions[1:],
                ),
            ),
            *result.cells[1:],
        ),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)

    probabilities = distribution.cdf_probabilities
    assert probabilities is not None
    broken_cdf = dataclasses.replace(
        result,
        cells=(
            dataclasses.replace(
                cell,
                distributions=(
                    dataclasses.replace(
                        distribution,
                        cdf_probabilities=probabilities[:-1],
                    ),
                    *cell.distributions[1:],
                ),
            ),
            *result.cells[1:],
        ),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken_cdf)


def test_wrong_shape_validity_mask_is_rejected_by_codec() -> None:
    family, arrays, tables = _build(_partial_support())
    bundle, all_arrays, all_tables = _full_bundle(family, arrays, tables)
    broken_arrays = dict(all_arrays)
    broken_arrays["f11_absolute_peak_v_valid"] = np.zeros(1, dtype=np.uint8)
    with pytest.raises(CharacterizationError, match="array_mask"):
        encode_bundle(
            bundle,
            broken_arrays,
            all_tables,
            max_artifact_bytes=_recipe().resource_limits.max_artifact_bytes,
        )


def test_broken_event_accounting_is_rejected() -> None:
    for broken in (
        _replace(_available(), event_count=21),
        _replace(_available(), evaluated_event_count=19),
        _replace(_available(), omitted_event_count=1),
        _replace(_available(), n_missing=1),
    ):
        with pytest.raises(CharacterizationError, match="status_invariant"):
            _build(broken)


def test_broken_cell_accounting_is_rejected() -> None:
    result = _available()
    cell = result.cells[0]
    broken = _replace(
        result,
        cells=(
            dataclasses.replace(cell, support_count=19),
            *result.cells[1:],
        ),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_structurally_absent_frequency_distribution_is_validated() -> None:
    result = _available()
    cell = result.cells[0]
    frequency = cell.distributions[2]
    broken = _replace(
        result,
        cells=(
            dataclasses.replace(
                cell,
                distributions=(
                    *cell.distributions[:2],
                    dataclasses.replace(frequency, missing_count=frequency.missing_count - 1),
                    cell.distributions[3],
                ),
            ),
            *result.cells[1:],
        ),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)


def test_unsorted_and_duplicated_cell_reason_codes_are_rejected() -> None:
    result = _partial_support()
    cell = result.cells[0]
    broken = _replace(
        result,
        cells=(
            dataclasses.replace(cell, reason_codes=(INSUFFICIENT_SUPPORT, BIN_EMPTY)),
            *result.cells[1:],
        ),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(broken)

    duplicate = _replace(
        result,
        cells=(
            dataclasses.replace(cell, reason_codes=(INSUFFICIENT_SUPPORT, INSUFFICIENT_SUPPORT)),
            *result.cells[1:],
        ),
    )
    with pytest.raises(CharacterizationError, match="status_invariant"):
        _build(duplicate)


def test_declared_vocabulary_is_closed() -> None:
    assert set(DECLARED_CODES) == {
        "phase_reference_unavailable",
        "insufficient_support",
        "bin_empty",
        "dominant_band_unavailable",
        "mode_unavailable",
        "mode_assignment_unavailable",
        "event_limit",
        "gaps_present",
    }
