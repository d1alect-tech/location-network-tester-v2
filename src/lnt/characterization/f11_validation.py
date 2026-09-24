"""Проверка инвариантов результата и persisted envelope F11."""

from __future__ import annotations

import math

import numpy as np

import lnt.characterization.f11_result as r
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.records import Status

_FREQUENCY_INDEX = 2
_MEASURED_INDICES = (0, 1, 3)


def validate_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    """Проверить замкнутый канонический словарь кодов F11."""
    if (
        any(code not in r.DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "f11 reason codes are not canonical")
    return codes


def validate_result(result: r.F11Result, reasons: tuple[str, ...]) -> None:
    """Проверить геометрию, учёт и статус до persisted envelope."""
    _status(result.status, reasons)
    _geometry(result)
    total = 0
    missing = [0, 0, 0, 0]
    counts = (
        result.n_missing,
        result.n_mode_missing,
        result.n_dominant_band_unavailable,
        result.n_phase_unavailable,
    )
    for cell in result.cells:
        total += cell.support_count
        _cell(cell, result.cdf_grids)
        for index, distribution in enumerate(cell.distributions):
            missing[index] += distribution.missing_count
    evaluated, omitted, events = (
        int(result.evaluated_event_count),
        int(result.omitted_event_count),
        int(result.event_count),
    )
    if (evaluated, omitted) != (
        min(max(events, 0), r.MAXIMUM_EVENTS),
        max(0, events - r.MAXIMUM_EVENTS),
    ) or any(value < 0 for value in counts):
        raise CharacterizationError("status_invariant", "f11 event accounting is inconsistent")
    excluded = evaluated - total
    if any(value > excluded for value in counts[1:]):
        raise CharacterizationError("status_invariant", "f11 exclusion counters are inconsistent")
    measured_missing = tuple(missing[index] for index in _MEASURED_INDICES)
    if not max(measured_missing) <= result.n_missing <= sum(measured_missing) + excluded:
        raise CharacterizationError("status_invariant", "f11 missing accounting is inconsistent")
    if bool(omitted) != (r.EVENT_LIMIT in reasons):
        raise CharacterizationError("status_invariant", "f11 event cap is not declared")
    if (
        result.status is Status.AVAILABLE
        and not any(cell.status is Status.AVAILABLE for cell in result.cells)
    ) or (
        result.status is Status.PARTIAL
        and not any(cell.status in (Status.AVAILABLE, Status.PARTIAL) for cell in result.cells)
    ):
        raise CharacterizationError("status_invariant", "f11 status has no supported cell")


def _geometry(result: r.F11Result) -> None:
    if (
        len(result.cells) != 192  # noqa: PLR2004
        or result.bands_hz != r.BANDS_HZ
        or not np.array_equal(
            result.phase_bin_edges_rad, tuple(2.0 * math.pi * index / 16 for index in range(17))
        )
        or len(result.mode_labels) != 4  # noqa: PLR2004
        or len(set(result.mode_labels)) != 4  # noqa: PLR2004
        or not np.array_equal(result.quantiles, r.QUANTILES)
        or not np.array_equal(result.cdf_probabilities, r.CDF_PROBABILITIES)
        or len(result.cdf_grids) != 4  # noqa: PLR2004
    ):
        raise CharacterizationError("status_invariant", "f11 geometry is not locked")
    expected = (
        (phase, band, label)
        for phase in range(16)
        for band in range(3)
        for label in result.mode_labels
    )
    if any(
        (cell.phase_bin, cell.band_index, cell.mode_label) != key
        for cell, key in zip(result.cells, expected, strict=True)
    ):
        raise CharacterizationError("status_invariant", "f11 cells do not cover the declared grid")
    for grid in result.cdf_grids:
        values = np.asarray(grid, dtype=np.float64)
        if (
            values.ndim != 1
            or values.size not in (0, r.CDF_PROBABILITIES.size)
            or not np.all(np.isfinite(values))
        ):
            raise CharacterizationError("status_invariant", "f11 cdf grid has wrong shape")


def _cell(cell: r.F11Cell, grids: tuple[tuple[float, ...], ...]) -> None:
    _status(cell.status, validate_codes(cell.reason_codes))
    if (
        min(cell.support_count, cell.positive_count, cell.negative_count) < 0
        or cell.positive_count + cell.negative_count > cell.support_count
        or len(cell.distributions) != 4  # noqa: PLR2004
    ):
        raise CharacterizationError("status_invariant", "f11 cell accounting is inconsistent")
    if cell.support_count == 0:
        expected, expected_codes = Status.UNAVAILABLE, (r.BIN_EMPTY,)
    elif cell.support_count < r.MINIMUM_SUPPORT:
        expected, expected_codes = Status.UNAVAILABLE, (r.INSUFFICIENT_SUPPORT,)
    elif all(
        item.status is Status.AVAILABLE
        for index, item in enumerate(cell.distributions)
        if index != _FREQUENCY_INDEX
    ):
        expected, expected_codes = Status.AVAILABLE, ()
    else:
        expected, expected_codes = Status.PARTIAL, (r.INSUFFICIENT_SUPPORT,)
    if cell.status is not expected or cell.reason_codes != expected_codes:
        raise CharacterizationError("status_invariant", "f11 cell status does not match support")
    for index, distribution in enumerate(cell.distributions):
        _distribution(cell, distribution, grids[index], index)


def _distribution(
    cell: r.F11Cell, item: r.F11QuantityResult, grid: tuple[float, ...], index: int
) -> None:
    _status(item.status, validate_codes(item.reason_codes))
    if (
        item.quantity != r.QUANTITIES[index]
        or min(item.observed_count, item.missing_count) < 0
        or item.observed_count + item.missing_count != cell.support_count
    ):
        raise CharacterizationError("status_invariant", "f11 quantity support is misaligned")
    if index == _FREQUENCY_INDEX:
        if (
            item.observed_count != 0
            or item.missing_count != cell.support_count
            or item.status is not Status.UNAVAILABLE
            or item.reason_codes != (r.INSUFFICIENT_SUPPORT,)
            or item.quantiles != (None,) * len(r.QUANTILES)
            or item.cdf_probabilities is not None
        ):
            raise CharacterizationError("status_invariant", "f11 absent frequency is invalid")
        return
    if item.status is Status.AVAILABLE:
        _available(item, grid)
    elif (
        item.status is not Status.UNAVAILABLE
        or item.observed_count >= r.MINIMUM_SUPPORT
        or item.quantiles != (None,) * len(r.QUANTILES)
        or item.cdf_probabilities is not None
    ):
        raise CharacterizationError("status_invariant", "f11 absent distribution is invalid")
    if cell.support_count == 0 and item.reason_codes != (r.BIN_EMPTY,):
        raise CharacterizationError("status_invariant", "empty f11 cell needs bin_empty")
    if 0 < cell.support_count < r.MINIMUM_SUPPORT and item.reason_codes != (
        r.INSUFFICIENT_SUPPORT,
    ):
        raise CharacterizationError("status_invariant", "under-supported f11 cell needs code")


def _available(item: r.F11QuantityResult, grid: tuple[float, ...]) -> None:
    quantiles, probabilities = item.quantiles, item.cdf_probabilities
    if len(quantiles) != len(r.QUANTILES) or any(
        value is None or not math.isfinite(float(value)) for value in quantiles
    ):
        raise CharacterizationError("status_invariant", "f11 quantiles are invalid")
    if (
        probabilities is None
        or len(probabilities) != len(grid)
        or any(
            not math.isfinite(float(value)) or not 0.0 <= value <= 1.0 for value in probabilities
        )
    ):
        raise CharacterizationError("status_invariant", "f11 distribution shape is invalid")


def _status(value: Status, reasons: tuple[str, ...]) -> None:
    if (value is Status.AVAILABLE and reasons) or (value is not Status.AVAILABLE and not reasons):
        raise CharacterizationError("status_invariant", "invalid F11 status/reasons")
