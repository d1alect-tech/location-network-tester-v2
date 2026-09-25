"""F16: finite-domain arrays, validity masks и восстановление результата."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f16_contract import (
    AUTOCORRELATION_NAME,
    COUNT_MEAN_NAME,
    COUNT_VARIANCE_NAME,
    F16_ID,
    FANO_FACTOR_NAME,
    METHOD,
    RECURRENCE_RATE_NAME,
)
from lnt.characterization.f16_result import F16Declarations, F16Result
from lnt.characterization.f16_tables import MEMORY_TABLE_ID, memory_metadata
from lnt.characterization.f16_validation import validate_f16_result
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Status, Unit, validate_unit_name

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

type Entry = tuple[str, str, Unit, str | None]

LAG_MASK: Final = "f16_lag_valid"
RECURRENCE_MASK: Final = "f16_recurrence_rate_valid"
COUNT_MASK: Final = "f16_count_window_valid"
FANO_MASK: Final = "f16_fano_factor_valid"
_INTEGER_IDS: Final = frozenset({"f16_pair_count", "f16_count_window_count"})
_ENTRIES: Final[tuple[Entry, ...]] = (
    ("f16_lag_s", "lag_axis", Unit.S, None),
    (AUTOCORRELATION_NAME, "normalized_autocorrelation", Unit.RATIO, LAG_MASK),
    ("f16_pair_count", "lag_pair_count", Unit.COUNT, None),
    ("f16_recurrence_radius_mad", "recurrence_radius_axis", Unit.RATIO, None),
    (RECURRENCE_RATE_NAME, "recurrence_rate", Unit.RATIO, RECURRENCE_MASK),
    ("f16_count_window_s", "count_window_axis", Unit.S, None),
    ("f16_count_window_count", "complete_count_window_count", Unit.COUNT, None),
    (COUNT_MEAN_NAME, "count_mean", Unit.COUNT, COUNT_MASK),
    (COUNT_VARIANCE_NAME, "count_variance", Unit.RATIO, COUNT_MASK),
    (FANO_FACTOR_NAME, "fano_factor", Unit.RATIO, FANO_MASK),
)


def published(
    result: F16Result, declarations: F16Declarations, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Проверить engine-контракт и опубликовать finite arrays с масками."""
    validate_f16_result(result)
    values = _values(result)
    arrays: dict[str, np.ndarray] = {}
    references: list[ArrayReference] = []
    for array_id, role, unit, mask_id in _ENTRIES:
        checked = _checked(array_id, values[array_id], declarations)
        if mask_id is not None:
            mask = _measurement_mask(result, array_id)
            checked = _persist_measurement(checked, mask)
            arrays[mask_id] = mask.astype(np.uint8)
        _store(arrays, references, array_id, role, unit, checked, mask_id, partial=partial)
    return arrays, references


