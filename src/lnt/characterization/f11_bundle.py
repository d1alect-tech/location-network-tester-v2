"""Mapper for F11 fixed phase-band-F15-mode conditional distributions."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import numpy as np

import lnt.characterization.f11_result as r
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f11_arrays import (
    CELL_TABLE_ID,
    cell_table,
    published,
)
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import FamilyResult, TableReference
from lnt.characterization.records import Band, ScalarSummary, Status, Support, Unit, Window

if TYPE_CHECKING:
    from lnt.analysis_store import characterization_family as family_types
    from lnt.characterization import tables as table_types

F11_ID: Final = "f11_conditional_distributions"
F11_INDEX: Final = 10
_UNITS: Final = (Unit.V, Unit.S, Unit.HZ, Unit.V2_S, Unit.COUNT, Unit.RATIO, Unit.RAD)


def build_f11_family(
    result: r.F11Result,
    family: family_types.CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, table_types.TableBlock]]:
    """Build the F11 family envelope, arrays, and cell table."""
    if family.id != F11_ID:
        raise CharacterizationError("family_order", "recipe must declare f11 at slot ten")
    reasons = _codes(result.reason_codes)
    if result.status is Status.UNAVAILABLE:
        if result.cells or any(result.cdf_grids):
            raise CharacterizationError("status_invariant", "unavailable f11 must publish no cells")
        spec = _spec(family, band, measured_channel, record_duration_s, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}, {}
    _validate(result, reasons)
    arrays, refs = published(result, partial=result.status is Status.PARTIAL)
    assigned = sum(cell.support_count for cell in result.cells)
    spec = _spec(family, band, measured_channel, record_duration_s, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(result, assigned),
        array_refs=tuple(refs),
        table_refs=(TableReference(table_id=CELL_TABLE_ID, role="conditional_cells"),),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays, {CELL_TABLE_ID: cell_table(result)}


def _codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if (
        any(code not in r.DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "f11 reason codes are not canonical")
    return codes


def _validate(result: r.F11Result, reasons: tuple[str, ...]) -> None:
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
    if not max(missing) <= result.n_missing <= sum(missing) + excluded:
        raise CharacterizationError("status_invariant", "f11 missing accounting is inconsistent")
    if bool(omitted) != ("event_limit" in reasons):
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
    _status(cell.status, _codes(cell.reason_codes))
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
    elif all(item.status is Status.AVAILABLE for item in cell.distributions):
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
    _status(item.status, _codes(item.reason_codes))
    if (
        item.quantity != r.QUANTITIES[index]
        or min(item.observed_count, item.missing_count) < 0
        or item.observed_count + item.missing_count != cell.support_count
    ):
        raise CharacterizationError("status_invariant", "f11 quantity support is misaligned")
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


def _spec(  # noqa: PLR0913, PLR0917 - declared envelope context
    family: family_types.CharacterizationFamily,
    band: Band,
    channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    duration = float(span)
    if not math.isfinite(duration) or duration <= 0.0:
        raise CharacterizationError("status_invariant", "f11 record duration must be positive")
    return FamilySpec(
        family_id=F11_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_UNITS,
        window=Window(kind="record", duration_s=duration, sample_count=None, overlap_fraction=0.0),
        band=band,
        signal_plane=signal_plane_for(channel),
    )


def _support(result: r.F11Result, assigned: int) -> Support:
    return Support(
        start_s=0.0,
        end_s=0.0,
        duration_s=0.0,
        sample_count=int(result.event_count),
        observation_count=assigned,
        missing_count=int(result.event_count) - assigned,
        stored_count=assigned,
        selection_rule="all",
    )


def _summaries(result: r.F11Result) -> tuple[ScalarSummary, ...]:
    fields = (
        "event_count",
        "evaluated_event_count",
        "omitted_event_count",
        "n_missing",
        "n_mode_missing",
        "n_dominant_band_unavailable",
        "n_phase_unavailable",
    )
    summaries = tuple(
        ScalarSummary(name=f"f11_{field}", value=float(getattr(result, field)), unit=Unit.COUNT)
        for field in fields
    )
    return (
        *summaries,
        ScalarSummary(name="f11_maximum_events", value=float(r.MAXIMUM_EVENTS), unit=Unit.COUNT),
    )
