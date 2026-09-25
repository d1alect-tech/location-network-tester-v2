"""F17: fail-closed validation of axes, masks, p-values and stored cells."""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f17_contract import (
    ARTIFACT_LIMIT,
    BH_P_VALUE_NAME,
    CYCLIC_FREQUENCIES_HZ,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_SPECTRUM_NAME,
    DECLARED_CODES,
    FALSE_DISCOVERY_RATE,
    FREQUENCY_NAME,
    MAXIMUM_STORED_CELLS,
    MINIMUM_COMPLETE_CYCLES,
    MINIMUM_FRAMES,
    NO_SIGNIFICANT_CELL,
    RAW_P_VALUE_NAME,
    SEGMENT_SUPPORT_NAME,
)
from lnt.characterization.records import Status, Unit, validate_unit_name

type Float64Array = NDArray[np.float64]
type Complex128Array = NDArray[np.complex128]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]


class _Result(Protocol):
    @property
    def status(self) -> Status: ...

    @property
    def reason_codes(self) -> tuple[str, ...]: ...

    @property
    def cyclic_frequencies_hz(self) -> Float64Array: ...

    @property
    def frequencies_hz(self) -> Float64Array: ...

    @property
    def cyclic_spectrum(self) -> Complex128Array: ...

    @property
    def coherence(self) -> Float64Array: ...

    @property
    def raw_p_value(self) -> Float64Array: ...

    @property
    def bh_p_value(self) -> Float64Array: ...

    @property
    def segment_support(self) -> Int64Array: ...

    @property
    def cell_available(self) -> BoolArray: ...

    @property
    def significant(self) -> BoolArray: ...

    @property
    def stored_alpha_hz(self) -> Float64Array: ...

    @property
    def stored_frequency_hz(self) -> Float64Array: ...

    @property
    def stored_cyclic_spectrum(self) -> Complex128Array: ...

    @property
    def stored_coherence(self) -> Float64Array: ...

    @property
    def stored_raw_p_value(self) -> Float64Array: ...

    @property
    def stored_bh_p_value(self) -> Float64Array: ...

    @property
    def stored_segment_support(self) -> Int64Array: ...

    @property
    def sample_count(self) -> int: ...

    @property
    def qualified_sample_count(self) -> int: ...

    @property
    def qualified_cycle_count(self) -> int: ...

    @property
    def frame_count(self) -> int: ...

    @property
    def tested_cell_count(self) -> int: ...

    @property
    def significant_cell_count(self) -> int: ...

    @property
    def stored_cell_count(self) -> int: ...

    @property
    def omitted_cell_count(self) -> int: ...


def validate_f17_result(result: _Result) -> None:
    """Проверить closed vocabulary, геометрию, support и masked absence."""
    _validate_codes(result)
    _validate_units()
    _validate_counts(result)
    if result.status is Status.UNAVAILABLE:
        _validate_unavailable(result)
        return
    _validate_built(result)


def _validate_codes(result: _Result) -> None:
    if any(code not in DECLARED_CODES for code in result.reason_codes):
        _fail("reason code is outside the F17 vocabulary")
    if result.reason_codes != tuple(sorted(set(result.reason_codes))):
        _fail("reason codes must be sorted and unique")
    if result.status is Status.AVAILABLE and result.reason_codes:
        _fail("available F17 result must not have reasons")
    if result.status is not Status.AVAILABLE and not result.reason_codes:
        _fail("non-available F17 result needs reasons")


def _validate_units() -> None:
    for name, unit in (
        (FREQUENCY_NAME, Unit.HZ),
        (CYCLIC_FREQUENCY_NAME, Unit.HZ),
        (CYCLIC_SPECTRUM_NAME, Unit.V2),
        ("f17_coherence", Unit.RATIO),
        (RAW_P_VALUE_NAME, Unit.RATIO),
        (BH_P_VALUE_NAME, Unit.RATIO),
        (SEGMENT_SUPPORT_NAME, Unit.COUNT),
    ):
        validate_unit_name(name, unit)


def _validate_counts(result: _Result) -> None:
    values = (
        result.sample_count,
        result.qualified_sample_count,
        result.qualified_cycle_count,
        result.frame_count,
        result.tested_cell_count,
        result.significant_cell_count,
        result.stored_cell_count,
        result.omitted_cell_count,
    )
    if any(value < 0 for value in values) or result.qualified_sample_count > result.sample_count:
        _fail("F17 support counts are inconsistent")


def _arrays(result: _Result) -> tuple[np.ndarray, ...]:
    return (
        result.cyclic_frequencies_hz,
        result.frequencies_hz,
        result.cyclic_spectrum,
        result.coherence,
        result.raw_p_value,
        result.bh_p_value,
        result.segment_support,
        result.cell_available,
        result.significant,
        result.stored_alpha_hz,
        result.stored_frequency_hz,
        result.stored_cyclic_spectrum,
        result.stored_coherence,
        result.stored_raw_p_value,
        result.stored_bh_p_value,
        result.stored_segment_support,
    )


def _validate_unavailable(result: _Result) -> None:
    if any(array.size != 0 for array in _arrays(result)):
        _fail("unavailable F17 result must use empty domains")
    if (
        result.qualified_sample_count != 0
        or result.qualified_cycle_count != 0
        or result.frame_count != 0
        or result.tested_cell_count != 0
        or result.significant_cell_count != 0
        or result.stored_cell_count != 0
        or result.omitted_cell_count != 0
    ):
        _fail("unavailable F17 result must not claim analyzed support")