def decode_f16_result(
    family: FamilyResult,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> F16Result:
    """Проверить persisted finite form и вернуть engine-форму с NaN под mask."""
    declarations = F16Declarations.locked()
    if (
        family.family_id != F16_ID
        or family.method != METHOD
        or family.method_version != 1
        or family.status is Status.UNAVAILABLE
        or tuple(reference.table_id for reference in family.table_refs) != (MEMORY_TABLE_ID,)
        or tables.get(MEMORY_TABLE_ID) != memory_metadata(declarations)
    ):
        _fail("F16 persisted identity or metadata is not locked")
    values = _persisted_values(family, arrays, declarations)
    autocorrelation, lag_available = _restore(AUTOCORRELATION_NAME, values, LAG_MASK)
    recurrence_rate, recurrence_available = _restore(RECURRENCE_RATE_NAME, values, RECURRENCE_MASK)
    count_mean, count_available = _restore(COUNT_MEAN_NAME, values, COUNT_MASK)
    count_variance, _ = _restore(COUNT_VARIANCE_NAME, values, COUNT_MASK)
    fano_factor, fano_available = _restore(FANO_FACTOR_NAME, values, FANO_MASK)
    sample = _summary_count(family, "f16_sample_count")
    qualified = int(family.support.observation_count)
    qualified_summary = _summary_count(family, "f16_qualified_sample_count")
    if (
        qualified_summary != qualified
        or family.support.sample_count != sample
        or family.support.missing_count != sample - qualified
        or family.support.stored_count != qualified
        or family.support.selection_rule != "all"
    ):
        _fail("F16 persisted support accounting is inconsistent")
    restored = F16Result(
        status=family.status,
        reason_codes=family.reason_codes,
        lag_s=values["f16_lag_s"],
        autocorrelation=autocorrelation,
        pair_count=values["f16_pair_count"],
        lag_available=lag_available,
        recurrence_radius_mad=values["f16_recurrence_radius_mad"],
        recurrence_rate=recurrence_rate,
        count_window_s=values["f16_count_window_s"],
        count_window_count=values["f16_count_window_count"],
        count_mean=count_mean,
        count_variance=count_variance,
        fano_factor=fano_factor,
        count_window_available=count_available,
        fano_available=fano_available,
        sample_count=sample,
        qualified_sample_count=qualified,
        analyzed_segment_count=_summary_count(family, "f16_analyzed_segment_count"),
        event_count=_summary_count(family, "f16_event_count"),
    )
    if not np.array_equal(recurrence_available, np.repeat(lag_available[:, None], 3, axis=1)):
        _fail("F16 persisted recurrence mask differs from lag support")
    validate_f16_result(restored)
    return restored


def _values(result: F16Result) -> dict[str, np.ndarray]:
    return {
        "f16_lag_s": result.lag_s,
        AUTOCORRELATION_NAME: result.autocorrelation,
        "f16_pair_count": result.pair_count,
        "f16_recurrence_radius_mad": result.recurrence_radius_mad,
        RECURRENCE_RATE_NAME: result.recurrence_rate,
        "f16_count_window_s": result.count_window_s,
        "f16_count_window_count": result.count_window_count,
        COUNT_MEAN_NAME: result.count_mean,
        COUNT_VARIANCE_NAME: result.count_variance,
        FANO_FACTOR_NAME: result.fano_factor,
    }


def _checked(array_id: str, source: np.ndarray, declarations: F16Declarations) -> np.ndarray:
    values = np.asarray(source, dtype=np.int64 if array_id in _INTEGER_IDS else np.float64)
    if values.shape != _shape(array_id, declarations):
        _fail(f"F16 array {array_id} has wrong shape")
    return values


def _shape(array_id: str, declarations: F16Declarations) -> tuple[int, ...]:
    if array_id in {"f16_lag_s", AUTOCORRELATION_NAME, "f16_pair_count"}:
        return (len(declarations.lags_s),)
    if array_id == "f16_recurrence_radius_mad":
        return (len(declarations.recurrence_radius_mad),)
    if array_id == RECURRENCE_RATE_NAME:
        return (len(declarations.lags_s), len(declarations.recurrence_radius_mad))
    return (len(declarations.count_windows_s),)


def _measurement_mask(result: F16Result, array_id: str) -> np.ndarray:
    if array_id == AUTOCORRELATION_NAME:
        return np.asarray(result.lag_available, dtype=np.bool_)
    if array_id == RECURRENCE_RATE_NAME:
        return np.repeat(
            np.asarray(result.lag_available, dtype=np.bool_)[:, None],
            result.recurrence_radius_mad.size,
            axis=1,
        )
    if array_id in {COUNT_MEAN_NAME, COUNT_VARIANCE_NAME}:
        return np.asarray(result.count_window_available, dtype=np.bool_)
    return np.asarray(result.fano_available, dtype=np.bool_)


def _persist_measurement(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Записать declared persistence fill 0.0 только под явной validity mask.

    Отсутствие всегда несёт mask, а числовое значение — никогда. Подмена без mask
    или потеря mask была бы fabrication, поэтому shape и two-sided invariant
    проверяются до преобразования.
    """
    if (
        values.shape != mask.shape
        or not np.all(np.isfinite(values[mask]))
        or not np.all(np.isnan(values[~mask]))
    ):
        _fail("F16 engine mask invariant is inconsistent")
    persisted = np.zeros_like(values, dtype=np.float64)
    persisted[mask] = values[mask]
    return persisted


def _store(  # noqa: PLR0913, PLR0917 - единый типизированный приёмник массивов
    arrays: dict[str, np.ndarray],
    references: list[ArrayReference],
    array_id: str,
    role: str,
    unit: Unit,
    values: np.ndarray,
    mask_id: str | None,
    *,
    partial: bool,
) -> None:
    validate_unit_name(array_id, unit)
    effective_mask = mask_id
    if partial and effective_mask is None:
        effective_mask = f"{array_id}_valid"
    if effective_mask is not None and effective_mask not in arrays:
        arrays[effective_mask] = np.ones(values.shape, dtype=np.uint8)
    arrays[array_id] = values
    references.append(
        ArrayReference(
            array_id=array_id,
            role=role,
            unit=unit,
            dtype=values.dtype.name,
            shape=tuple(int(size) for size in values.shape),
            validity_mask_id=effective_mask,
            offsets_id=None,
        )
    )


def _persisted_values(
    family: FamilyResult, arrays: Mapping[str, np.ndarray], declarations: F16Declarations
) -> dict[str, np.ndarray]:
    if tuple(reference.array_id for reference in family.array_refs) != tuple(
        entry[0] for entry in _ENTRIES
    ):
        _fail("F16 persisted array references are not canonical")
    values: dict[str, np.ndarray] = {}
    for index, (array_id, _, _, domain_mask) in enumerate(_ENTRIES):
        dtype = np.dtype(np.int64 if array_id in _INTEGER_IDS else np.float64)
        value = arrays.get(array_id)
        if value is None or value.dtype != dtype or value.shape != _shape(array_id, declarations):
            _fail(f"F16 persisted array {array_id} has wrong dtype or shape")
        if not np.all(np.isfinite(value)):
            _fail(f"F16 persisted array {array_id} is nonfinite")
        values[array_id] = value
        reference = family.array_refs[index]
        expected_mask = domain_mask
        if expected_mask is None and family.status is Status.PARTIAL:
            expected_mask = f"{array_id}_valid"
        if reference.validity_mask_id != expected_mask:
            _fail("F16 persisted validity reference is not canonical")
        if expected_mask is not None:
            mask = arrays.get(expected_mask)
            if mask is None or mask.dtype != np.dtype(np.uint8) or mask.shape != value.shape:
                _fail("F16 persisted validity mask has wrong dtype or shape")
            if domain_mask is None and not np.all(mask == 1):
                _fail("F16 structural mask must remain fully valid")
            values[expected_mask] = mask
    return values


def _restore(
    array_id: str, values: Mapping[str, np.ndarray], mask_id: str
) -> tuple[np.ndarray, np.ndarray]:
    value = values[array_id]
    mask = values.get(mask_id)
    if mask is None:
        _fail("F16 persisted measurement mask is missing")
    valid = np.asarray(mask, dtype=np.bool_)
    if not np.all(np.isfinite(value)) or not np.all(value[~valid] == 0.0):
        _fail("F16 persisted measurement violates zero-under-mask invariant")
    restored = np.full(value.shape, np.nan, dtype=np.float64)
    restored[valid] = value[valid]
    return restored, valid


def _summary_count(family: FamilyResult, name: str) -> int:
    values = {item.name: item.value for item in family.comparison_summary}
    if name not in values or values[name] < 0 or not float(values[name]).is_integer():
        _fail("F16 persisted accounting summary is invalid")
    return int(values[name])


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
