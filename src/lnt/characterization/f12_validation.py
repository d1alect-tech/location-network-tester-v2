"""F12: инварианты scale domains, significant cap и unavailable-результата."""

from __future__ import annotations

import math
from typing import NoReturn, Protocol

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f12_contract import (
    ARTIFACT_LIMIT,
    CLIPPED,
    DECLARED_CODES,
    INSUFFICIENT_FRAMES,
    MAXIMUM_STORED_BINS,
    MINIMUM_FRAMES,
    NO_SIGNIFICANT_BIN,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_UNSUPPORTED,
    SEGMENT_SAMPLES,
    SURROGATE_COUNT,
    ZERO_POWER,
)
from lnt.characterization.f12_units import validate_f12_units
from lnt.characterization.records import Status

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
    def segment_samples(self) -> Int64Array: ...

    @property
    def frame_count(self) -> Int64Array: ...

    @property
    def scale_available(self) -> BoolArray: ...

    @property
    def frequencies_hz(self) -> Float64Array: ...

    @property
    def scale_index(self) -> Int64Array: ...

    @property
    def spectral_kurtosis(self) -> Float64Array: ...

    @property
    def adjusted_p_value(self) -> Float64Array: ...

    @property
    def maximum_spectral_kurtosis(self) -> float | None: ...

    @property
    def selected_scale_index(self) -> int | None: ...

    @property
    def selected_band_low_hz(self) -> float | None: ...

    @property
    def selected_band_high_hz(self) -> float | None: ...

    @property
    def sample_count(self) -> int: ...

    @property
    def qualified_sample_count(self) -> int: ...

    @property
    def analyzed_scale_count(self) -> int: ...

    @property
    def candidate_count(self) -> int: ...

    @property
    def significant_bin_count(self) -> int: ...

    @property
    def stored_significant_bin_count(self) -> int: ...

    @property
    def surrogate_count(self) -> int: ...


def validate_f12_result(result: _Result) -> None:
    """Проверить closed vocabulary, geometry, support и explicit absence."""
    _validate_codes(result)
    validate_f12_units()
    if result.sample_count < 0 or not 0 <= result.qualified_sample_count <= result.sample_count:
        _fail("F12 sample support is inconsistent")
    if result.status is Status.UNAVAILABLE:
        _validate_unavailable(result)
    else:
        _validate_built(result)


def _validate_codes(result: _Result) -> None:
    if any(code not in DECLARED_CODES for code in result.reason_codes):
        _fail("reason code is outside the F12 vocabulary")
    if result.reason_codes != tuple(sorted(set(result.reason_codes))):
        _fail("F12 reason codes must be sorted and unique")
    if result.status is Status.AVAILABLE and result.reason_codes:
        _fail("available F12 result must not have reasons")
    if result.status is not Status.AVAILABLE and not result.reason_codes:
        _fail("non-available F12 result needs reasons")


def _arrays(result: _Result) -> tuple[NDArray[np.generic], ...]:
    return (
        result.segment_samples,
        result.frame_count,
        result.scale_available,
        result.frequencies_hz,
        result.scale_index,
        result.spectral_kurtosis,
        result.adjusted_p_value,
    )


def _validate_unavailable(result: _Result) -> None:
    if any(array.size != 0 for array in _arrays(result)):
        _fail("unavailable F12 result must use empty domains")
    if (
        result.maximum_spectral_kurtosis is not None
        or result.selected_scale_index is not None
        or result.selected_band_low_hz is not None
        or result.selected_band_high_hz is not None
    ):
        _fail("unavailable F12 result must not publish selected measurements")
    if (
        result.qualified_sample_count != 0
        or result.analyzed_scale_count != 0
        or result.candidate_count != 0
        or result.significant_bin_count != 0
        or result.stored_significant_bin_count != 0
        or result.surrogate_count != 0
    ):
        _fail("unavailable F12 result must not claim analyzed support")


