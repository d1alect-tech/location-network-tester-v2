"""Published numeric and tabular layout for the F11 conditional distributions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Unit, validate_unit_name
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    from lnt.characterization.f11_result import F11Cell, F11Result

CELL_SHAPE: Final = (16, 3, 4)
CELL_TABLE_ID: Final = "f11_cells"
_QUANTITY_NAMES: Final = ("absolute_peak_v", "duration_s", "dominant_frequency_hz", "v2_s")
_QUANTILE_IDS: Final = tuple(f"f11_{name}" for name in _QUANTITY_NAMES)
_COUNT_IDS: Final = ("f11_absolute_peak", "f11_duration", "f11_dominant_frequency", "f11_v2_s")
_CDF_IDS: Final = tuple(f"f11_cdf_{name}" for name in _QUANTITY_NAMES)
_GRID_IDS: Final = tuple(f"f11_cdf_grid_{name}" for name in _QUANTITY_NAMES)
_AXIS_ENTRIES: Final = (
    ("f11_phase_bin", "phase_bin_axis", Unit.COUNT),
    ("f11_phase_bin_edges_rad", "phase_bin_edges", Unit.RAD),
    ("f11_band_index", "band_index_axis", Unit.COUNT),
    ("f11_band_low_hz", "band_low_edges", Unit.HZ),
    ("f11_band_high_hz", "band_high_edges", Unit.HZ),
    ("f11_mode_index", "mode_axis", Unit.COUNT),
    ("f11_quantile_level", "quantile_levels", Unit.RATIO),
    ("f11_cdf_probability", "cdf_probabilities", Unit.RATIO),
)


def published(
    result: F11Result, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Publish F11 arrays and typed references."""
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    _axes(result, arrays, refs, partial=partial)
    _cell_counters(result, arrays, refs, partial=partial)
    _quantiles(result, arrays, refs)
    _cdfs(result, arrays, refs)
    _grids(result, arrays, refs, partial=partial)
    return arrays, refs


def cell_table(result: F11Result) -> TableBlock:
    """Publish one explicit row for every F11 cell."""
    columns = _table_columns()
    rows = tuple(_table_row(cell) for cell in result.cells)
    return TableBlock(
        table_id=CELL_TABLE_ID,
        columns=columns,
        rows=rows,
        row_count=192,
        stored_count=len(rows),
        selection_rule="all",
    )


def _axes(
    result: F11Result,
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    *,
    partial: bool,
) -> None:
    values = {
        "f11_phase_bin": np.arange(16, dtype=np.int64),
        "f11_phase_bin_edges_rad": np.asarray(result.phase_bin_edges_rad, dtype=np.float64),
        "f11_band_index": np.arange(3, dtype=np.int64),
        "f11_band_low_hz": np.asarray(tuple(pair[0] for pair in result.bands_hz), dtype=np.float64),
        "f11_band_high_hz": np.asarray(
            tuple(pair[1] for pair in result.bands_hz), dtype=np.float64
        ),
        "f11_mode_index": np.arange(4, dtype=np.int64),
        "f11_quantile_level": np.asarray(result.quantiles, dtype=np.float64),
        "f11_cdf_probability": np.asarray(result.cdf_probabilities, dtype=np.float64),
    }
    for array_id, role, unit in _AXIS_ENTRIES:
        _store(arrays, refs, array_id, role, unit, values[array_id], partial=partial)


def _cell_counters(
    result: F11Result,
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    *,
    partial: bool,
) -> None:
    columns = {
        "f11_cell_support_count": np.asarray(
            [cell.support_count for cell in result.cells], dtype=np.int64
        ).reshape(CELL_SHAPE),
        "f11_cell_positive_count": np.asarray(
            [cell.positive_count for cell in result.cells], dtype=np.int64
        ).reshape(CELL_SHAPE),
        "f11_cell_negative_count": np.asarray(
            [cell.negative_count for cell in result.cells], dtype=np.int64
        ).reshape(CELL_SHAPE),
    }
    entries = (
        ("f11_cell_support_count", "cell_support_count", Unit.COUNT),
        ("f11_cell_positive_count", "cell_positive_count", Unit.COUNT),
        ("f11_cell_negative_count", "cell_negative_count", Unit.COUNT),
    )
    for array_id, role, unit in entries:
        _store(arrays, refs, array_id, role, unit, columns[array_id], partial=partial)


