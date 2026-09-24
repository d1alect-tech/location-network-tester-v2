"""F14: направленные массивы, ragged lag-вектор и маски области."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f14_contract import (
    BASELINE_PROBABILITY_NAME,
    EVENT_LIMIT,
    EVENT_PROBABILITY_NAME,
    MEAN_WAVEFORM_NAME,
    NEAREST_LAG_NAME,
)
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Unit, validate_unit_name

if TYPE_CHECKING:
    from lnt.characterization.f14_result import F14Declarations, F14DirectionResult, F14Result

_DIRECTION_COUNT: Final = 2
_ENTRIES: Final = (
    ("f14_direction_index", "direction_index", Unit.COUNT),
    ("f14_relative_time_s", "relative_time_axis", Unit.S),
    ("f14_cycle_shift_offsets", "cycle_shift_offset_axis", Unit.COUNT),
    (MEAN_WAVEFORM_NAME, "direction_mean_waveform", Unit.V),
    (EVENT_PROBABILITY_NAME, "direction_event_probability", Unit.RATIO),
    (NEAREST_LAG_NAME, "direction_nearest_lag", Unit.S),
    (BASELINE_PROBABILITY_NAME, "direction_baseline_probability", Unit.RATIO),
    ("f14_baseline_low", "direction_baseline_low", Unit.RATIO),
    ("f14_baseline_high", "direction_baseline_high", Unit.RATIO),
)
_TOLERANCE: Final = 1e-12
_CANONICAL_DIRECTIONS: Final = (("ch1", "ch2"), ("ch2", "ch1"))


def validate_unavailable(result: F14Result, declarations: F14Declarations) -> None:
    """Проверить пустые домены UNAVAILABLE и честный trigger-учёт."""
    if (
        np.asarray(result.relative_time_s).shape != (0,)
        or not _is_count(result.qualified_cycle_count)
        or result.qualified_cycle_count != 0
        or len(result.directions) != _DIRECTION_COUNT
        or not _is_count(result.sample_count)
    ):
        _fail("unavailable F14 must use empty domains")
    actual = tuple(
        (direction.trigger_channel, direction.response_channel) for direction in result.directions
    )
    if actual != _CANONICAL_DIRECTIONS:
        _fail("F14 direction order is not canonical")
    for direction in result.directions:
        _validate_counts(direction, declarations, built=False)
        if (
            direction.stored_trigger_count != 0
            or direction.omitted_trigger_count != direction.qualified_trigger_count
            or np.asarray(direction.mean_waveform_v).shape != (0,)
            or np.asarray(direction.event_probability).shape != (0,)
            or np.asarray(direction.nearest_lag_s).shape != (0,)
            or np.asarray(direction.baseline_probability).shape != (0, 0)
            or np.asarray(direction.baseline_low).shape != (0,)
            or np.asarray(direction.baseline_high).shape != (0,)
        ):
            _fail("unavailable F14 must use empty domains")


def published(
    result: F14Result,
    declarations: F14Declarations,
    *,
    partial: bool,
    reason_codes: tuple[str, ...] = (),
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Проверить и упаковать два направления без изменения их границ."""
    _validate_built(result, declarations, reason_codes)
    values = _values(result, declarations)
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in _ENTRIES:
        checked = _checked(array_id, values[array_id], result, declarations)
        mask_id = f"{array_id}_valid" if partial or array_id == NEAREST_LAG_NAME else None
        _store(arrays, refs, (array_id, role, unit), checked, mask_id)
        if array_id == NEAREST_LAG_NAME:
            first = int(result.directions[0].nearest_lag_s.size)
            second = int(result.directions[1].nearest_lag_s.size)
            arrays["f14_nearest_lag_offsets"] = np.asarray(
                [0, first, first + second], dtype=np.int64
            )
    return arrays, refs


def _values(result: F14Result, declarations: F14Declarations) -> dict[str, np.ndarray]:
    first, second = result.directions
    return {
        "f14_direction_index": np.arange(_DIRECTION_COUNT, dtype=np.int64),
        "f14_relative_time_s": result.relative_time_s,
        "f14_cycle_shift_offsets": np.asarray(declarations.cycle_shift_offsets, dtype=np.int64),
        MEAN_WAVEFORM_NAME: np.stack((first.mean_waveform_v, second.mean_waveform_v)),
        EVENT_PROBABILITY_NAME: np.stack((first.event_probability, second.event_probability)),
        NEAREST_LAG_NAME: np.concatenate((first.nearest_lag_s, second.nearest_lag_s)),
        BASELINE_PROBABILITY_NAME: np.stack(
            (first.baseline_probability, second.baseline_probability)
        ),
        "f14_baseline_low": np.stack((first.baseline_low, second.baseline_low)),
        "f14_baseline_high": np.stack((first.baseline_high, second.baseline_high)),
    }


def _checked(
    array_id: str,
    source: np.ndarray,
    result: F14Result,
    declarations: F14Declarations,
) -> np.ndarray:
    unit = next(unit for name, _, unit in _ENTRIES if name == array_id)
    dtype = np.int64 if unit is Unit.COUNT else np.float64
    values = np.asarray(source, dtype=dtype)
    if values.shape != _shape(array_id, result, declarations):
        _fail(f"F14 array {array_id} has wrong shape")
    if not bool(np.all(np.isfinite(values))):
        _fail(f"F14 array {array_id} is nonfinite")
    return values


