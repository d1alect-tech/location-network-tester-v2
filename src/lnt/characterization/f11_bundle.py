"""Mapper for F11 fixed phase-band-F15-mode conditional distributions."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import lnt.characterization.f11_result as r
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f11_arrays import (
    CELL_TABLE_ID,
    cell_table,
    published,
)
from lnt.characterization.f11_validation import validate_codes, validate_result
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import FamilyResult, TableReference
from lnt.characterization.records import Band, ScalarSummary, Status, Support, Unit, Window

if TYPE_CHECKING:
    import numpy as np

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
    reasons = validate_codes(result.reason_codes)
    if result.status is Status.UNAVAILABLE:
        if result.cells or any(result.cdf_grids):
            raise CharacterizationError("status_invariant", "unavailable f11 must publish no cells")
        spec = _spec(family, band, measured_channel, record_duration_s, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}, {}
    validate_result(result, reasons)
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