def _quantiles(
    result: F11Result,
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
) -> None:
    shape = (192, len(result.quantiles))
    for quantity_index, name in enumerate(_QUANTILE_IDS):
        values = np.zeros(shape, dtype=np.float64)
        mask = np.zeros(shape, dtype=np.uint8)
        for cell_index, cell in enumerate(result.cells):
            distribution = cell.distributions[quantity_index]
            if distribution.status.value == "available":
                values[cell_index] = np.asarray(distribution.quantiles, dtype=np.float64)
                mask[cell_index] = 1
        arrays[f"{name}_valid"] = mask
        _store(
            arrays,
            refs,
            name,
            "conditional_quantile",
            _quantity_unit(quantity_index),
            values,
            mask_id=f"{name}_valid",
        )


def _cdfs(
    result: F11Result,
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
) -> None:
    for quantity_index, name in enumerate(_CDF_IDS):
        grid_size = len(result.cdf_grids[quantity_index])
        shape = (192, grid_size)
        values = np.zeros(shape, dtype=np.float64)
        mask = np.zeros(shape, dtype=np.uint8)
        for cell_index, cell in enumerate(result.cells):
            distribution = cell.distributions[quantity_index]
            if distribution.status.value == "available":
                values[cell_index] = np.asarray(distribution.cdf_probabilities, dtype=np.float64)
                mask[cell_index] = 1
        arrays[f"{name}_valid"] = mask
        _store(arrays, refs, name, "conditional_cdf", Unit.RATIO, values, mask_id=f"{name}_valid")


def _grids(
    result: F11Result,
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    *,
    partial: bool,
) -> None:
    for index, name in enumerate(_GRID_IDS):
        values = np.asarray(result.cdf_grids[index], dtype=np.float64)
        _store(
            arrays, refs, name, "pooled_cdf_grid", _quantity_unit(index), values, partial=partial
        )


def _store(  # noqa: PLR0913, PLR0917 - one shared typed-array sink
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    array_id: str,
    role: str,
    unit: Unit,
    values: np.ndarray,
    *,
    partial: bool = False,
    mask_id: str | None = None,
) -> None:
    validate_unit_name(array_id, unit)
    if partial and mask_id is None:
        mask_id = f"{array_id}_valid"
    if mask_id is not None and mask_id not in arrays:
        arrays[mask_id] = np.ones(values.shape, dtype=np.uint8)
    arrays[array_id] = values
    refs.append(
        ArrayReference(
            array_id=array_id,
            role=role,
            unit=unit,
            dtype=values.dtype.name,
            shape=tuple(int(size) for size in values.shape),
            validity_mask_id=mask_id,
            offsets_id=None,
        )
    )


def _quantity_unit(index: int) -> Unit:
    return (Unit.V, Unit.S, Unit.HZ, Unit.V2_S)[index]


def _table_columns() -> tuple[TableColumn, ...]:
    columns: list[TableColumn] = [
        TableColumn(name="phase_bin", unit=Unit.COUNT, type=TableValueType.INTEGER),
        TableColumn(name="band_index", unit=Unit.COUNT, type=TableValueType.INTEGER),
        TableColumn(name="mode_label", unit=None, type=TableValueType.TEXT),
        TableColumn(name="support_count", unit=Unit.COUNT, type=TableValueType.INTEGER),
        TableColumn(name="positive_count", unit=Unit.COUNT, type=TableValueType.INTEGER),
        TableColumn(name="negative_count", unit=Unit.COUNT, type=TableValueType.INTEGER),
        TableColumn(name="status", unit=None, type=TableValueType.TEXT),
        TableColumn(name="cell_reason_code", unit=None, type=TableValueType.REASON_CODE),
    ]
    for name in _COUNT_IDS:
        columns.extend(
            (
                TableColumn(
                    name=f"{name}_observed_count", unit=Unit.COUNT, type=TableValueType.INTEGER
                ),
                TableColumn(
                    name=f"{name}_missing_count", unit=Unit.COUNT, type=TableValueType.INTEGER
                ),
                TableColumn(name=f"{name}_status", unit=None, type=TableValueType.TEXT),
                TableColumn(name=f"{name}_reason_code", unit=None, type=TableValueType.REASON_CODE),
            )
        )
    return tuple(columns)


def _table_row(cell: F11Cell) -> tuple[str | int | float | bool | None, ...]:
    row: list[str | int | float | bool | None] = [
        cell.phase_bin,
        cell.band_index,
        cell.mode_label,
        cell.support_count,
        cell.positive_count,
        cell.negative_count,
        cell.status.value,
        _reason(cell.reason_codes),
    ]
    for distribution in cell.distributions:
        row.extend(
            (
                distribution.observed_count,
                distribution.missing_count,
                distribution.status.value,
                _reason(distribution.reason_codes),
            )
        )
    return tuple(row)


def _reason(codes: tuple[str, ...]) -> str | None:
    return "|".join(codes) if codes else None