def _validate_built(result: _Result) -> None:
    shape = (len(SEGMENT_SAMPLES),)
    measured = result.frequencies_hz.shape
    counts = (
        result.candidate_count,
        result.significant_bin_count,
        result.stored_significant_bin_count,
    )
    if (
        result.segment_samples.shape != shape
        or result.frame_count.shape != shape
        or result.scale_available.shape != shape
        or not np.array_equal(result.segment_samples, SEGMENT_SAMPLES)
        or result.frequencies_hz.ndim != 1
        or result.scale_index.shape != measured
        or result.spectral_kurtosis.shape != measured
        or result.adjusted_p_value.shape != measured
        or result.stored_significant_bin_count != result.spectral_kurtosis.size
        or any(value < 0 for value in counts)
        or result.candidate_count < 1
        or not (
            result.candidate_count
            >= result.significant_bin_count
            >= result.stored_significant_bin_count
        )
        or result.stored_significant_bin_count > MAXIMUM_STORED_BINS
        or result.stored_significant_bin_count
        != min(result.significant_bin_count, MAXIMUM_STORED_BINS)
    ):
        _fail("F12 arrays or bounded counts are inconsistent")
    _validate_support(result)
    _validate_measurements(result)
    _validate_reasons(result)


def _validate_support(result: _Result) -> None:
    available_count = int(np.count_nonzero(result.scale_available))
    if (
        result.sample_count <= 0
        or result.qualified_sample_count <= 0
        or not 1 <= available_count <= len(SEGMENT_SAMPLES)
        or result.analyzed_scale_count != available_count
        or result.surrogate_count != SURROGATE_COUNT
        or np.any(result.frame_count < 0)
        or bool(np.any(result.scale_available & (result.frame_count < MINIMUM_FRAMES)))
    ):
        _fail("F12 scale, window, or surrogate support is inconsistent")


def _validate_measurements(result: _Result) -> None:
    values = (result.frequencies_hz, result.spectral_kurtosis, result.adjusted_p_value)
    if any(not np.all(np.isfinite(value)) for value in values):
        _fail("F12 published measurements must be finite")
    if (
        np.any(result.frequencies_hz <= 0.0)
        or np.any((result.adjusted_p_value <= 0.0) | (result.adjusted_p_value > 1.0))
        or np.any((result.scale_index < 0) | (result.scale_index >= len(SEGMENT_SAMPLES)))
    ):
        _fail("F12 frequency, probability, or scale domain is invalid")
    if result.maximum_spectral_kurtosis is None or not math.isfinite(
        result.maximum_spectral_kurtosis
    ):
        _fail("built F12 result must publish finite observed maximum")
    _validate_selection(result)


def _validate_selection(result: _Result) -> None:
    selected = (
        result.selected_scale_index,
        result.selected_band_low_hz,
        result.selected_band_high_hz,
    )
    if result.significant_bin_count == 0:
        if any(value is not None for value in selected) or (
            NO_SIGNIFICANT_BIN not in result.reason_codes
        ):
            _fail("no-significant F12 result must not publish a selected band")
        return
    if any(value is None for value in selected) or result.stored_significant_bin_count == 0:
        _fail("significant F12 result must publish its selected band")
    scale, low, high = selected
    if (
        not isinstance(scale, int)
        or not isinstance(low, float)
        or not isinstance(high, float)
        or not math.isfinite(low)
        or not math.isfinite(high)
        or low > high
    ):
        _fail("F12 selected band is invalid")
    retained = (
        (result.scale_index == scale)
        & (result.frequencies_hz >= low)
        & (result.frequencies_hz <= high)
    )
    if not np.any(retained) or float(np.max(result.spectral_kurtosis)) != (
        result.maximum_spectral_kurtosis
    ):
        _fail("F12 stored domain lost the selected maximum")


def _validate_reasons(result: _Result) -> None:
    terminal = {PHASE_REFERENCE_UNAVAILABLE, ZERO_POWER, CLIPPED}
    if terminal.intersection(result.reason_codes):
        _fail("terminal F12 reason cannot be partial")
    has_scale_gap = not bool(np.all(result.scale_available))
    has_scale_reason = bool(
        {SCALE_UNSUPPORTED, INSUFFICIENT_FRAMES}.intersection(result.reason_codes)
    )
    if has_scale_gap != has_scale_reason:
        _fail("F12 scale support lacks its declared reason")
    if (result.significant_bin_count == 0) != (NO_SIGNIFICANT_BIN in result.reason_codes):
        _fail("F12 no-significant accounting is inconsistent")
    cap_binds = result.significant_bin_count > MAXIMUM_STORED_BINS
    if cap_binds != (ARTIFACT_LIMIT in result.reason_codes):
        _fail("F12 artifact cap accounting is inconsistent")


def _fail(detail: str) -> NoReturn:
    raise CharacterizationError("status_invariant", detail)
