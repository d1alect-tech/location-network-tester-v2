"""F14: инварианты опубликованной записи и пустых unavailable-доменов."""

from __future__ import annotations

from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f14_contract import (
    BASELINE_PROBABILITY_NAME,
    DECLARED_CODES,
    EVENT_PROBABILITY_NAME,
    MEAN_WAVEFORM_NAME,
    NEAREST_LAG_NAME,
)
from lnt.characterization.records import Status, Unit, validate_unit_name

_DIRECTION_COUNT: Final = 2
_BASELINE_NDIM: Final = 2
type Float64Array = NDArray[np.float64]


class _Direction(Protocol):
    """Структурный контракт одного направления без импорта result-модуля."""

    @property
    def trigger_channel(self) -> str: ...

    @property
    def response_channel(self) -> str: ...

    @property
    def total_event_count(self) -> int: ...

    @property
    def qualified_trigger_count(self) -> int: ...

    @property
    def stored_trigger_count(self) -> int: ...

    @property
    def omitted_trigger_count(self) -> int: ...

    @property
    def boundary_trigger_count(self) -> int: ...

    @property
    def gap_crossing_trigger_count(self) -> int: ...

    @property
    def window_truncated_count(self) -> int: ...

    @property
    def mean_waveform_v(self) -> Float64Array: ...

    @property
    def event_probability(self) -> Float64Array: ...

    @property
    def nearest_lag_s(self) -> Float64Array: ...

    @property
    def baseline_probability(self) -> Float64Array: ...

    @property
    def baseline_low(self) -> Float64Array: ...

    @property
    def baseline_high(self) -> Float64Array: ...


class _Result(Protocol):
    """Структурный контракт F14-записи для fail-closed validation."""

    @property
    def status(self) -> Status: ...

    @property
    def reason_codes(self) -> tuple[str, ...]: ...

    @property
    def relative_time_s(self) -> Float64Array: ...

    @property
    def directions(self) -> tuple[_Direction, _Direction]: ...

    @property
    def sample_count(self) -> int: ...

    @property
    def qualified_cycle_count(self) -> int: ...


def validate_f14_result(result: _Result) -> None:
    """Проверить коды, единицы, направления, счётчики и числовые домены."""
    if any(code not in DECLARED_CODES for code in result.reason_codes):
        _fail("reason code is outside the F14 vocabulary")
    if result.reason_codes != tuple(sorted(set(result.reason_codes))):
        _fail("reason codes must be sorted and unique")
    if result.status is Status.AVAILABLE and result.reason_codes:
        _fail("available F14 result must not have reasons")
    if result.status is not Status.AVAILABLE and not result.reason_codes:
        _fail("non-available F14 result needs reasons")
    validate_unit_name(MEAN_WAVEFORM_NAME, Unit.V)
    validate_unit_name(EVENT_PROBABILITY_NAME, Unit.RATIO)
    validate_unit_name(NEAREST_LAG_NAME, Unit.S)
    validate_unit_name(BASELINE_PROBABILITY_NAME, Unit.RATIO)
    if result.sample_count < 0 or result.qualified_cycle_count < 0:
        _fail("F14 support counts must be nonnegative")
    if len(result.directions) != _DIRECTION_COUNT:
        _fail("F14 requires two directional results")
    expected = (("ch1", "ch2"), ("ch2", "ch1"))
    actual = tuple((item.trigger_channel, item.response_channel) for item in result.directions)
    if actual != expected:
        _fail("F14 direction order is not canonical")
    if result.status is Status.UNAVAILABLE:
        _validate_unavailable(result)
        return
    _validate_built(result)


