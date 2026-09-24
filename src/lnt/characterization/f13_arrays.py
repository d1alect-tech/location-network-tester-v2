"""F13: оси, матрицы и проверка persisted array domain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NoReturn

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f13_math import PAIR_INDICES
from lnt.characterization.f13_result import (
    ACTIVITY_FRACTION_NAME,
    BAND_COUNT,
    PAIR_QUANTITY_NAMES,
    PAIR_QUANTITY_UNITS,
)
from lnt.characterization.models import ArrayReference
from lnt.characterization.records import Unit, validate_unit_name

if TYPE_CHECKING:
    from lnt.characterization.f13_result import F13Declarations, F13Result

BAND_METADATA_TABLE_ID: Final = "f13_band_metadata"
_ENTRIES: Final[tuple[tuple[str, str, Unit], ...]] = (
    ("f13_band_index", "band_index_axis", Unit.COUNT),
    ("f13_band_low_hz", "band_low_edges", Unit.HZ),
    ("f13_band_high_hz", "band_high_edges", Unit.HZ),
    ("f13_lag_s", "lag_axis", Unit.S),
    (ACTIVITY_FRACTION_NAME, "activity_fraction", Unit.RATIO),
    ("f13_active_sample_count", "active_sample_count", Unit.COUNT),
    (PAIR_QUANTITY_NAMES[0], "zero_lag_correlation", PAIR_QUANTITY_UNITS[0]),
    (PAIR_QUANTITY_NAMES[1], "coincidence_probability", PAIR_QUANTITY_UNITS[1]),
    (PAIR_QUANTITY_NAMES[2], "lift", PAIR_QUANTITY_UNITS[2]),
    (PAIR_QUANTITY_NAMES[3], "maximum_lag", PAIR_QUANTITY_UNITS[3]),
    (PAIR_QUANTITY_NAMES[4], "maximum_lag_correlation", PAIR_QUANTITY_UNITS[4]),
)
_TOLERANCE: Final = 1e-12


def validate_unavailable(result: F13Result, declarations: F13Declarations) -> None:
    """Проверить пустые домены UNAVAILABLE, не превращая их в нули."""
    _bands(result, declarations)
    sample_count = _count(result.sample_count, "sample_count")
    qualified = _count(result.qualified_sample_count, "qualified_sample_count")
    if (
        sample_count < 0
        or qualified != 0
        or result.activity_fraction.size != 0
        or result.active_sample_count.size != 0
        or result.lag_s.size != 0
        or any(
            values.size != 0
            for values in (
                result.zero_lag_correlation,
                result.coincidence_probability,
                result.lift,
                result.maximum_lag_s,
                result.maximum_lag_correlation,
            )
        )
    ):
        _fail("unavailable F13 must use explicit empty domains")


def published(
    result: F13Result, declarations: F13Declarations, *, partial: bool
) -> tuple[dict[str, np.ndarray], list[ArrayReference]]:
    """Проверить и упаковать все F13 arrays с масками только для PARTIAL."""
    _validate_built(result, declarations)
    values = _values(result)
    arrays: dict[str, np.ndarray] = {}
    refs: list[ArrayReference] = []
    for array_id, role, unit in _ENTRIES:
        checked = _checked(array_id, values[array_id])
        _store(arrays, refs, array_id, role, unit, checked, partial=partial)
    return arrays, refs


def _values(result: F13Result) -> dict[str, np.ndarray]:
    return {
        "f13_band_index": np.arange(BAND_COUNT, dtype=np.int64),
        "f13_band_low_hz": np.asarray([pair[0] for pair in result.bands_hz], dtype=np.float64),
        "f13_band_high_hz": np.asarray([pair[1] for pair in result.bands_hz], dtype=np.float64),
        "f13_lag_s": result.lag_s,
        ACTIVITY_FRACTION_NAME: result.activity_fraction,
        "f13_active_sample_count": result.active_sample_count,
        PAIR_QUANTITY_NAMES[0]: result.zero_lag_correlation,
        PAIR_QUANTITY_NAMES[1]: result.coincidence_probability,
        PAIR_QUANTITY_NAMES[2]: result.lift,
        PAIR_QUANTITY_NAMES[3]: result.maximum_lag_s,
        PAIR_QUANTITY_NAMES[4]: result.maximum_lag_correlation,
    }


def _checked(array_id: str, source: np.ndarray) -> np.ndarray:
    unit = next(unit for name, _, unit in _ENTRIES if name == array_id)
    dtype = np.int64 if unit is Unit.COUNT else np.float64
    values = np.asarray(source, dtype=dtype)
    expected = _shape(array_id, values)
    if values.shape != expected:
        _fail(f"F13 array {array_id} has wrong shape")
    if not bool(np.all(np.isfinite(values))):
        _fail(f"F13 array {array_id} is nonfinite")
    return values


def _shape(array_id: str, values: np.ndarray) -> tuple[int, ...]:
    if array_id in {"f13_band_index", "f13_band_low_hz", "f13_band_high_hz"}:
        return (BAND_COUNT,)
    if array_id in {ACTIVITY_FRACTION_NAME, "f13_active_sample_count"}:
        return (BAND_COUNT,)
    if array_id == "f13_lag_s":
        return (values.size,)
    return (BAND_COUNT, BAND_COUNT)


def _store(  # noqa: PLR0913, PLR0917 — единый приёмник типизированных массивов
    arrays: dict[str, np.ndarray],
    refs: list[ArrayReference],
    array_id: str,
    role: str,
    unit: Unit,
    values: np.ndarray,
    *,
    partial: bool,
) -> None:
    validate_unit_name(array_id, unit)
    mask_id = f"{array_id}_valid" if partial else None
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
            offsets_id=None,
        )
    )


def _validate_built(result: F13Result, declarations: F13Declarations) -> None:
    _bands(result, declarations)
    sample_count = _count(result.sample_count, "sample_count")
    qualified = _count(result.qualified_sample_count, "qualified_sample_count")
    if sample_count < 0 or qualified <= 0 or sample_count < qualified:
        _fail("F13 sample accounting is inconsistent")
    lag = np.asarray(result.lag_s, dtype=np.float64)
    _lag_grid(lag, declarations)
    activity = np.asarray(result.activity_fraction, dtype=np.float64)
    counts = np.asarray(result.active_sample_count)
    if (
        activity.shape != (BAND_COUNT,)
        or counts.shape != (BAND_COUNT,)
        or not np.issubdtype(counts.dtype, np.integer)
        or not np.all(np.isfinite(activity))
        or np.any(activity < 0.0)
        or np.any(activity > 1.0)
        or np.any(counts < 0)
        or np.any(counts > qualified)
        or np.any(counts < declarations.minimum_active_samples)
    ):
        _fail("F13 activity accounting is inconsistent")
    if not np.allclose(
        activity,
        np.asarray(counts, dtype=np.float64) / qualified,
        rtol=0.0,
        atol=_TOLERANCE,
    ):
        _fail("F13 activity accounting is inconsistent")
    _matrices(result, activity, lag)


def _lag_grid(lag: np.ndarray, declarations: F13Declarations) -> None:
    if (
        lag.ndim != 1
        or lag.size == 0
        or lag.size > declarations.maximum_lag_points
        or not np.all(np.isfinite(lag))
        or bool(np.any(np.diff(lag) <= 0.0))
        or not bool(np.any(lag == 0.0))
        or not np.allclose(lag, -lag[::-1], rtol=0.0, atol=_TOLERANCE)
        or bool(np.any(lag < declarations.lag_low_s - _TOLERANCE))
        or bool(np.any(lag > declarations.lag_high_s + _TOLERANCE))
    ):
        _fail("F13 materialised lag grid contradicts declarations")


def _matrices(result: F13Result, activity: np.ndarray, lag: np.ndarray) -> None:
    values = (
        result.zero_lag_correlation,
        result.coincidence_probability,
        result.lift,
        result.maximum_lag_s,
        result.maximum_lag_correlation,
    )
    if any(np.asarray(value).shape != (BAND_COUNT, BAND_COUNT) for value in values):
        _fail("F13 pair matrices must have declared shape")
    zero, coincidence, lift, maximum_lag, maximum_correlation = (
        np.asarray(value, dtype=np.float64) for value in values
    )
    if any(
        not np.all(np.isfinite(value))
        for value in (zero, coincidence, lift, maximum_lag, maximum_correlation)
    ):
        _fail("F13 pair matrices must be finite")
    if any(
        not np.allclose(value, value.T, rtol=0.0, atol=_TOLERANCE)
        for value in (zero, coincidence, lift, maximum_lag, maximum_correlation)
    ):
        _fail("F13 pair matrices must be symmetric")
    if (
        np.any(np.abs(zero) > 1.0)
        or np.any(np.abs(maximum_correlation) > 1.0)
        or np.any(coincidence < 0.0)
        or np.any(coincidence > 1.0)
        or np.any(lift < 0.0)
        or not np.allclose(np.diag(zero), 1.0, rtol=0.0, atol=_TOLERANCE)
        or not np.allclose(np.diag(coincidence), activity, rtol=0.0, atol=_TOLERANCE)
        or not np.allclose(np.diag(lift), 1.0, rtol=0.0, atol=_TOLERANCE)
        or not np.allclose(np.diag(maximum_lag), 0.0, rtol=0.0, atol=_TOLERANCE)
        or not np.allclose(np.diag(maximum_correlation), 1.0, rtol=0.0, atol=_TOLERANCE)
        or not np.all(np.isin(maximum_lag, lag))
    ):
        _fail("F13 pair values violate their declared domains")
    expected_lift = np.eye(BAND_COUNT, dtype=np.float64)
    for first, second in PAIR_INDICES:
        probability = coincidence[first, second]
        if (
            probability > activity[first] + _TOLERANCE
            or probability > activity[second] + _TOLERANCE
        ):
            _fail("F13 coincidence accounting is inconsistent")
        expected_lift[first, second] = expected_lift[second, first] = probability / (
            activity[first] * activity[second]
        )
    if not np.allclose(lift, expected_lift, rtol=0.0, atol=_TOLERANCE):
        _fail("F13 lift accounting is inconsistent")


def _bands(result: F13Result, declarations: F13Declarations) -> None:
    expected_names = tuple(f"band_{index:04d}" for index in range(1, BAND_COUNT + 1))
    try:
        pairs = tuple((float(pair[0]), float(pair[1])) for pair in result.bands_hz)
        names = tuple(result.band_names)
    except (IndexError, TypeError, ValueError):
        _fail("F13 band axis is malformed")
    declared = tuple((float(pair[0]), float(pair[1])) for pair in declarations.bands_hz)
    if names != expected_names or pairs != declared:
        _fail("F13 band axis does not follow shared resolver")


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"F13 {name} must be an integer")
    return value


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
