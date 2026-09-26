"""F18: приведение finite arrays к канонической форме, маскам и ссылкам."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_contract import (
    ADJUSTED_P_NAME,
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    DUAL_P_NAME,
    FRAME_SUPPORT_NAME,
    IAAFT_P_NAME,
    PHASE_RANDOMIZED_P_NAME,
    TRIAD_HIGH_NAME,
    TRIAD_LOW_NAME,
    TRIAD_SUM_NAME,
)
from lnt.characterization.f18_tables import (
    F18_ARRAY_ENTRIES as _ENTRIES,
)
from lnt.characterization.f18_tables import (
    SIGNIFICANT_NAME,
    TRIAD_AVAILABLE_NAME,
    locked_axes,
)
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Status, validate_unit_name

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.f18_result import F18Declarations, F18Result
    from lnt.characterization.f18_tables import F18ArrayEntry


def f18_result_arrays(result: F18Result) -> dict[str, np.ndarray]:
    """Собрать 12 finite arrays результата по каноническим id."""
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


def check_f18_axes(result: F18Result, declarations: F18Declarations) -> None:
    """Сверить triad axes результата с объявленными и счётчиком cap."""
    expected, dropped = locked_axes(declarations)
    actual = np.column_stack((result.triad_low_hz, result.triad_high_hz, result.triad_sum_hz))
    if (
        actual.shape != expected.shape
        or not np.array_equal(actual, expected)
        or result.declared_triad_count != expected.shape[0]
        or result.dropped_triad_count != dropped
    ):
        fail_f18_invariant("F18 triad axes or count-cap accounting differ from declarations")


def checked_f18_array(
    array_id: str,
    source: np.ndarray,
    dtype_name: str,
    shape: tuple[int, ...],
    domain_mask: str | None,
) -> np.ndarray:
    """Привести array к persisted dtype и форме, проверив конечность."""
    values = np.asarray(source)
    if values.dtype == np.dtype(np.bool_) and dtype_name == "uint8":
        values = values.astype(np.uint8)
    if values.dtype != np.dtype(dtype_name) or values.shape != shape:
        fail_f18_invariant(f"F18 array {array_id} has wrong dtype or shape")
    if domain_mask is None and not bool(np.all(np.isfinite(values))):
        fail_f18_invariant(f"F18 array {array_id} is nonfinite")
    return values


def persist_f18_measurement(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Обнулить измерение вне mask, сохранив NaN-инвариант движка."""
    valid = np.asarray(mask, dtype=np.bool_)
    if (
        values.shape != valid.shape
        or not np.all(np.isfinite(values[valid]))
        or not np.all(np.isnan(values[~valid]))
    ):
        fail_f18_invariant("F18 engine mask invariant is inconsistent")
    persisted = np.zeros(values.shape, dtype=np.float64)
    persisted[valid] = values[valid]
    return persisted


def store_f18_array(
    arrays: dict[str, np.ndarray],
    references: list[ArrayReference],
    entry: F18ArrayEntry,
    values: np.ndarray,
    *,
    partial: bool,
) -> None:
    """Записать array и её validity mask, дополнив ссылки каноническим id."""
    array_id, _role, unit, _, domain_mask = entry
    validate_unit_name(array_id, unit)
    mask_id = domain_mask
    if partial and mask_id is None:
        mask_id = f"{array_id}_valid"
    if mask_id is not None and mask_id not in arrays:
        arrays[mask_id] = np.ones(values.shape, dtype=np.uint8)
    arrays[array_id] = values
    references.append(f18_array_reference(entry, values.shape, mask_id))


def f18_array_references(status: Status, shape: tuple[int, ...]) -> list[ArrayReference]:
    """Собрать канонические ссылки на persisted arrays для статуса."""
    partial = status is Status.PARTIAL
    return [
        f18_array_reference(
            entry,
            shape,
            entry[4] if entry[4] is not None or not partial else f"{entry[0]}_valid",
        )
        for entry in _ENTRIES
    ]


def f18_array_reference(
    entry: F18ArrayEntry, shape: tuple[int, ...], mask_id: str | None
) -> ArrayReference:
    """Собрать одну ссылку на array с её validity mask."""
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


def persisted_f18_entry(
    arrays: Mapping[str, np.ndarray],
    entry: F18ArrayEntry,
    shape: tuple[int, ...],
    mask_id: str | None,
) -> np.ndarray:
    """Проверить persisted array на dtype, форму, конечность и маску."""
    array_id, _, _, dtype_name, domain_mask = entry
    value = arrays[array_id]
    if (
        value.dtype != np.dtype(dtype_name)
        or value.shape != shape
        or not bool(np.all(np.isfinite(value)))
    ):
        fail_f18_invariant(
            f"F18 persisted array {array_id} has wrong dtype, shape, or finite values"
        )
    if mask_id is not None:
        mask = arrays[mask_id]
        if (
            mask.dtype != np.dtype(np.uint8)
            or mask.shape != shape
            or not bool(np.all((mask == 0) | (mask == 1)))
            or (domain_mask is None and not bool(np.all(mask == 1)))
        ):
            fail_f18_invariant("F18 persisted validity mask is not canonical")
    return value


def restore_f18_measurement(values: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Восстановить NaN-форму измерения из persisted нулей под mask."""
    if not np.all(np.isfinite(values)) or not np.all(values[~mask] == 0.0):
        fail_f18_invariant("F18 persisted measurement violates zero-under-mask invariant")
    restored = np.full(values.shape, np.nan, dtype=np.float64)
    restored[mask] = values[mask]
    return restored, mask


def fail_f18_invariant(detail: str) -> NoReturn:
    """Отклонить нарушение status_invariant в array-слое F18."""
    raise CharacterizationError("status_invariant", detail)
