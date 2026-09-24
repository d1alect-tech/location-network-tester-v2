"""F16: инварианты fixed axes, masked absence и unavailable-результата."""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f16_contract import (
    AUTOCORRELATION_NAME,
    COUNT_MEAN_NAME,
    COUNT_VARIANCE_NAME,
    COUNT_WINDOWS_S,
    DECLARED_CODES,
    FANO_FACTOR_NAME,
    INSUFFICIENT_COUNT_WINDOWS,
    INSUFFICIENT_PAIRS,
    LAG_ABOVE_SUPPORT,
    LAGS_S,
    MINIMUM_COUNT_WINDOWS,
    MINIMUM_PAIRS,
    RECURRENCE_RADIUS_MAD,
    RECURRENCE_RATE_NAME,
    ZERO_EVENT_RATE,
)
from lnt.characterization.records import Status, Unit, validate_unit_name

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]


class _Result(Protocol):
    """Structural read contract без runtime import result-модуля."""

    @property
    def status(self) -> Status: ...

    @property
    def reason_codes(self) -> tuple[str, ...]: ...

    @property
    def lag_s(self) -> Float64Array: ...

    @property
    def autocorrelation(self) -> Float64Array: ...

    @property
    def pair_count(self) -> Int64Array: ...

    @property
    def lag_available(self) -> BoolArray: ...

    @property
    def recurrence_radius_mad(self) -> Float64Array: ...

    @property
    def recurrence_rate(self) -> Float64Array: ...

    @property
    def count_window_s(self) -> Float64Array: ...

    @property
    def count_window_count(self) -> Int64Array: ...

    @property
    def count_mean(self) -> Float64Array: ...

    @property
    def count_variance(self) -> Float64Array: ...

    @property
    def fano_factor(self) -> Float64Array: ...

    @property
    def count_window_available(self) -> BoolArray: ...

    @property
    def fano_available(self) -> BoolArray: ...

    @property
    def sample_count(self) -> int: ...

    @property
    def qualified_sample_count(self) -> int: ...

    @property
    def analyzed_segment_count(self) -> int: ...

    @property
    def event_count(self) -> int: ...


def validate_f16_result(result: _Result) -> None:
    """Проверить closed vocabulary, геометрию, support и masked absence."""
    _validate_codes(result)
    _validate_units()
    if (
        result.sample_count < 0
        or not 0 <= result.qualified_sample_count <= result.sample_count
        or result.analyzed_segment_count < 0
        or result.analyzed_segment_count > result.qualified_sample_count
        or result.event_count < 0
    ):
        _fail("F16 support counts are inconsistent")
    if result.status is Status.UNAVAILABLE:
        _validate_unavailable(result)
        return
    _validate_built(result)


def _validate_codes(result: _Result) -> None:
    """AVAILABLE не имеет причин; PARTIAL и UNAVAILABLE имеют причины."""
    if any(code not in DECLARED_CODES for code in result.reason_codes):
        _fail("reason code is outside the F16 vocabulary")
    if result.reason_codes != tuple(sorted(set(result.reason_codes))):
        _fail("reason codes must be sorted and unique")
    if result.status is Status.AVAILABLE and result.reason_codes:
        _fail("available F16 result must not have reasons")
    if result.status is not Status.AVAILABLE and not result.reason_codes:
        _fail("non-available F16 result needs reasons")


def _validate_units() -> None:
    """Проверить persisted quantity names через closed unit vocabulary."""
    for name, unit in (
        (AUTOCORRELATION_NAME, Unit.RATIO),
        (RECURRENCE_RATE_NAME, Unit.RATIO),
        (COUNT_MEAN_NAME, Unit.COUNT),
        (COUNT_VARIANCE_NAME, Unit.RATIO),
        (FANO_FACTOR_NAME, Unit.RATIO),
    ):
        validate_unit_name(name, unit)


def _arrays(result: _Result) -> tuple[np.ndarray, ...]:
    return (
        result.lag_s,
        result.autocorrelation,
        result.pair_count,
        result.lag_available,
        result.recurrence_radius_mad,
        result.recurrence_rate,
        result.count_window_s,
        result.count_window_count,
        result.count_mean,
        result.count_variance,
        result.fano_factor,
        result.count_window_available,
        result.fano_available,
    )


def _validate_unavailable(result: _Result) -> None:
    """UNAVAILABLE публикует пустые domains, сохраняя только внешний support."""
    if any(array.size != 0 for array in _arrays(result)):
        _fail("unavailable F16 result must use empty domains")
    if result.qualified_sample_count != 0 or result.analyzed_segment_count != 0:
        _fail("unavailable F16 result must not claim analyzed support")