def _validate_built(result: _Result) -> None:
    alpha_count = len(CYCLIC_FREQUENCIES_HZ)
    frequency_count = result.frequencies_hz.size
    shape = (alpha_count, frequency_count)
    if (
        result.cyclic_frequencies_hz.shape != (alpha_count,)
        or result.frequencies_hz.ndim != 1
        or frequency_count == 0
        or result.cyclic_spectrum.shape != shape
        or result.coherence.shape != shape
        or result.raw_p_value.shape != shape
        or result.bh_p_value.shape != shape
        or result.segment_support.shape != shape
        or result.cell_available.shape != shape
        or result.significant.shape != shape
        or not np.array_equal(result.cyclic_frequencies_hz, CYCLIC_FREQUENCIES_HZ)
        or not np.all(np.isfinite(result.frequencies_hz))
        or bool(np.any(np.diff(result.frequencies_hz) <= 0.0))
        or result.qualified_cycle_count < MINIMUM_COMPLETE_CYCLES
        or result.frame_count < MINIMUM_FRAMES
        or result.qualified_sample_count <= 0
    ):
        _fail("F17 built axes or support do not match the locked method")
    _validate_masked_values(result)
    _validate_counts_and_cells(result)


def _validate_masked_values(result: _Result) -> None:
    mask = result.cell_available
    if not _masked_complex(result.cyclic_spectrum, mask):
        _fail("F17 cyclic spectrum validity mask is inconsistent")
    for values in (result.coherence, result.raw_p_value, result.bh_p_value):
        if not _masked_float(values, mask):
            _fail("F17 measured value validity mask is inconsistent")
    if not bool(np.all(result.segment_support[mask] == result.frame_count)):
        _fail("F17 segment support differs from frame count")
    if np.any(result.segment_support[~mask] != 0):
        _fail("unavailable F17 cells cannot claim segment support")
    if np.any((result.coherence[mask] < 0.0) | (result.coherence[mask] > 1.0)):
        _fail("F17 coherence must stay in [0, 1]")
    if np.any((result.raw_p_value[mask] < 0.0) | (result.raw_p_value[mask] > 1.0)):
        _fail("F17 raw p-values must stay in [0, 1]")
    if np.any((result.bh_p_value[mask] < 0.0) | (result.bh_p_value[mask] > 1.0)):
        _fail("F17 BH p-values must stay in [0, 1]")
    expected = mask & (result.bh_p_value <= FALSE_DISCOVERY_RATE)
    if not np.array_equal(result.significant, expected):
        _fail("F17 significant mask differs from declared BH threshold")


def _validate_counts_and_cells(result: _Result) -> None:
    available_count = int(np.count_nonzero(result.cell_available))
    significant_count = int(np.count_nonzero(result.significant))
    stored_count = result.stored_cell_count
    if (
        result.tested_cell_count != available_count
        or result.significant_cell_count != significant_count
        or stored_count > MAXIMUM_STORED_CELLS
        or stored_count > significant_count
        or result.omitted_cell_count != significant_count - stored_count
    ):
        _fail("F17 tested, significant, and stored counts are inconsistent")
    stored_shapes = (
        result.stored_alpha_hz,
        result.stored_frequency_hz,
        result.stored_cyclic_spectrum,
        result.stored_coherence,
        result.stored_raw_p_value,
        result.stored_bh_p_value,
        result.stored_segment_support,
    )
    if any(array.ndim != 1 or array.size != stored_count for array in stored_shapes):
        _fail("F17 stored arrays do not share one bounded domain")
    _validate_stored_prefix(result)
    if result.omitted_cell_count > 0 and ARTIFACT_LIMIT not in result.reason_codes:
        _fail("F17 stored-cell cap must report artifact_limit")
    if significant_count == 0 and NO_SIGNIFICANT_CELL not in result.reason_codes:
        _fail("F17 absent discoveries must report no_significant_cell")


def _validate_stored_prefix(result: _Result) -> None:
    indices = np.flatnonzero(result.significant.ravel())[: result.stored_cell_count]
    expected_alpha = result.cyclic_frequencies_hz[indices // result.frequencies_hz.size]
    expected_frequency = result.frequencies_hz[indices % result.frequencies_hz.size]
    if not (
        np.array_equal(result.stored_alpha_hz, expected_alpha)
        and np.array_equal(result.stored_frequency_hz, expected_frequency)
        and np.array_equal(result.stored_cyclic_spectrum, result.cyclic_spectrum.ravel()[indices])
        and np.array_equal(result.stored_coherence, result.coherence.ravel()[indices])
        and np.array_equal(result.stored_raw_p_value, result.raw_p_value.ravel()[indices])
        and np.array_equal(result.stored_bh_p_value, result.bh_p_value.ravel()[indices])
        and np.array_equal(result.stored_segment_support, result.segment_support.ravel()[indices])
    ):
        _fail("F17 stored cells are not the canonical significant prefix")


def _masked_float(values: Float64Array, mask: BoolArray) -> bool:
    return bool(np.all(np.isfinite(values[mask])) and np.all(np.isnan(values[~mask])))


def _masked_complex(values: Complex128Array, mask: BoolArray) -> bool:
    return bool(np.all(np.isfinite(values[mask])) and np.all(np.isnan(values[~mask])))


def _fail(detail: str) -> None:
    raise CharacterizationError("status_invariant", detail)
