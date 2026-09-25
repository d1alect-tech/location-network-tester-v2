"""F17: finite-domain arrays, validity masks и публикация сетки ячеек."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f17_contract import (
    BH_P_VALUE_NAME,
    COHERENCE_NAME,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_SPECTRUM_NAME,
    FREQUENCY_NAME,
    RAW_P_VALUE_NAME,
    SEGMENT_SUPPORT_NAME,
)
from lnt.characterization.f17_validation import validate_f17_result
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Unit, validate_unit_name

if TYPE_CHECKING:
    from lnt.characterization.f17_result import F17Declarations, F17Result

__all__ = [
    "ARRAY_IDS",
    "CELL_AVAILABLE_ID",
    "COUNTER_FIELDS",
    "ENTRIES",
    "SIGNIFICANT_ID",
    "STORED_ALPHA_ID",
    "expected_mask_id",
    "published",
    "shape_for",
]

CELL_AVAILABLE_ID: Final = "f17_cell_available"
SIGNIFICANT_ID: Final = "f17_significant"
STORED_ALPHA_ID: Final = "f17_stored_alpha_hz"
STORED_FREQUENCY_ID: Final = "f17_stored_frequency_hz"
STORED_SPECTRUM_ID: Final = "f17_stored_cyclic_spectrum_v2"
STORED_COHERENCE_ID: Final = "f17_stored_coherence"
STORED_RAW_P_ID: Final = "f17_stored_raw_p_value"
STORED_BH_P_ID: Final = "f17_stored_bh_p_value"
STORED_SUPPORT_ID: Final = "f17_stored_segment_support"
_ALPHA: Final = "alpha"
_FREQUENCY: Final = "frequency"
_GRID: Final = "grid"
_STORED: Final = "stored"

# (array_id, role, unit, dtype, shape key, declared domain mask)
type Entry = tuple[str, str, Unit, str, str, str | None]

# Порядок ссылок каноничен: decode сверяет его целиком, иначе ref-order дрейфует.
ENTRIES: Final[tuple[Entry, ...]] = (
    (FREQUENCY_NAME, "frequency_axis", Unit.HZ, "float64", _FREQUENCY, None),
    (CYCLIC_FREQUENCY_NAME, "cyclic_frequency_axis", Unit.HZ, "float64", _ALPHA, None),
    (CYCLIC_SPECTRUM_NAME, "cyclic_spectrum", Unit.V2, "complex128", _GRID, CELL_AVAILABLE_ID),
    (COHERENCE_NAME, "coherence", Unit.RATIO, "float64", _GRID, CELL_AVAILABLE_ID),
    (RAW_P_VALUE_NAME, "raw_p_value", Unit.RATIO, "float64", _GRID, CELL_AVAILABLE_ID),
    (BH_P_VALUE_NAME, "bh_p_value", Unit.RATIO, "float64", _GRID, CELL_AVAILABLE_ID),
    (SEGMENT_SUPPORT_NAME, "segment_support", Unit.COUNT, "int64", _GRID, CELL_AVAILABLE_ID),
    (SIGNIFICANT_ID, "significant_cell", Unit.COUNT, "uint8", _GRID, CELL_AVAILABLE_ID),
    (STORED_ALPHA_ID, "stored_alpha_axis", Unit.HZ, "float64", _STORED, None),
    (STORED_FREQUENCY_ID, "stored_frequency_axis", Unit.HZ, "float64", _STORED, None),
    (STORED_SPECTRUM_ID, "stored_cyclic_spectrum", Unit.V2, "complex128", _STORED, None),
    (STORED_COHERENCE_ID, "stored_coherence", Unit.RATIO, "float64", _STORED, None),
    (STORED_RAW_P_ID, "stored_raw_p_value", Unit.RATIO, "float64", _STORED, None),
    (STORED_BH_P_ID, "stored_bh_p_value", Unit.RATIO, "float64", _STORED, None),
    (STORED_SUPPORT_ID, "stored_segment_support", Unit.COUNT, "int64", _STORED, None),
)
ARRAY_IDS: Final[tuple[str, ...]] = tuple(entry[0] for entry in ENTRIES)
# Только эти четыре публикуют NaN в движке: они и только они получают declared fill 0.0.
_FILL_MEASUREMENTS: Final[frozenset[str]] = frozenset(
    {CYCLIC_SPECTRUM_NAME, COHERENCE_NAME, RAW_P_VALUE_NAME, BH_P_VALUE_NAME}
)
# Compact stored домен: persisted id -> поле F17Result.
_STORED_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    (STORED_ALPHA_ID, "stored_alpha_hz"),
    (STORED_FREQUENCY_ID, "stored_frequency_hz"),
    (STORED_SPECTRUM_ID, "stored_cyclic_spectrum"),
    (STORED_COHERENCE_ID, "stored_coherence"),
    (STORED_RAW_P_ID, "stored_raw_p_value"),
    (STORED_BH_P_ID, "stored_bh_p_value"),
    (STORED_SUPPORT_ID, "stored_segment_support"),
)
# Persisted accounting surface: имя счётчика в F17Result == summary без префикса.
COUNTER_FIELDS: Final[tuple[str, ...]] = (
    "sample_count",
    "qualified_sample_count",
    "qualified_cycle_count",
    "frame_count",
    "tested_cell_count",
    "significant_cell_count",
    "stored_cell_count",
    "omitted_cell_count",
)


def shape_for(
    key: str, alpha_count: int, frequency_count: int, stored_count: int
) -> tuple[int, ...]:
    """Вернуть locked геометрию одного persisted домена."""
    if key == _ALPHA:
        return (alpha_count,)
    if key == _FREQUENCY:
        return (frequency_count,)
    if key == _GRID:
        return (alpha_count, frequency_count)
    if key == _STORED:
        return (stored_count,)
    raise CharacterizationError("status_invariant", f"F17 shape key {key!r} is not declared")


def expected_mask_id(array_id: str, domain_mask: str | None, *, partial: bool) -> str | None:
    """Вернуть канонический mask ref: declared домен либо синтезированная полная метка."""
    if domain_mask is not None:
        return domain_mask
    return f"{array_id}_valid" if partial else None


def published(
    result: F17Result, declarations: F17Declarations, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Проверить engine-контракт и опубликовать finite arrays с масками."""
    validate_f17_result(result)
    values = _values(result)
    alpha_count = len(declarations.cyclic_frequencies_hz)
    frequency_count = int(result.frequencies_hz.size)
    stored_count = int(result.stored_cell_count)
    cell = np.asarray(result.cell_available, dtype=np.bool_)
    arrays: dict[str, np.ndarray] = {}
    references: list[ArrayReference] = []
    for array_id, role, unit, dtype, shape_key, domain_mask in ENTRIES:
        expected = shape_for(shape_key, alpha_count, frequency_count, stored_count)
        checked = _checked(array_id, values[array_id], dtype, expected)
        if domain_mask is not None:
            arrays[domain_mask] = cell.astype(np.uint8)
        if array_id in _FILL_MEASUREMENTS:
            checked = _fill(checked, cell)
        _store(arrays, references, array_id, role, unit, checked, domain_mask, partial=partial)
    return arrays, references


