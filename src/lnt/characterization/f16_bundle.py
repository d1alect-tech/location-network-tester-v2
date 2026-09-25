"""F16: persistence mapper для multiscale-memory результата."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f16_arrays import decode_f16_result, published
from lnt.characterization.f16_contract import (
    DECLARED_CODES,
    F16_ID,
    F16_INDEX,
    METHOD,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_ZERO,
)
from lnt.characterization.f16_result import F16Declarations
from lnt.characterization.f16_tables import MEMORY_TABLE_ID, memory_metadata
from lnt.characterization.f16_validation import validate_f16_result
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import FamilyResult, TableReference
from lnt.characterization.records import (
    Band,
    ScalarSummary,
    Status,
    Support,
    Unit,
    Window,
)

if TYPE_CHECKING:
    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f16_result import F16Result
    from lnt.characterization.tables import TableBlock

__all__ = ["F16_ID", "F16_INDEX", "MEMORY_TABLE_ID", "build_f16_family", "decode_f16_result"]

_F16_UNITS: Final = (Unit.S, Unit.RATIO, Unit.COUNT)
_WINDOW_KIND: Final = "record"


def build_f16_family(
    result: F16Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Собрать F16 envelope, finite arrays и таблицу conventions."""
    if family.id != F16_ID or family.method != METHOD or family.method_version != 1:
        raise CharacterizationError("family_order", "f16 mapper needs the f16 family")
    declarations = _locked_declarations(_declarations(family))
    reasons = _checked_codes(result.reason_codes)
    span = _span(record_duration_s)
    _status(result.status, reasons)
    validate_f16_result(result)
    if result.status is Status.UNAVAILABLE:
        spec = _spec(family, band, measured_channel, span, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}, {}
    arrays, references = published(result, declarations, partial=result.status is Status.PARTIAL)
    table = memory_metadata(declarations)
    spec = _spec(family, band, measured_channel, span, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(result, span),
        array_refs=tuple(references),
        table_refs=(TableReference(table_id=MEMORY_TABLE_ID, role="memory_metadata"),),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays, {MEMORY_TABLE_ID: table}


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if (
        any(code not in DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "f16 reasons are not canonical")
    return codes


def _status(status: object, reasons: tuple[str, ...]) -> None:
    if not isinstance(status, Status):
        raise CharacterizationError("status_invariant", "unknown F16 status")
    if (status is Status.AVAILABLE and reasons) or (status is not Status.AVAILABLE and not reasons):
        raise CharacterizationError("status_invariant", "invalid F16 status/reasons")
    if status is not Status.UNAVAILABLE and any(
        code in reasons for code in (PHASE_REFERENCE_UNAVAILABLE, SCALE_ZERO)
    ):
        raise CharacterizationError("status_invariant", "terminal F16 reason cannot be partial")


def _span(value: float) -> float:
    span = float(value)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "f16 record duration must be positive")
    return span


def _support(result: F16Result, span: float) -> Support:
    sample = _count(result.sample_count, "sample_count")
    qualified = _count(result.qualified_sample_count, "qualified_sample_count")
    segments = _count(result.analyzed_segment_count, "analyzed_segment_count")
    _count(result.event_count, "event_count")
    if sample <= 0 or qualified <= 0 or sample < qualified or not 1 <= segments <= qualified:
        raise CharacterizationError("status_invariant", "invalid f16 support counts")
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


def _summaries(result: F16Result) -> tuple[ScalarSummary, ...]:
    values = (
        ("f16_sample_count", result.sample_count),
        ("f16_qualified_sample_count", result.qualified_sample_count),
        ("f16_analyzed_segment_count", result.analyzed_segment_count),
        ("f16_event_count", result.event_count),
    )
    return tuple(
        ScalarSummary(name=name, value=float(value), unit=Unit.COUNT) for name, value in values
    )


def _spec(  # noqa: PLR0913, PLR0917 - конверт несёт declared F16 geometry
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F16_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F16_UNITS,
        window=Window(
            kind=_WINDOW_KIND,
            duration_s=span,
            sample_count=None,
            overlap_fraction=0.0,
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _declarations(family: CharacterizationFamily) -> F16Declarations:
    try:
        return F16Declarations(
            phase_bins=_integer(family.value("phase_bins")),
            autocovariance=_text(family.value("autocovariance")),
            lags_s=_numbers(family.value("lags_s")),
            recurrence_radius_mad=_numbers(family.value("recurrence_radius_mad")),
            count_windows_s=_numbers(family.value("count_windows_s")),
            count_window_overlap_fraction=_number(family.value("count_window_overlap_fraction")),
            partial_count_window_handling=_text(family.value("partial_count_window_handling")),
            fano_variance_ddof=_integer(family.value("fano_variance_ddof")),
            minimum_pairs=_integer(family.value("minimum_pairs")),
            minimum_count_windows=_integer(family.value("minimum_count_windows")),
            maximum_fft_segment_samples=_integer(family.value("maximum_fft_segment_samples")),
        )
    except ValueError as error:
        raise CharacterizationError(
            "status_invariant", "F16 recipe declarations are invalid"
        ) from error


def _locked_declarations(declarations: F16Declarations) -> F16Declarations:
    if declarations != F16Declarations.locked():
        raise CharacterizationError("status_invariant", "F16 recipe declarations are not locked")
    return declarations


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CharacterizationError("status_invariant", "F16 recipe value must be text")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("status_invariant", "F16 recipe value must be an integer")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CharacterizationError("status_invariant", "F16 recipe value must be a number")
    return float(value)


def _numbers(value: object) -> tuple[float, ...]:
    if not isinstance(value, tuple | list) or not value:
        raise CharacterizationError("status_invariant", "F16 recipe axis has wrong shape")
    return tuple(_number(item) for item in value)


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CharacterizationError("status_invariant", f"f16 {name} must be a nonnegative integer")
    return value