def _validate_unavailable(result: _Result) -> None:
    """UNAVAILABLE публикует пустые домены, сохраняя только честный учёт."""
    if result.relative_time_s.size != 0 or result.qualified_cycle_count != 0:
        _fail("unavailable F14 result must use empty domains")
    for direction in result.directions:
        if (
            direction.total_event_count < 0
            or direction.qualified_trigger_count < 0
            or direction.stored_trigger_count < 0
            or direction.omitted_trigger_count < 0
            or direction.boundary_trigger_count < 0
            or direction.gap_crossing_trigger_count < 0
            or direction.window_truncated_count < 0
            or direction.total_event_count < direction.qualified_trigger_count
            or direction.stored_trigger_count > direction.qualified_trigger_count
            or direction.mean_waveform_v.size != 0
            or direction.event_probability.size != 0
            or direction.nearest_lag_s.size != 0
            or direction.baseline_probability.size != 0
            or direction.baseline_low.size != 0
            or direction.baseline_high.size != 0
        ):
            _fail("unavailable F14 direction must use empty domains")


def _validate_built(result: _Result) -> None:
    """Проверить общую сетку, два среза и вероятностные границы baseline."""
    axis = np.asarray(result.relative_time_s, dtype=np.float64)
    if (
        axis.ndim != 1
        or axis.size == 0
        or axis.size % 2 == 0
        or not np.all(np.isfinite(axis))
        or bool(np.any(np.diff(axis) <= 0.0))
        or not bool(np.any(axis == 0.0))
    ):
        _fail("F14 relative-time axis is invalid")
    for direction in result.directions:
        _validate_direction(direction, axis.size)


def _validate_direction(direction: _Direction, bins: int) -> None:
    """Проверить счётчики направления и все его числовые массивы."""
    counts = (
        direction.total_event_count,
        direction.qualified_trigger_count,
        direction.stored_trigger_count,
        direction.omitted_trigger_count,
        direction.boundary_trigger_count,
        direction.gap_crossing_trigger_count,
        direction.window_truncated_count,
    )
    if (
        any(count < 0 for count in counts)
        or direction.stored_trigger_count > direction.qualified_trigger_count
        or direction.qualified_trigger_count > direction.total_event_count
        or direction.omitted_trigger_count
        != direction.qualified_trigger_count - direction.stored_trigger_count
        or direction.stored_trigger_count <= 0
    ):
        _fail("F14 direction accounting is inconsistent")
    if (
        direction.mean_waveform_v.shape != (bins,)
        or direction.event_probability.shape != (bins,)
        or direction.baseline_low.shape != (bins,)
        or direction.baseline_high.shape != (bins,)
        or direction.baseline_probability.ndim != _BASELINE_NDIM
        or direction.baseline_probability.shape[1] != bins
        or direction.baseline_probability.shape[0] == 0
        or direction.nearest_lag_s.ndim != 1
        or not np.all(np.isfinite(direction.mean_waveform_v))
        or not np.all(np.isfinite(direction.event_probability))
        or not np.all(np.isfinite(direction.baseline_probability))
        or not np.all(np.isfinite(direction.baseline_low))
        or not np.all(np.isfinite(direction.baseline_high))
        or not np.all(np.isfinite(direction.nearest_lag_s))
    ):
        _fail("F14 direction arrays do not share their declared domains")
    if (
        np.any(direction.event_probability < 0.0)
        or np.any(direction.event_probability > 1.0)
        or np.any(direction.baseline_probability < 0.0)
        or np.any(direction.baseline_probability > 1.0)
        or np.any(direction.baseline_low < 0.0)
        or np.any(direction.baseline_high < 0.0)
        or np.any(direction.baseline_low > 1.0)
        or np.any(direction.baseline_high > 1.0)
        or not np.allclose(
            direction.baseline_low,
            np.min(direction.baseline_probability, axis=0),
            rtol=0.0,
            atol=1e-12,
        )
        or not np.allclose(
            direction.baseline_high,
            np.max(direction.baseline_probability, axis=0),
            rtol=0.0,
            atol=1e-12,
        )
    ):
        _fail("F14 probability domains are invalid")


def _fail(detail: str) -> None:
    """Единая доменная ошибка публикуемой записи F14."""
    raise CharacterizationError("status_invariant", detail)