def _values(result: F17Result) -> dict[str, np.ndarray]:
    return {
        FREQUENCY_NAME: result.frequencies_hz,
        CYCLIC_FREQUENCY_NAME: result.cyclic_frequencies_hz,
        CYCLIC_SPECTRUM_NAME: result.cyclic_spectrum,
        COHERENCE_NAME: result.coherence,
        RAW_P_VALUE_NAME: result.raw_p_value,
        BH_P_VALUE_NAME: result.bh_p_value,
        SEGMENT_SUPPORT_NAME: result.segment_support,
        SIGNIFICANT_ID: np.asarray(result.significant, dtype=np.uint8),
        **{array_id: getattr(result, field) for array_id, field in _STORED_FIELDS},
    }


def _checked(array_id: str, source: np.ndarray, dtype: str, shape: tuple[int, ...]) -> np.ndarray:
    values = np.asarray(source)
    if values.dtype.name != dtype or values.shape != shape:
        _fail(f"F17 array {array_id} has wrong dtype or shape")
    return values


def _fill(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Записать declared persistence fill 0.0 только под явной validity mask.

    Отсутствие всегда несёт mask, а числовое значение — никогда: подмена без mask
    была бы fabrication, поэтому two-sided invariant проверяется до преобразования.
    """
    if (
        values.shape != mask.shape
        or not np.all(np.isfinite(values[mask]))
        or not np.all(np.isnan(values[~mask]))
    ):
        _fail("F17 engine mask invariant is inconsistent")
    persisted = np.zeros_like(values)
    persisted[mask] = values[mask]
    return persisted


def _store(  # noqa: PLR0913, PLR0917 - единый типизированный приёмник массивов
    arrays: dict[str, np.ndarray],
    references: list[ArrayReference],
    array_id: str,
    role: str,
    unit: Unit,
    values: np.ndarray,
    domain_mask: str | None,
    *,
    partial: bool,
) -> None:
    validate_unit_name(array_id, unit)
    mask_id = expected_mask_id(array_id, domain_mask, partial=partial)
    if mask_id is not None and mask_id not in arrays:
        arrays[mask_id] = np.ones(values.shape, dtype=np.uint8)
    arrays[array_id] = values
    references.append(
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


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