def _validate_built(result: _Result) -> None:
    """Проверить fixed axes, pair/window support и явные validity masks."""
    lag_shape = (len(LAGS_S),)
    radius_shape = (len(RECURRENCE_RADIUS_MAD),)
    window_shape = (len(COUNT_WINDOWS_S),)
    if (
        result.sample_count <= 0
        or result.lag_s.shape != lag_shape
        or result.autocorrelation.shape != lag_shape
        or result.pair_count.shape != lag_shape
        or result.lag_available.shape != lag_shape
        or result.recurrence_radius_mad.shape != radius_shape
        or result.recurrence_rate.shape != (lag_shape[0], radius_shape[0])
        or result.count_window_s.shape != window_shape
        or result.count_window_count.shape != window_shape
        or result.count_mean.shape != window_shape
        or result.count_variance.shape != window_shape
        or result.fano_factor.shape != window_shape
        or result.count_window_available.shape != window_shape
        or result.fano_available.shape != window_shape
    ):
        _fail("F16 arrays do not share their fixed domains")
    if not (
        np.array_equal(result.lag_s, np.asarray(LAGS_S))
        and np.array_equal(result.recurrence_radius_mad, RECURRENCE_RADIUS_MAD)
        and np.array_equal(result.count_window_s, COUNT_WINDOWS_S)
    ):
        _fail("F16 axes differ from the locked recipe")
    if np.any(result.pair_count < 0) or np.any(result.count_window_count < 0):
        _fail("F16 support counts must be nonnegative")
    if not np.array_equal(result.lag_available, result.pair_count >= MINIMUM_PAIRS):
        _fail("F16 lag availability differs from minimum_pairs")
    if not np.array_equal(
        result.count_window_available, result.count_window_count >= MINIMUM_COUNT_WINDOWS
    ):
        _fail("F16 count-window availability differs from minimum_count_windows")
    _validate_masked_values(result)
    _validate_scale_reasons(result)


def _validate_masked_values(result: _Result) -> None:
    """Unavailable cells хранят NaN mask; available cells хранят finite values."""
    if not _masked_finite(result.autocorrelation, result.lag_available):
        _fail("F16 autocorrelation validity mask is inconsistent")
    row_valid = np.repeat(result.lag_available[:, None], result.recurrence_rate.shape[1], axis=1)
    if not _masked_finite(result.recurrence_rate, row_valid):
        _fail("F16 recurrence validity mask is inconsistent")
    if np.any(result.recurrence_rate[row_valid] < 0.0) or np.any(
        result.recurrence_rate[row_valid] > 1.0
    ):
        _fail("F16 recurrence rate must stay in [0, 1]")
    for values in (result.count_mean, result.count_variance):
        if not _masked_finite(values, result.count_window_available):
            _fail("F16 count summary validity mask is inconsistent")
    if not _masked_finite(result.fano_factor, result.fano_available):
        _fail("F16 Fano validity mask is inconsistent")
    if np.any(result.count_variance[result.count_window_available] < 0.0) or np.any(
        result.fano_factor[result.fano_available] < 0.0
    ):
        _fail("F16 variance and Fano factor must be nonnegative")
    expected_fano = result.count_window_available & (result.count_mean > 0.0)
    if not np.array_equal(result.fano_available, expected_fano):
        _fail("F16 Fano validity must follow positive event rate")


def _validate_scale_reasons(result: _Result) -> None:
    """Sparse scale support must use exact declared reason vocabulary."""
    required: set[str] = set()
    if bool(np.any(result.pair_count == 0)):
        required.add(LAG_ABOVE_SUPPORT)
    if bool(np.any((result.pair_count > 0) & (result.pair_count < MINIMUM_PAIRS))):
        required.add(INSUFFICIENT_PAIRS)
    if bool(np.any(result.count_window_count < MINIMUM_COUNT_WINDOWS)):
        required.add(INSUFFICIENT_COUNT_WINDOWS)
    if bool(np.any(result.count_window_available & (result.count_mean == 0.0))):
        required.add(ZERO_EVENT_RATE)
    if not required.issubset(result.reason_codes):
        _fail("F16 scale support lacks its declared reason code")


def _masked_finite(values: np.ndarray, mask: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(values[mask])) and np.all(np.isnan(values[~mask])))


def _fail(detail: str) -> None:
    raise CharacterizationError("status_invariant", detail)
