"""F18: инварианты fixed triad domain, masked absence и unavailable-результата."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_contract import (
    ARTIFACT_LIMIT,
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    DECLARED_CODES,
    FALSE_DISCOVERY_RATE,
    FRAME_SUPPORT_NAME,
    IAAFT_NOT_CONVERGED,
    IAAFT_SURROGATE_COUNT,
    MINIMUM_FRAMES,
    NO_SIGNIFICANT_TRIAD,
    OVERLAP_FRACTION,
    TRIAD_ABOVE_NYQUIST,
    TRIAD_HIGH_NAME,
    TRIAD_LOW_NAME,
    TRIAD_OFF_GRID,
    TRIAD_SUM_NAME,
    ZERO_DENOMINATOR,
)
from lnt.characterization.f18_significance import benjamini_hochberg
from lnt.characterization.records import Status, Unit, validate_unit_name

type Float64Array = np.ndarray
type Int64Array = np.ndarray
type BoolArray = np.ndarray


class _Result(Protocol):
    """Structural read contract без runtime import result-модуля."""

    @property
    def status(self) -> Status: ...

    @property
    def reason_codes(self) -> tuple[str, ...]: ...

    @property
    def triad_low_hz(self) -> Float64Array: ...

    @property
    def triad_high_hz(self) -> Float64Array: ...

    @property
    def triad_sum_hz(self) -> Float64Array: ...

    @property
    def bicoherence_squared(self) -> Float64Array: ...

    @property
    def biphase_rad(self) -> Float64Array: ...

    @property
    def phase_randomized_p_value(self) -> Float64Array: ...

    @property
    def iaaft_p_value(self) -> Float64Array: ...

    @property
    def dual_null_p_value(self) -> Float64Array: ...

    @property
    def adjusted_p_value(self) -> Float64Array: ...

    @property
    def triad_available(self) -> BoolArray: ...

    @property
    def significant(self) -> BoolArray: ...

    @property
    def frame_support(self) -> Int64Array: ...

    @property
    def sample_count(self) -> int: ...

    @property
    def qualified_sample_count(self) -> int: ...

    @property
    def segment_samples(self) -> int: ...

    @property
    def frame_count(self) -> int: ...

    @property
    def declared_triad_count(self) -> int: ...

    @property
    def measurable_triad_count(self) -> int: ...

    @property
    def off_grid_triad_count(self) -> int: ...

    @property
    def above_nyquist_triad_count(self) -> int: ...

    @property
    def dropped_triad_count(self) -> int: ...

    @property
    def iaaft_converged_count(self) -> int: ...


def validate_f18_result(result: _Result) -> None:
    """Проверить closed vocabulary, геометрию, support и masked absence."""
    _validate_codes(result)
    _validate_units()
    _validate_accounting(result)
    if result.status is Status.UNAVAILABLE:
        _validate_unavailable(result)
        return
    _validate_built(result)


def _validate_codes(result: _Result) -> None:
    """AVAILABLE не имеет причин; PARTIAL и UNAVAILABLE имеют причины."""
    if any(code not in DECLARED_CODES for code in result.reason_codes):
        _fail("reason code is outside the F18 vocabulary")
    if result.reason_codes != tuple(sorted(set(result.reason_codes))):
        _fail("reason codes must be sorted and unique")
    if result.status is Status.AVAILABLE and result.reason_codes:
        _fail("available F18 result must not have reasons")
    if result.status is not Status.AVAILABLE and not result.reason_codes:
        _fail("non-available F18 result needs reasons")


def _validate_units() -> None:
    """Проверить persisted quantity names через closed unit vocabulary."""
    for name, unit in (
        (BICOHERENCE_NAME, Unit.RATIO),
        (BIPHASE_NAME, Unit.RAD),
        (TRIAD_LOW_NAME, Unit.HZ),
        (TRIAD_HIGH_NAME, Unit.HZ),
        (TRIAD_SUM_NAME, Unit.HZ),
        (FRAME_SUPPORT_NAME, Unit.COUNT),
    ):
        validate_unit_name(name, unit)


def _validate_accounting(result: _Result) -> None:
    """Счётчики неотрицательны, а declared триады разбиты на свои три причины."""
    counts = (
        result.sample_count,
        result.qualified_sample_count,
        result.frame_count,
        result.declared_triad_count,
        result.measurable_triad_count,
        result.off_grid_triad_count,
        result.above_nyquist_triad_count,
        result.dropped_triad_count,
        result.iaaft_converged_count,
    )
    if result.segment_samples < 1 or any(value < 0 for value in counts):
        _fail("F18 support counts must be nonnegative")
    if (
        result.qualified_sample_count > result.sample_count
        or result.iaaft_converged_count > IAAFT_SURROGATE_COUNT
        or result.measurable_triad_count > result.declared_triad_count
    ):
        _fail("F18 support counts contradict each other")
    if result.declared_triad_count != (
        result.measurable_triad_count
        + result.off_grid_triad_count
        + result.above_nyquist_triad_count
    ):
        _fail("F18 declared triads are not partitioned by their declared reasons")


def _arrays(result: _Result) -> tuple[np.ndarray, ...]:
    return (
        result.triad_low_hz,
        result.triad_high_hz,
        result.triad_sum_hz,
        result.bicoherence_squared,
        result.biphase_rad,
        result.phase_randomized_p_value,
        result.iaaft_p_value,
        result.dual_null_p_value,
        result.adjusted_p_value,
        result.triad_available,
        result.significant,
        result.frame_support,
    )


def _validate_unavailable(result: _Result) -> None:
    """UNAVAILABLE публикует пустые domains, сохраняя только внешний support."""
    if any(array.size != 0 for array in _arrays(result)):
        _fail("unavailable F18 result must use empty domains")
    if (
        result.qualified_sample_count != 0
        or result.frame_count != 0
        or result.declared_triad_count != 0
        or result.measurable_triad_count != 0
        or result.iaaft_converged_count != 0
    ):
        _fail("unavailable F18 result must not claim measured support")


def _validate_built(result: _Result) -> None:
    """Проверить fixed triad domain, frame support, masks и BH-решение."""
    shape = (result.declared_triad_count,)
    if result.declared_triad_count < 1 or any(array.shape != shape for array in _arrays(result)):
        _fail("F18 arrays do not share their fixed triad domain")
    # Построенный результат обязан иметь хотя бы minimum_frames кадров: иначе
    # валидатор движка был бы мягче объявленного support, а бандл всё равно отверг.
    # Геометрия кадров выводится из ПУБЛИКОВАННОГО сегмента результата, а не из
    # константы модуля: recipe объявляет длительность, поэтому число отсчётов
    # принадлежит движку, и единственное место, где его можно проверить на
    # согласованность с hop, — это сам результат.
    hop_samples = round(result.segment_samples * (1.0 - OVERLAP_FRACTION))
    expected_samples = (result.frame_count - 1) * hop_samples + result.segment_samples
    if (
        result.frame_count < MINIMUM_FRAMES
        or result.qualified_sample_count != expected_samples
        or result.qualified_sample_count > result.sample_count
    ):
        _fail("F18 framed support does not follow its declared frame geometry")
    if not np.array_equal(result.frame_support, np.full(shape, result.frame_count, dtype=np.int64)):
        _fail("F18 frame support differs from the analyzed frame count")
    _validate_measurements(result)
    _validate_decision(result)
    _validate_required_reasons(result)


def _validate_measurements(result: _Result) -> None:
    """Доступная триада хранит [0,1] и p-value, недоступная — явный NaN."""
    available = result.triad_available
    if int(np.count_nonzero(available)) != result.measurable_triad_count:
        _fail("F18 measurable support differs from the triad availability mask")
    if not _masked(result.bicoherence_squared, available):
        _fail("F18 bicoherence validity mask is inconsistent")
    measured = result.bicoherence_squared[available]
    if measured.size == 0 or bool(np.any(measured < 0.0)) or bool(np.any(measured > 1.0)):
        _fail("F18 bicoherence must stay in [0, 1]")
    for values in (
        result.phase_randomized_p_value,
        result.iaaft_p_value,
        result.dual_null_p_value,
        result.adjusted_p_value,
    ):
        if not _masked(values, available):
            _fail("F18 p-value validity mask is inconsistent")
        selected = values[available]
        if selected.size == 0 or bool(np.any(selected < 0.0)) or bool(np.any(selected > 1.0)):
            _fail("F18 p-values must stay in [0, 1]")
    if not np.array_equal(
        result.dual_null_p_value,
        np.maximum(result.phase_randomized_p_value, result.iaaft_p_value),
        equal_nan=True,
    ):
        _fail("F18 dual null p-value differs from the declared maximum")
    if not np.array_equal(np.isfinite(result.biphase_rad), result.significant):
        _fail("F18 biphase is stored exactly for significant triads")


def _validate_decision(result: _Result) -> None:
    """Флаг значимости обязан совпадать с одним BH-проходом по тем же p-value."""
    available = result.triad_available
    adjusted, significant = benjamini_hochberg(
        result.dual_null_p_value[available], FALSE_DISCOVERY_RATE
    )
    if not np.array_equal(adjusted, result.adjusted_p_value[available]):
        _fail("F18 adjusted p-value differs from the declared Benjamini-Hochberg pass")
    expected = np.zeros(result.declared_triad_count, dtype=np.bool_)
    expected[available] = significant
    if not np.array_equal(result.significant, expected):
        _fail("F18 significance differs from the declared Benjamini-Hochberg decision")


def _validate_required_reasons(result: _Result) -> None:
    """Каждая измеренная причина обязана быть объявлена своим locked кодом."""
    required: set[str] = set()
    if result.off_grid_triad_count:
        required.add(TRIAD_OFF_GRID)
    if result.above_nyquist_triad_count:
        required.add(TRIAD_ABOVE_NYQUIST)
    if result.dropped_triad_count:
        required.add(ARTIFACT_LIMIT)
    if int(np.count_nonzero(result.triad_available)) != result.measurable_triad_count:
        required.add(ZERO_DENOMINATOR)
    if result.iaaft_converged_count < IAAFT_SURROGATE_COUNT:
        required.add(IAAFT_NOT_CONVERGED)
    if not bool(np.any(result.significant)):
        required.add(NO_SIGNIFICANT_TRIAD)
    if not required.issubset(result.reason_codes):
        _fail("F18 measured support lacks its declared reason code")


def _masked(values: np.ndarray, mask: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(values[mask])) and np.all(np.isnan(values[~mask])))


def _fail(detail: str) -> None:
    raise CharacterizationError("status_invariant", detail)
