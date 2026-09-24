"""F14: persistence mapper для двусторонней event-triggered ассоциации."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f14_arrays import published, validate_unavailable
from lnt.characterization.f14_contract import (
    CHANNEL_MISSING,
    CHANNELS_NOT_SYNCHRONOUS,
    DECLARED_CODES,
    F14_ID,
    F14_INDEX,
    INSUFFICIENT_TRIGGERS,
    METHOD,
    PHASE_REFERENCE_UNAVAILABLE,
)
from lnt.characterization.f14_result import F14Declarations
from lnt.characterization.f14_tables import DIRECTION_TABLE_ID, direction_metadata
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    zero_support,
)
from lnt.characterization.models import FamilyResult, TableReference
from lnt.characterization.records import (
    Band,
    ScalarSummary,
    SignalPlane,
    Status,
    Support,
    Unit,
    Window,
)

if TYPE_CHECKING:
    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f14_result import F14Result
    from lnt.characterization.tables import TableBlock

__all__ = ["F14_ID", "F14_INDEX", "build_f14_family"]

_F14_UNITS: Final = (Unit.V, Unit.RATIO, Unit.S, Unit.COUNT)
_WINDOW_KIND: Final = "record"


def build_f14_family(
    result: F14Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Собрать F14 envelope, направленные массивы и таблицу учёта."""
    if family.id != F14_ID or family.method != METHOD or family.method_version != 1:
        raise CharacterizationError("family_order", "f14 mapper needs the f14 family")
    declarations = _locked_declarations(_declarations(family))
    reasons = _checked_codes(result.reason_codes)
    span = _span(record_duration_s)
    _status(result.status, reasons)
    if result.status is Status.UNAVAILABLE:
        validate_unavailable(result, declarations)
        spec = _spec(family, band, span, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}, {}
    arrays, refs = published(
        result,
        declarations,
        partial=result.status is Status.PARTIAL,
        reason_codes=reasons,
    )
    table = direction_metadata(result, declarations)
    spec = _spec(family, band, span, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(result, span),
        array_refs=tuple(refs),
        table_refs=(TableReference(table_id=DIRECTION_TABLE_ID, role="direction_metadata"),),
        comparison_summary=_summaries(result, declarations),
    )
    return envelope, arrays, {DIRECTION_TABLE_ID: table}


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if (
        any(code not in DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "f14 reasons are not canonical")
    return codes


def _status(status: object, reasons: tuple[str, ...]) -> None:
    if not isinstance(status, Status):
        raise CharacterizationError("status_invariant", "unknown F14 status")
    if (status is Status.AVAILABLE and reasons) or (status is not Status.AVAILABLE and not reasons):
        raise CharacterizationError("status_invariant", "invalid F14 status/reasons")
    if status is not Status.UNAVAILABLE and any(
        code in reasons
        for code in (
            CHANNEL_MISSING,
            CHANNELS_NOT_SYNCHRONOUS,
            INSUFFICIENT_TRIGGERS,
            PHASE_REFERENCE_UNAVAILABLE,
        )
    ):
        raise CharacterizationError("status_invariant", "incomplete F14 reason cannot be built")


def _span(value: float) -> float:
    span = float(value)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "f14 record duration must be positive")
    return span


def _locked_declarations(declarations: F14Declarations) -> F14Declarations:
    """Не позволить persistence-рецепту разойтись с locked F14 surface."""
    if declarations != F14Declarations.locked():
        raise CharacterizationError("status_invariant", "F14 recipe declarations are not locked")
    return declarations


