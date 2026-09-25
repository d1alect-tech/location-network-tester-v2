"""F12: finite arrays, validity masks и восстановление engine-результата."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f12_contract import (
    ADJUSTED_P_VALUE_NAME,
    F12_ID,
    FRAME_COUNT_NAME,
    FREQUENCY_AXIS_NAME,
    MAXIMUM_SPECTRAL_KURTOSIS_NAME,
    METHOD,
    MINIMUM_FRAMES,
    SCALE_INDEX_NAME,
    SEGMENT_SAMPLES,
    SELECTED_BAND_HIGH_NAME,
    SELECTED_BAND_LOW_NAME,
    SPECTRAL_KURTOSIS_NAME,
    SURROGATE_SUPPORT_NAME,
    WINDOW_SUPPORT_NAME,
)
from lnt.characterization.f12_result import F12Declarations, F12Result
from lnt.characterization.f12_tables import KURTOSIS_TABLE_ID, kurtosis_metadata
from lnt.characterization.f12_validation import validate_f12_result
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Status, Unit, validate_unit_name

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization.models import FamilyResult
    from lnt.characterization.tables import TableBlock

__all__ = ["checked_cap_order", "checked_scale_domain", "decode_f12_result", "published"]

type Entry = tuple[str, str, str, str, Unit, str | None, bool]

SEGMENT_ID: Final = "f12_segment_samples"
AVAILABLE_ID: Final = "f12_scale_available"
SK_MASK: Final = f"{SPECTRAL_KURTOSIS_NAME}_valid"
P_MASK: Final = f"{ADJUSTED_P_VALUE_NAME}_valid"
SELECTED_SCALE_ID: Final = "f12_selected_scale_index"
# Объявленный конечный заполнитель на границе персистенции: ячейка вне маски
# несёт ровно 0.0. Отсутствие несёт mask, никогда значение.
FILLER: Final = 0.0
_METHOD_VERSION: Final = 1
_BAND: Final = (SELECTED_BAND_LOW_NAME, SELECTED_BAND_HIGH_NAME, SELECTED_SCALE_ID)
# id, engine field, role, dtype name, unit, domain mask, scale-domain флаг.
_ENTRIES: Final[tuple[Entry, ...]] = (
    (SEGMENT_ID, "segment_samples", "declared_segment_scale", "int64", Unit.COUNT, None, True),
    (FRAME_COUNT_NAME, "frame_count", "scale_frame_count", "int64", Unit.COUNT, None, True),
    (AVAILABLE_ID, "scale_available", "scale_availability", "uint8", Unit.COUNT, None, True),
    (FREQUENCY_AXIS_NAME, "frequencies_hz", "bin_frequency", "float64", Unit.HZ, None, False),
    (SCALE_INDEX_NAME, "scale_index", "bin_scale", "int64", Unit.COUNT, None, False),
    (SPECTRAL_KURTOSIS_NAME, "spectral_kurtosis", "sk_bin", "float64", Unit.RATIO, SK_MASK, False),
    (ADJUSTED_P_VALUE_NAME, "adjusted_p_value", "p_bin", "float64", Unit.RATIO, P_MASK, False),
)


def published(
    result: F12Result, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Проверить locked geometry и опубликовать finite arrays с масками."""
    arrays: dict[str, np.ndarray] = {}
    references: list[ArrayReference] = []
    stored = result.stored_significant_bin_count
    for array_id, field, role, dtype, unit, mask_id, scale in _ENTRIES:
        values = np.asarray(getattr(result, field)).astype(dtype, copy=False)
        if values.shape != _shape(scale=scale, stored=stored):
            _fail(f"F12 array {array_id} has wrong shape")
        if mask_id is not None:
            values, mask = _persist_measurement(values)
            arrays[mask_id] = mask
        effective = mask_id or (f"{array_id}_valid" if partial else None)
        if effective is not None and effective not in arrays:
            arrays[effective] = np.ones(values.shape, dtype=np.uint8)
        validate_unit_name(array_id, unit)
        arrays[array_id] = values
        references.append(
            ArrayReference(
                array_id=array_id,
                role=role,
                unit=unit,
                dtype=values.dtype.name,
                shape=tuple(int(size) for size in values.shape),
                validity_mask_id=effective,
                offsets_id=None,
            )
        )
    return arrays, references


