"""F13: маппер persistence для коактивности полосовых огибающих."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f13_arrays import (
    BAND_METADATA_TABLE_ID,
    published,
    validate_unavailable,
)
from lnt.characterization.f13_result import (
    BAND_COUNT,
    BAND_EDGE_COUNT,
    DECLARED_CODES,
    METHOD,
    F13Declarations,
)
from lnt.characterization.family_envelope import (
    FamilySpec,
    family_envelope,
    signal_plane_for,
    zero_support,
)
from lnt.characterization.models import FamilyResult, TableReference
from lnt.characterization.records import (
    Band,
    Filter,
    ScalarSummary,
    Status,
    Support,
    Unit,
    Window,
)
from lnt.characterization.tables import TableBlock, TableColumn, TableValueType

if TYPE_CHECKING:
    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f13_result import F13Result

F13_ID: Final = "f13_band_envelope_coactivity"
F13_INDEX: Final = 12
_F13_UNITS: Final = (Unit.RATIO, Unit.S, Unit.COUNT, Unit.HZ)
_WINDOW_KIND: Final = "record"


def build_f13_family(
    result: F13Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Собрать F13 FamilyResult, выровненные массивы и band metadata."""
    if family.id != F13_ID or family.method != METHOD:
        raise CharacterizationError("family_order", "f13 mapper needs the f13 family")
    span = _span(record_duration_s)
    declarations = _declarations(family)
    reasons = _checked_codes(result.reason_codes)
    _status(result.status, reasons)
    if result.status is Status.UNAVAILABLE:
        validate_unavailable(result, declarations)
        spec = _spec(
            family, band, measured_channel, span, Status.UNAVAILABLE, reasons, declarations
        )
        return family_envelope(spec, zero_support()), {}, {}
    arrays, refs = published(result, declarations, partial=result.status is Status.PARTIAL)
    table = band_metadata(result)
    spec = _spec(family, band, measured_channel, span, result.status, reasons, declarations)
    envelope = family_envelope(
        spec,
        _support(result, span),
        array_refs=tuple(refs),
        table_refs=(TableReference(table_id=BAND_METADATA_TABLE_ID, role="band_metadata"),),
        comparison_summary=_summaries(result, declarations),
    )
    return envelope, arrays, {BAND_METADATA_TABLE_ID: table}


def band_metadata(result: F13Result) -> TableBlock:
    """Сохранить канонические имена и запрошенные края полос в одной таблице."""
    rows = tuple(
        (
            index,
            result.band_names[index],
            float(result.bands_hz[index][0]),
            float(result.bands_hz[index][1]),
        )
        for index in range(BAND_COUNT)
    )
    return TableBlock(
        table_id=BAND_METADATA_TABLE_ID,
        columns=(
            TableColumn(name="band_index", unit=Unit.COUNT, type=TableValueType.INTEGER),
            TableColumn(name="band_name", unit=None, type=TableValueType.TEXT),
            TableColumn(name="band_low_hz", unit=Unit.HZ, type=TableValueType.NUMBER),
            TableColumn(name="band_high_hz", unit=Unit.HZ, type=TableValueType.NUMBER),
        ),
        rows=rows,
        row_count=BAND_COUNT,
        stored_count=BAND_COUNT,
        selection_rule="all",
    )


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if (
        any(code not in DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "f13 reasons are not canonical")
    return codes


def _status(status: object, reasons: tuple[str, ...]) -> None:
    if not isinstance(status, Status):
        raise CharacterizationError("status_invariant", "unknown F13 status")
    if (status is Status.AVAILABLE and reasons) or (status is not Status.AVAILABLE and not reasons):
        raise CharacterizationError("status_invariant", "invalid F13 status/reasons")


def _span(value: float) -> float:
    span = float(value)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "f13 record duration must be positive")
    return span