def _declarations(family: CharacterizationFamily) -> F14Declarations:
    try:
        return F14Declarations(
            trigger_window_low_s=_number(
                family.value("trigger_window_low_s"), "trigger_window_low_s"
            ),
            trigger_window_high_s=_number(
                family.value("trigger_window_high_s"), "trigger_window_high_s"
            ),
            relative_time_bins=_integer(family.value("relative_time_bins"), "relative_time_bins"),
            nearest_event_lag_low_s=_number(
                family.value("nearest_event_lag_low_s"), "nearest_event_lag_low_s"
            ),
            nearest_event_lag_high_s=_number(
                family.value("nearest_event_lag_high_s"), "nearest_event_lag_high_s"
            ),
            nearest_event_tie_break=_text(
                family.value("nearest_event_tie_break"), "nearest_event_tie_break"
            ),
            phase_bins=_integer(family.value("phase_bins"), "phase_bins"),
            cycle_shift_offsets=_offsets(family.value("cycle_shift_offsets")),
            minimum_triggers=_integer(family.value("minimum_triggers"), "minimum_triggers"),
            maximum_triggers_per_direction=_integer(
                family.value("maximum_triggers_per_direction"), "maximum_triggers_per_direction"
            ),
            boundary_handling=_text(family.value("boundary_handling"), "boundary_handling"),
        )
    except ValueError as error:
        raise CharacterizationError(
            "status_invariant", "F14 recipe declarations are invalid"
        ) from error


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CharacterizationError("status_invariant", f"f14 {name} must be text")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("status_invariant", f"f14 {name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CharacterizationError("status_invariant", f"f14 {name} must be a number")
    return float(value)


def _offsets(value: object) -> tuple[int, ...]:
    if not isinstance(value, tuple | list):
        raise CharacterizationError("status_invariant", "f14 cycle_shift_offsets has wrong shape")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise CharacterizationError("status_invariant", "f14 cycle_shift_offsets has wrong shape")
    return tuple(int(item) for item in value)


def _spec(
    family: CharacterizationFamily,
    band: Band,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F14_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F14_UNITS,
        window=Window(
            kind=_WINDOW_KIND,
            duration_s=span,
            sample_count=None,
            overlap_fraction=0.0,
        ),
        band=band,
        signal_plane=SignalPlane.CROSS_CHANNEL,
    )


def _support(result: F14Result, span: float) -> Support:
    sample = _integer(result.sample_count, "sample_count")
    qualified = _integer(result.qualified_cycle_count, "qualified_cycle_count")
    if qualified <= 0 or sample < qualified:
        raise CharacterizationError("status_invariant", "invalid F14 support counts")
    return Support(
        start_s=0.0,
        end_s=span,
        duration_s=span,
        sample_count=sample,
        observation_count=qualified,
        missing_count=sample - qualified,
        stored_count=qualified,
        selection_rule="all",
    )


def _summaries(result: F14Result, declarations: F14Declarations) -> tuple[ScalarSummary, ...]:
    stored = sum(direction.stored_trigger_count for direction in result.directions)
    qualified = sum(direction.qualified_trigger_count for direction in result.directions)
    omitted = sum(direction.omitted_trigger_count for direction in result.directions)
    matches = sum(direction.nearest_lag_s.size for direction in result.directions)
    values = (
        ("f14_sample_count", result.sample_count, Unit.COUNT),
        ("f14_qualified_cycle_count", result.qualified_cycle_count, Unit.COUNT),
        ("f14_relative_time_bins", declarations.relative_time_bins, Unit.COUNT),
        ("f14_phase_bins", declarations.phase_bins, Unit.COUNT),
        ("f14_cycle_shift_count", len(declarations.cycle_shift_offsets), Unit.COUNT),
        ("f14_minimum_triggers", declarations.minimum_triggers, Unit.COUNT),
        (
            "f14_maximum_triggers_per_direction",
            declarations.maximum_triggers_per_direction,
            Unit.COUNT,
        ),
        ("f14_stored_trigger_count", stored, Unit.COUNT),
        ("f14_qualified_trigger_count", qualified, Unit.COUNT),
        ("f14_omitted_trigger_count", omitted, Unit.COUNT),
        ("f14_nearest_lag_match_count", matches, Unit.COUNT),
        ("f14_nearest_lag_omitted_count", stored - matches, Unit.COUNT),
        ("f14_trigger_window_low_s", declarations.trigger_window_low_s, Unit.S),
        ("f14_trigger_window_high_s", declarations.trigger_window_high_s, Unit.S),
        ("f14_nearest_event_lag_low_s", declarations.nearest_event_lag_low_s, Unit.S),
        ("f14_nearest_event_lag_high_s", declarations.nearest_event_lag_high_s, Unit.S),
    )
    return tuple(
        ScalarSummary(name=name, value=float(value), unit=unit) for name, value, unit in values
    )
