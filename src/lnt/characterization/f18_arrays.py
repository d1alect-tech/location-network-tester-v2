"""F18: finite arrays, validity masks и strict reconstruction."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_contract import (
    ADJUSTED_P_NAME,
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    DUAL_P_NAME,
    F18_ID,
    FRAME_SUPPORT_NAME,
    IAAFT_P_NAME,
    METHOD,
    PHASE_RANDOMIZED_P_NAME,
    TRIAD_HIGH_NAME,
    TRIAD_LOW_NAME,
    TRIAD_SUM_NAME,
)
from lnt.characterization.f18_result import F18Declarations, F18Result
from lnt.characterization.f18_tables import (
    BIPHASE_MASK,
    F18_METADATA_TABLE_ID,
    SIGNIFICANT_NAME,
    TRIAD_AVAILABLE_NAME,
    F18ArrayEntry,
    bicoherence_metadata,
    locked_axes,
)
from lnt.characterization.f18_tables import (
    F18_ARRAY_ENTRIES as _ENTRIES,
)
from lnt.characterization.f18_validation import validate_f18_result
from lnt.characterization.models import ArrayReference, TableReference
from lnt.characterization.records import Status, validate_unit_name

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

# Canonical array schema is imported under its private local name.


def published(
    result: F18Result, declarations: F18Declarations, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Опубликовать finite arrays с явными masks без изменения engine domain."""
    validate_f18_result(result)
    _check_axes(result, declarations)
    shape = (result.declared_triad_count,)
    values = _values(result)
    arrays: dict[str, np.ndarray] = {}
    references: list[ArrayReference] = []
    for entry in _ENTRIES:
        array_id, _, _, dtype_name, domain_mask = entry
        checked = _checked(array_id, values[array_id], dtype_name, shape, domain_mask)
        if domain_mask is not None:
            mask = result.significant if array_id == BIPHASE_NAME else result.triad_available
            checked = _persist_measurement(checked, mask)
            arrays[domain_mask] = np.asarray(mask, dtype=np.uint8)
        _store(arrays, references, entry, checked, partial=partial)
    return arrays, references


def decode_f18_arrays(
    family: FamilyResult,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
    declared_count: int,
    dropped_count: int,
) -> dict[str, np.ndarray]:
    """Восстановить engine-форму из finite persisted arrays и явных масок."""
    declarations = F18Declarations.locked()
    shape = (declared_count,)
    if (
        family.family_id != F18_ID
        or family.method != METHOD
        or family.method_version != 1
        or family.status not in (Status.AVAILABLE, Status.PARTIAL)
        or family.table_refs
        != (TableReference(table_id=F18_METADATA_TABLE_ID, role="bicoherence_metadata"),)
        or set(tables) != {F18_METADATA_TABLE_ID}
        or tables.get(F18_METADATA_TABLE_ID) != bicoherence_metadata(declarations)
    ):
        _fail("F18 persisted identity or metadata is not locked")
    references = _references(family.status, shape)
    if family.array_refs != tuple(references):
        _fail("F18 persisted array references are not canonical")
    expected_members = {reference.array_id for reference in references} | {
        reference.validity_mask_id
        for reference in references
        if reference.validity_mask_id is not None
    }
    if set(arrays) != expected_members:
        _fail("F18 persisted array members are not canonical")
    values: dict[str, np.ndarray] = {}
    for index, entry in enumerate(_ENTRIES):
        # Entry itself carries id, dtype, and semantic mask.
        values[entry[0]] = _persisted_entry(
            arrays, entry, shape, references[index].validity_mask_id
        )
    expected_axis, expected_dropped = locked_axes(declarations)
    actual_axes = np.column_stack(
        (values[TRIAD_LOW_NAME], values[TRIAD_HIGH_NAME], values[TRIAD_SUM_NAME])
    )
    if (
        not np.array_equal(actual_axes, expected_axis)
        or declared_count != expected_axis.shape[0]
        or dropped_count != expected_dropped
    ):
        _fail("F18 persisted triad axes or count-cap accounting differ from declarations")
    available = np.asarray(values[TRIAD_AVAILABLE_NAME], dtype=np.bool_)
    significant = np.asarray(values[SIGNIFICANT_NAME], dtype=np.bool_)
    restored: dict[str, np.ndarray] = {}
    for array_id, mask_id in (
        (BICOHERENCE_NAME, TRIAD_AVAILABLE_NAME),
        (BIPHASE_NAME, BIPHASE_MASK),
        (PHASE_RANDOMIZED_P_NAME, TRIAD_AVAILABLE_NAME),
        (IAAFT_P_NAME, TRIAD_AVAILABLE_NAME),
        (DUAL_P_NAME, TRIAD_AVAILABLE_NAME),
        (ADJUSTED_P_NAME, TRIAD_AVAILABLE_NAME),
    ):
        restored[array_id], _ = _restore(
            values[array_id], np.asarray(arrays[mask_id], dtype=np.bool_)
        )
    restored.update(
        {
            TRIAD_LOW_NAME: values[TRIAD_LOW_NAME].copy(),
            TRIAD_HIGH_NAME: values[TRIAD_HIGH_NAME].copy(),
            TRIAD_SUM_NAME: values[TRIAD_SUM_NAME].copy(),
            FRAME_SUPPORT_NAME: values[FRAME_SUPPORT_NAME].copy(),
            TRIAD_AVAILABLE_NAME: available,
            SIGNIFICANT_NAME: significant,
        }
    )
    return restored