def decode_f12_result(
    family: FamilyResult,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> F12Result:
    """Проверить persisted finite form и вернуть engine-форму под масками."""
    declarations = F12Declarations.locked()
    if (
        family.family_id != F12_ID
        or family.method != METHOD
        or family.method_version != _METHOD_VERSION
        or family.status is Status.UNAVAILABLE
        or tuple(reference.table_id for reference in family.table_refs) != (KURTOSIS_TABLE_ID,)
        or tables.get(KURTOSIS_TABLE_ID) != kurtosis_metadata(declarations)
    ):
        _fail("F12 persisted identity or metadata is not locked")
    stored = _summary_count(family, "f12_stored_significant_bin_count")
    values = _persisted_values(family, arrays, stored, partial=family.status is Status.PARTIAL)
    if not np.array_equal(values[SEGMENT_ID], np.asarray(SEGMENT_SAMPLES, dtype=np.int64)):
        _fail("F12 frozen segment axis drifted from the declared recipe")
    sample = _summary_count(family, "f12_sample_count")
    qualified = int(family.support.observation_count)
    if (
        _summary_count(family, "f12_qualified_sample_count") != qualified
        or family.support.sample_count != sample
        or family.support.missing_count != sample - qualified
        or family.support.stored_count != qualified
        or family.support.selection_rule != "all"
    ):
        _fail("F12 persisted support accounting is inconsistent")
    significant = _summary_count(family, "f12_significant_bin_count")
    scale, low, high = _band(family, significant)
    restored = F12Result(
        status=family.status,
        reason_codes=family.reason_codes,
        segment_samples=values[SEGMENT_ID],
        frame_count=values[FRAME_COUNT_NAME],
        scale_available=np.asarray(values[AVAILABLE_ID], dtype=np.bool_),
        frequencies_hz=values[FREQUENCY_AXIS_NAME],
        scale_index=values[SCALE_INDEX_NAME],
        spectral_kurtosis=_restore(SPECTRAL_KURTOSIS_NAME, values, SK_MASK),
        adjusted_p_value=_restore(ADJUSTED_P_VALUE_NAME, values, P_MASK),
        maximum_spectral_kurtosis=_summary(family, MAXIMUM_SPECTRAL_KURTOSIS_NAME),
        selected_scale_index=scale,
        selected_band_low_hz=low,
        selected_band_high_hz=high,
        sample_count=sample,
        qualified_sample_count=qualified,
        analyzed_scale_count=_summary_count(family, WINDOW_SUPPORT_NAME),
        candidate_count=_summary_count(family, "f12_candidate_count"),
        significant_bin_count=significant,
        stored_significant_bin_count=stored,
        surrogate_count=_summary_count(family, SURROGATE_SUPPORT_NAME),
    )
    checked_scale_domain(restored)
    checked_cap_order(restored)
    validate_f12_result(restored)
    return restored


def _persist_measurement(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Перенести явное отсутствие движка в declared fill плюс uint8 mask."""
    # f12_math.antoni_from_moments публикует NaN для нулевого second moment, но
    # f12_candidates отбрасывает такие ячейки до домена результата, поэтому
    # declared mask сейчас единичен. Конвертация всё равно принадлежит мапперу,
    # а не кодеку: отсутствие несёт mask, никогда значение.
    mask = np.isfinite(values)
    persisted = np.zeros(values.shape, dtype=np.float64)
    persisted[mask] = values[mask]
    return persisted, mask.astype(np.uint8)


def _restore(array_id: str, values: Mapping[str, np.ndarray], mask_id: str) -> np.ndarray:
    """Проверить двусторонний инвариант в персистентной форме и вернуть NaN."""
    value = values[array_id]
    mask = values.get(mask_id)
    if mask is None:
        _fail("F12 persisted measurement mask is missing")
    valid = np.asarray(mask, dtype=np.bool_)
    if not np.all(np.isfinite(value)) or not np.all(value[~valid] == FILLER):
        _fail("F12 persisted measurement violates zero-under-mask invariant")
    restored = np.full(value.shape, np.nan, dtype=np.float64)
    restored[valid] = value[valid]
    return restored


def _persisted_values(
    family: FamilyResult, arrays: Mapping[str, np.ndarray], stored: int, *, partial: bool
) -> dict[str, np.ndarray]:
    if tuple(item.array_id for item in family.array_refs) != tuple(e[0] for e in _ENTRIES):
        _fail("F12 persisted array references are not canonical")
    values: dict[str, np.ndarray] = {}
    for index, (array_id, _, _, dtype, _, domain_mask, scale) in enumerate(_ENTRIES):
        value = arrays.get(array_id)
        shape = _shape(scale=scale, stored=stored)
        if value is None or value.dtype.name != dtype or value.shape != shape:
            _fail(f"F12 persisted array {array_id} has wrong dtype or shape")
        if not np.all(np.isfinite(value)):
            _fail(f"F12 persisted array {array_id} is nonfinite")
        expected = domain_mask or (f"{array_id}_valid" if partial else None)
        if family.array_refs[index].validity_mask_id != expected:
            _fail("F12 persisted validity reference is not canonical")
        if expected is not None:
            mask = arrays.get(expected)
            if mask is None or mask.dtype != np.dtype(np.uint8) or mask.shape != value.shape:
                _fail("F12 persisted validity mask has wrong dtype or shape")
            if domain_mask is None and not np.all(mask == 1):
                _fail("F12 structural mask must remain fully valid")
            values[expected] = mask
        values[array_id] = value
    return values


def checked_scale_domain(result: F12Result) -> None:
    """Bundle строже движка: недоступная scale не набирает minimum_frames."""
    if bool(np.any(~result.scale_available & (result.frame_count >= MINIMUM_FRAMES))):
        _fail("F12 unavailable scale claims declared minimum frame support")


def checked_cap_order(result: F12Result) -> None:
    """Проверить CAP_STORAGE_CONVENTION: maximum первым, дальше полоса и порядок."""
    # Cap ограничивает COUNT, а не объявленный RANGE полосы: маппер ничего не
    # отбрасывает и не переставляет, поэтому сохранённый домен остаётся в
    # объявленном порядке выживания. Это единственное место, где cap может
    # незаметно переставить сохранённый домен, поэтому проверка локальна.
    if int(result.spectral_kurtosis.size) == 0:
        return
    selected, low, high = (
        result.selected_scale_index,
        result.selected_band_low_hz,
        result.selected_band_high_hz,
    )
    if selected is None or low is None or high is None:
        _fail("F12 stored domain lost its selected band")
    scale = np.asarray(result.scale_index)
    frequencies = np.asarray(result.frequencies_hz)
    in_band = (scale == selected) & (frequencies >= low)
    in_band &= frequencies <= high
    step_scale = np.diff(scale[1:])
    ascending = (step_scale > 0) | ((step_scale == 0) & (np.diff(frequencies[1:]) > 0.0))
    outside = np.flatnonzero(~in_band[1:])
    if (
        float(result.spectral_kurtosis[0]) != result.maximum_spectral_kurtosis
        or not bool(in_band[0])
        or not bool(np.all(ascending))
        or bool(outside.size > 0 and np.any(in_band[1 + int(outside[0]) :]))
    ):
        _fail("F12 cap storage order is not canonical")


def _band(family: FamilyResult, significant: int) -> tuple[int | None, float | None, float | None]:
    """Вернуть явное отсутствие полосы вместо выдуманного нулевого края."""
    values = {item.name: item.value for item in family.comparison_summary}
    present = tuple(name in values for name in _BAND)
    if significant == 0:
        if any(present):
            _fail("F12 selected band is published without a significant bin")
        return (None, None, None)
    if not all(present):
        _fail("F12 selected band is missing for a significant result")
    scale = values[SELECTED_SCALE_ID]
    if not scale.is_integer():
        _fail("F12 selected band accounting is invalid")
    return (int(scale), values[SELECTED_BAND_LOW_NAME], values[SELECTED_BAND_HIGH_NAME])


def _summary(family: FamilyResult, name: str) -> float:
    value = {item.name: item.value for item in family.comparison_summary}.get(name)
    if value is None or not math.isfinite(value):
        _fail("F12 persisted comparison summary is invalid")
    return value


def _summary_count(family: FamilyResult, name: str) -> int:
    value = _summary(family, name)
    if value < 0 or not value.is_integer():
        _fail("F12 persisted accounting summary is invalid")
    return int(value)


def _shape(*, scale: bool, stored: int) -> tuple[int, ...]:
    return (len(SEGMENT_SAMPLES),) if scale else (stored,)


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