def _declarations(family: CharacterizationFamily) -> F13Declarations:
    try:
        return F13Declarations(
            bands_hz=_bands(family),
            filter=_text(family, "filter"),
            filter_order=_integer(family, "filter_order"),
            filter_phase=_text(family, "filter_phase"),
            filter_edge_guard_fraction=_number(family, "filter_edge_guard_fraction"),
            phase_bins=_integer(family, "phase_bins"),
            activity_threshold_mad=_number(family, "activity_threshold_mad"),
            lag_low_s=_number(family, "lag_low_s"),
            lag_high_s=_number(family, "lag_high_s"),
            maximum_lag_points=_integer(family, "maximum_lag_points"),
            lag_tie_break=_text(family, "lag_tie_break"),
            minimum_active_samples=_integer(family, "minimum_active_samples"),
        )
    except ValueError as error:
        raise CharacterizationError(
            "status_invariant", "F13 recipe declarations are invalid"
        ) from error


def _bands(family: CharacterizationFamily) -> tuple[tuple[float, float], ...]:
    raw = family.value("bands_hz")
    if not isinstance(raw, tuple) or len(raw) != BAND_COUNT:
        raise CharacterizationError("status_invariant", "f13 bands_hz has wrong shape")
    result: list[tuple[float, float]] = []
    for pair in raw:
        if not isinstance(pair, tuple) or len(pair) != BAND_EDGE_COUNT:
            raise CharacterizationError("status_invariant", "f13 bands_hz has wrong shape")
        result.append((_scalar(pair[0], "band edge"), _scalar(pair[1], "band edge")))
    return tuple(result)


def _text(family: CharacterizationFamily, name: str) -> str:
    raw = family.value(name)
    if not isinstance(raw, str) or not raw:
        raise CharacterizationError("status_invariant", f"f13 {name} must be text")
    return raw


def _integer(family: CharacterizationFamily, name: str) -> int:
    raw = family.value(name)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CharacterizationError("status_invariant", f"f13 {name} must be an integer")
    return raw


def _number(family: CharacterizationFamily, name: str) -> float:
    return _scalar(family.value(name), name)


def _scalar(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CharacterizationError("status_invariant", f"f13 {name} must be a number")
    return float(value)


def _spec(  # noqa: PLR0913, PLR0917 — конверт несёт объявленный контекст F13
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
    declarations: F13Declarations,
) -> FamilySpec:
    return FamilySpec(
        family_id=F13_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F13_UNITS,
        window=Window(
            kind=_WINDOW_KIND,
            duration_s=span,
            sample_count=None,
            overlap_fraction=0.0,
        ),
        band=band,
        filter=Filter(
            kind=declarations.filter,
            order=declarations.filter_order,
            phase=declarations.filter_phase,
        ),
        signal_plane=signal_plane_for(measured_channel),
    )


def _support(result: F13Result, span: float) -> Support:
    sample = _count(result.sample_count, "sample_count")
    qualified = _count(result.qualified_sample_count, "qualified_sample_count")
    if sample < 0 or qualified <= 0 or sample < qualified:
        raise CharacterizationError("status_invariant", "invalid f13 support counts")
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


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("status_invariant", f"f13 {name} must be an integer")
    return value


def _summaries(result: F13Result, declarations: F13Declarations) -> tuple[ScalarSummary, ...]:
    values = (
        ("f13_sample_count", result.sample_count, Unit.COUNT),
        ("f13_qualified_sample_count", result.qualified_sample_count, Unit.COUNT),
        ("f13_stored_lag_count", result.lag_s.size, Unit.COUNT),
        ("f13_maximum_lag_points", declarations.maximum_lag_points, Unit.COUNT),
        ("f13_lag_low_s", declarations.lag_low_s, Unit.S),
        ("f13_lag_high_s", declarations.lag_high_s, Unit.S),
        ("f13_filter_edge_guard_fraction", declarations.filter_edge_guard_fraction, Unit.RATIO),
        ("f13_phase_bins", declarations.phase_bins, Unit.COUNT),
        ("f13_minimum_active_samples", declarations.minimum_active_samples, Unit.COUNT),
        ("f13_activity_threshold_mad", declarations.activity_threshold_mad, Unit.RATIO),
    )
    return tuple(
        ScalarSummary(name=name, value=float(value), unit=unit) for name, value, unit in values
    )