def _values(result: F18Result) -> dict[str, np.ndarray]:
    return {
        TRIAD_LOW_NAME: result.triad_low_hz,
        TRIAD_HIGH_NAME: result.triad_high_hz,
        TRIAD_SUM_NAME: result.triad_sum_hz,
        BICOHERENCE_NAME: result.bicoherence_squared,
        BIPHASE_NAME: result.biphase_rad,
        PHASE_RANDOMIZED_P_NAME: result.phase_randomized_p_value,
        IAAFT_P_NAME: result.iaaft_p_value,
        DUAL_P_NAME: result.dual_null_p_value,
        ADJUSTED_P_NAME: result.adjusted_p_value,
        TRIAD_AVAILABLE_NAME: result.triad_available,
        SIGNIFICANT_NAME: result.significant,
        FRAME_SUPPORT_NAME: result.frame_support,
    }


def _check_axes(result: F18Result, declarations: F18Declarations) -> None:
    expected, dropped = locked_axes(declarations)
    actual = np.column_stack((result.triad_low_hz, result.triad_high_hz, result.triad_sum_hz))
    if (
        actual.shape != expected.shape
        or not np.array_equal(actual, expected)
        or result.declared_triad_count != expected.shape[0]
        or result.dropped_triad_count != dropped
    ):
        _fail("F18 triad axes or count-cap accounting differ from declarations")


def _checked(
    array_id: str,
    source: np.ndarray,
    dtype_name: str,
    shape: tuple[int, ...],
    domain_mask: str | None,
) -> np.ndarray:
    values = np.asarray(source)
    if values.dtype == np.dtype(np.bool_) and dtype_name == "uint8":
        values = values.astype(np.uint8)
    if values.dtype != np.dtype(dtype_name) or values.shape != shape:
        _fail(f"F18 array {array_id} has wrong dtype or shape")
    if domain_mask is None and not bool(np.all(np.isfinite(values))):
        _fail(f"F18 array {array_id} is nonfinite")
    return values


def _persist_measurement(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    valid = np.asarray(mask, dtype=np.bool_)
    if (
        values.shape != valid.shape
        or not np.all(np.isfinite(values[valid]))
        or not np.all(np.isnan(values[~valid]))
    ):
        _fail("F18 engine mask invariant is inconsistent")
    persisted = np.zeros(values.shape, dtype=np.float64)
    persisted[valid] = values[valid]
    return persisted


def _store(
    arrays: dict[str, np.ndarray],
    references: list[ArrayReference],
    entry: F18ArrayEntry,
    values: np.ndarray,
    *,
    partial: bool,
) -> None:
    array_id, _role, unit, _, domain_mask = entry
    validate_unit_name(array_id, unit)
    mask_id = domain_mask
    if partial and mask_id is None:
        mask_id = f"{array_id}_valid"
    if mask_id is not None and mask_id not in arrays:
        arrays[mask_id] = np.ones(values.shape, dtype=np.uint8)
    arrays[array_id] = values
    references.append(_reference(entry, values.shape, mask_id))


def _references(status: Status, shape: tuple[int, ...]) -> list[ArrayReference]:
    partial = status is Status.PARTIAL
    return [
        _reference(
            entry,
            shape,
            entry[4] if entry[4] is not None or not partial else f"{entry[0]}_valid",
        )
        for entry in _ENTRIES
    ]


def _reference(entry: F18ArrayEntry, shape: tuple[int, ...], mask_id: str | None) -> ArrayReference:
    array_id, role, unit, dtype_name, _ = entry
    return ArrayReference(
        array_id=array_id,
        role=role,
        unit=unit,
        dtype=dtype_name,
        shape=shape,
        validity_mask_id=mask_id,
        offsets_id=None,
    )


def _persisted_entry(
    arrays: Mapping[str, np.ndarray],
    entry: F18ArrayEntry,
    shape: tuple[int, ...],
    mask_id: str | None,
) -> np.ndarray:
    array_id, _, _, dtype_name, domain_mask = entry
    value = arrays[array_id]
    if (
        value.dtype != np.dtype(dtype_name)
        or value.shape != shape
        or not bool(np.all(np.isfinite(value)))
    ):
        _fail(f"F18 persisted array {array_id} has wrong dtype, shape, or finite values")
    if mask_id is not None:
        mask = arrays[mask_id]
        if (
            mask.dtype != np.dtype(np.uint8)
            or mask.shape != shape
            or not bool(np.all((mask == 0) | (mask == 1)))
            or (domain_mask is None and not bool(np.all(mask == 1)))
        ):
            _fail("F18 persisted validity mask is not canonical")
    return value


def _restore(values: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if not np.all(np.isfinite(values)) or not np.all(values[~mask] == 0.0):
        _fail("F18 persisted measurement violates zero-under-mask invariant")
    restored = np.full(values.shape, np.nan, dtype=np.float64)
    restored[mask] = values[mask]
    return restored, mask


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
