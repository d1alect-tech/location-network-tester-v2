"""F17: восстановление engine-формы из persisted finite arrays и таблицы."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f17_arrays import (
    ARRAY_IDS,
    CELL_AVAILABLE_ID,
    COUNTER_FIELDS,
    ENTRIES,
    SIGNIFICANT_ID,
    STORED_ALPHA_ID,
    expected_mask_id,
    shape_for,
)
from lnt.characterization.f17_contract import (
    BH_P_VALUE_NAME,
    COHERENCE_NAME,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_SPECTRUM_NAME,
    F17_ID,
    FREQUENCY_NAME,
    METHOD,
    METHOD_VERSION,
    RAW_P_VALUE_NAME,
    SEGMENT_SUPPORT_NAME,
    F17Declarations,
)
from lnt.characterization.f17_result import F17Result
from lnt.characterization.f17_tables import COHERENCE_TABLE_ID, coherence_metadata
from lnt.characterization.f17_validation import validate_f17_result
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

__all__ = ["decode_f17_result"]

_COMPLEX_FILL: Final = np.nan + 1j * np.nan


def decode_f17_result(
    family: FamilyResult,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> F17Result:
    """Проверить persisted finite form и вернуть engine-форму с NaN под mask."""
    declarations = F17Declarations.locked()
    if (
        family.family_id != F17_ID
        or family.method != METHOD
        or family.method_version != METHOD_VERSION
        or family.status is Status.UNAVAILABLE
        or tuple(reference.table_id for reference in family.table_refs) != (COHERENCE_TABLE_ID,)
        or tables.get(COHERENCE_TABLE_ID) != coherence_metadata(declarations)
    ):
        _fail("F17 persisted identity or metadata is not locked")
    values = _persisted_values(family, arrays, declarations)
    counters = _counters(family)
    _accounting(family, values, counters)
    cell = np.asarray(values[CELL_AVAILABLE_ID], dtype=np.bool_)
    restored = F17Result(
        status=family.status,
        reason_codes=family.reason_codes,
        cyclic_frequencies_hz=values[CYCLIC_FREQUENCY_NAME],
        frequencies_hz=values[FREQUENCY_NAME],
        cyclic_spectrum=_restore(CYCLIC_SPECTRUM_NAME, values, cell, _COMPLEX_FILL),
        coherence=_restore(COHERENCE_NAME, values, cell, np.nan),
        raw_p_value=_restore(RAW_P_VALUE_NAME, values, cell, np.nan),
        bh_p_value=_restore(BH_P_VALUE_NAME, values, cell, np.nan),
        segment_support=values[SEGMENT_SUPPORT_NAME],
        cell_available=cell,
        significant=np.asarray(values[SIGNIFICANT_ID], dtype=np.bool_),
        stored_alpha_hz=values[STORED_ALPHA_ID],
        stored_frequency_hz=values["f17_stored_frequency_hz"],
        stored_cyclic_spectrum=values["f17_stored_cyclic_spectrum_v2"],
        stored_coherence=values["f17_stored_coherence"],
        stored_raw_p_value=values["f17_stored_raw_p_value"],
        stored_bh_p_value=values["f17_stored_bh_p_value"],
        stored_segment_support=values["f17_stored_segment_support"],
        sample_count=counters["sample_count"],
        qualified_sample_count=counters["qualified_sample_count"],
        qualified_cycle_count=counters["qualified_cycle_count"],
        frame_count=counters["frame_count"],
        tested_cell_count=counters["tested_cell_count"],
        significant_cell_count=counters["significant_cell_count"],
        stored_cell_count=counters["stored_cell_count"],
        omitted_cell_count=counters["omitted_cell_count"],
    )
    # Инвариант движка проверяется в его собственных терминах, на пересобранном результате.
    validate_f17_result(restored)
    return restored


def _persisted_values(
    family: FamilyResult, arrays: Mapping[str, np.ndarray], declarations: F17Declarations
) -> dict[str, np.ndarray]:
    if tuple(reference.array_id for reference in family.array_refs) != ARRAY_IDS:
        _fail("F17 persisted array references are not canonical")
    alpha_count = len(declarations.cyclic_frequencies_hz)
    frequency_count = _axis_size(arrays, FREQUENCY_NAME, empty=False)
    stored_count = _axis_size(arrays, STORED_ALPHA_ID, empty=True)
    partial = family.status is Status.PARTIAL
    values: dict[str, np.ndarray] = {}
    for index, (array_id, _, _, dtype, shape_key, domain_mask) in enumerate(ENTRIES):
        expected = shape_for(shape_key, alpha_count, frequency_count, stored_count)
        value = arrays.get(array_id)
        if value is None or value.dtype.name != dtype or value.shape != expected:
            _fail(f"F17 persisted array {array_id} has wrong dtype or shape")
        if not np.all(np.isfinite(value)):
            _fail(f"F17 persisted array {array_id} is nonfinite")
        values[array_id] = value
        mask_id = expected_mask_id(array_id, domain_mask, partial=partial)
        if family.array_refs[index].validity_mask_id != mask_id:
            _fail("F17 persisted validity reference is not canonical")
        if mask_id is not None:
            values[mask_id] = _mask(arrays, mask_id, expected, structural=domain_mask is None)
    return values


def _axis_size(arrays: Mapping[str, np.ndarray], array_id: str, *, empty: bool) -> int:
    value = arrays.get(array_id)
    if value is None or value.ndim != 1 or value.dtype != np.dtype(np.float64):
        _fail(f"F17 persisted array {array_id} has wrong dtype or shape")
    if not empty and not value.size:
        _fail(f"F17 persisted array {array_id} has wrong dtype or shape")
    return int(value.size)


def _mask(
    arrays: Mapping[str, np.ndarray], mask_id: str, shape: tuple[int, ...], *, structural: bool
) -> np.ndarray:
    mask = arrays.get(mask_id)
    if mask is None:
        _fail(f"F17 persisted validity mask {mask_id} is missing")
    if mask.dtype != np.dtype(np.uint8) or mask.shape != shape:
        _fail(f"F17 persisted validity mask {mask_id} has wrong dtype or shape")
    if not np.all((mask == 0) | (mask == 1)):
        _fail(f"F17 persisted validity mask {mask_id} is not boolean")
    if structural and not np.all(mask == 1):
        _fail("F17 structural mask must remain fully valid")
    return mask


def _restore(
    array_id: str, values: Mapping[str, np.ndarray], cell: np.ndarray, fill: complex
) -> np.ndarray:
    value = values[array_id]
    if value.shape != cell.shape or not np.all(np.isfinite(value)) or not np.all(value[~cell] == 0):
        _fail(f"F17 persisted {array_id} violates zero-under-mask invariant")
    restored = np.full(value.shape, fill, dtype=value.dtype)
    restored[cell] = value[cell]
    return restored


def _counters(family: FamilyResult) -> dict[str, int]:
    values = {item.name.removeprefix("f17_"): item.value for item in family.comparison_summary}
    if set(values) != set(COUNTER_FIELDS):
        _fail("F17 persisted accounting summary is incomplete")
    counters: dict[str, int] = {}
    for name in COUNTER_FIELDS:
        value = values[name]
        if value < 0 or not float(value).is_integer():
            _fail("F17 persisted accounting summary is invalid")
        counters[name] = int(value)
    return counters


def _accounting(
    family: FamilyResult, values: Mapping[str, np.ndarray], counters: dict[str, int]
) -> None:
    support = family.support
    sample = counters["sample_count"]
    qualified = counters["qualified_sample_count"]
    if (
        sample != support.sample_count
        or qualified != support.observation_count
        or support.missing_count != sample - qualified
        or support.stored_count != qualified
        or support.selection_rule != "all"
    ):
        _fail("F17 persisted support accounting is inconsistent")
    if int(values[STORED_ALPHA_ID].size) != counters["stored_cell_count"]:
        _fail("F17 persisted stored-cell accounting is inconsistent")


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