def _shape(array_id: str, result: F14Result, declarations: F14Declarations) -> tuple[int, ...]:
    bins = declarations.relative_time_bins
    if array_id == "f14_direction_index":
        shape = (_DIRECTION_COUNT,)
    elif array_id == "f14_relative_time_s":
        shape = (bins,)
    elif array_id == "f14_cycle_shift_offsets":
        shape = (len(declarations.cycle_shift_offsets),)
    elif array_id in {MEAN_WAVEFORM_NAME, EVENT_PROBABILITY_NAME}:
        shape = (_DIRECTION_COUNT, bins)
    elif array_id == NEAREST_LAG_NAME:
        shape = (sum(direction.nearest_lag_s.size for direction in result.directions),)
    elif array_id == BASELINE_PROBABILITY_NAME:
        shape = (_DIRECTION_COUNT, len(declarations.cycle_shift_offsets), bins)
    else:
        shape = (_DIRECTION_COUNT, bins)
    return shape


def _store(
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    entry: tuple[str, str, Unit],
    values: np.ndarray,
    mask_id: str | None,
) -> None:
    array_id, role, unit = entry
    offsets_id = "f14_nearest_lag_offsets" if array_id == NEAREST_LAG_NAME else None
    validate_unit_name(array_id, unit)
    if mask_id is not None:
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
            offsets_id=offsets_id,
        )
    )


def _validate_built(
    result: F14Result, declarations: F14Declarations, reason_codes: tuple[str, ...]
) -> None:
    axis = np.asarray(result.relative_time_s, dtype=np.float64)
    expected = np.linspace(
        declarations.trigger_window_low_s,
        declarations.trigger_window_high_s,
        declarations.relative_time_bins,
        dtype=np.float64,
    )
    if (
        axis.shape != expected.shape
        or not np.all(np.isfinite(axis))
        or not np.allclose(axis, expected, rtol=0.0, atol=_TOLERANCE)
        or len(result.directions) != _DIRECTION_COUNT
        or not _is_count(result.sample_count)
        or not _is_count(result.qualified_cycle_count)
        or result.qualified_cycle_count <= 0
        or result.sample_count < result.qualified_cycle_count
    ):
        _fail("F14 result does not match declared domains")
    actual = tuple(
        (direction.trigger_channel, direction.response_channel) for direction in result.directions
    )
    if actual != _CANONICAL_DIRECTIONS:
        _fail("F14 direction order is not canonical")
    for direction in result.directions:
        _validate_counts(direction, declarations, built=True)
        _validate_direction(direction, declarations)
    omitted = sum(direction.omitted_trigger_count for direction in result.directions)
    if (omitted > 0) != (EVENT_LIMIT in reason_codes):
        _fail("F14 event cap is not declared exactly")


def _validate_counts(
    direction: F14DirectionResult,
    declarations: F14Declarations,
    *,
    built: bool,
) -> None:
    counts: tuple[object, ...] = (
        direction.total_event_count,
        direction.qualified_trigger_count,
        direction.stored_trigger_count,
        direction.omitted_trigger_count,
        direction.boundary_trigger_count,
        direction.gap_crossing_trigger_count,
        direction.window_truncated_count,
    )
    if any(not _is_count(value) for value in counts):
        _fail("F14 trigger counts must be nonnegative integers")
    if (
        direction.qualified_trigger_count > direction.total_event_count
        or direction.stored_trigger_count > direction.qualified_trigger_count
        or direction.omitted_trigger_count
        != direction.qualified_trigger_count - direction.stored_trigger_count
        or direction.boundary_trigger_count
        + direction.gap_crossing_trigger_count
        + direction.window_truncated_count
        + direction.qualified_trigger_count
        != direction.total_event_count
        or (built and direction.stored_trigger_count < declarations.minimum_triggers)
        or direction.stored_trigger_count > declarations.maximum_triggers_per_direction
    ):
        _fail("F14 trigger accounting is inconsistent")


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_direction(direction: F14DirectionResult, declarations: F14Declarations) -> None:
    bins = declarations.relative_time_bins
    values = (
        np.asarray(direction.mean_waveform_v, dtype=np.float64),
        np.asarray(direction.event_probability, dtype=np.float64),
        np.asarray(direction.nearest_lag_s, dtype=np.float64),
        np.asarray(direction.baseline_probability, dtype=np.float64),
        np.asarray(direction.baseline_low, dtype=np.float64),
        np.asarray(direction.baseline_high, dtype=np.float64),
    )
    if (
        values[0].shape != (bins,)
        or values[1].shape != (bins,)
        or values[2].ndim != 1
        or values[3].shape != (len(declarations.cycle_shift_offsets), bins)
        or values[4].shape != (bins,)
        or values[5].shape != (bins,)
        or any(not bool(np.all(np.isfinite(item))) for item in values)
    ):
        _fail("F14 direction arrays do not share their declared domains")
    if (
        values[2].size > direction.stored_trigger_count
        or np.any(values[2] < declarations.nearest_event_lag_low_s)
        or np.any(values[2] > declarations.nearest_event_lag_high_s)
        or np.any(values[1] < 0.0)
        or np.any(values[1] > 1.0)
        or np.any(values[3] < 0.0)
        or np.any(values[3] > 1.0)
        or not np.allclose(values[4], np.min(values[3], axis=0), rtol=0.0, atol=_TOLERANCE)
        or not np.allclose(values[5], np.max(values[3], axis=0), rtol=0.0, atol=_TOLERANCE)
    ):
        _fail("F14 direction values violate their declared domains")


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
