"""F18: persistence mapper для bicoherence triad record."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import lnt.characterization.f18_contract as contract
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_arrays import decode_f18_arrays, published
from lnt.characterization.f18_decode import (
    checked_f18_codes,
    checked_f18_reasons,
    checked_f18_status,
    f18_count,
    f18_record_span,
)
from lnt.characterization.f18_result import F18Result
from lnt.characterization.f18_tables import (
    F18_METADATA_TABLE_ID as _TABLE_ID,
)
from lnt.characterization.f18_tables import (
    bicoherence_metadata,
    locked_declarations,
    persisted_analysis_rate_hz,
    persisted_segment_samples,
)
from lnt.characterization.f18_validation import validate_f18_result
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
    from collections.abc import Mapping

    import numpy as np

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.tables import TableBlock

F18_ID = contract.F18_ID
F18_INDEX = contract.F18_INDEX
F18_METADATA_TABLE_ID = _TABLE_ID

# Public seam remains explicit through build_f18_family and decode_f18_result.

_F18_UNITS: Final = (Unit.HZ, Unit.RATIO, Unit.RAD, Unit.COUNT)
_WINDOW_KIND: Final = "record"
_SUMMARY_NAMES: Final = (
    "f18_sample_count",
    "f18_qualified_sample_count",
    "f18_frame_count",
    "f18_declared_triad_count",
    "f18_measurable_triad_count",
    "f18_off_grid_triad_count",
    "f18_above_nyquist_triad_count",
    "f18_dropped_triad_count",
    "f18_iaaft_converged_count",
)


def build_f18_family(
    result: F18Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Собрать F18 envelope, finite triad arrays и locked metadata table."""
    if (
        family.id != contract.F18_ID
        or family.method != contract.METHOD
        or family.method_version != 1
    ):
        raise CharacterizationError("family_order", "f18 mapper needs the f18 family")
    declarations = locked_declarations(family)
    reasons = checked_f18_codes(result.reason_codes)
    span = f18_record_span(record_duration_s)
    checked_f18_status(result.status, reasons)
    validate_f18_result(result)
    spec = _spec(family, band, measured_channel, span, result.status, reasons)
    if result.status is Status.UNAVAILABLE:
        return family_envelope(spec, zero_support()), {}, {}
    checked_f18_reasons(result, reasons)
    arrays, references = published(result, declarations, partial=result.status is Status.PARTIAL)
    table = bicoherence_metadata(declarations, result.segment_samples, result.analysis_rate_hz)
    envelope = family_envelope(
        spec,
        _support(result, span),
        array_refs=tuple(references),
        table_refs=(TableReference(table_id=F18_METADATA_TABLE_ID, role="bicoherence_metadata"),),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays, {F18_METADATA_TABLE_ID: table}


def decode_f18_result(
    family: FamilyResult,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> F18Result:
    """Проверить persisted F18 form и вернуть только engine-валидный F18Result."""
    reasons = checked_f18_codes(family.reason_codes)
    checked_f18_status(family.status, reasons)
    if family.status is Status.UNAVAILABLE:
        raise CharacterizationError("status_invariant", "unavailable F18 has no decodable domain")
    counters = _summary_counts(family)
    values = decode_f18_arrays(family, arrays, tables, counters[3], counters[7])
    segment_samples = persisted_segment_samples(tables[F18_METADATA_TABLE_ID])
    analysis_rate_hz = persisted_analysis_rate_hz(tables[F18_METADATA_TABLE_ID])
    sample_count, qualified_count, frame_count = counters[:3]
    if (
        family.n != qualified_count
        or family.support.sample_count != sample_count
        or family.support.observation_count != qualified_count
        or family.support.missing_count != sample_count - qualified_count
        or family.support.stored_count != qualified_count
        or family.support.selection_rule != "all"
    ):
        _fail("F18 persisted support accounting is inconsistent")
    restored = F18Result(
        status=family.status,
        reason_codes=family.reason_codes,
        triad_low_hz=values["f18_triad_low_hz"],
        triad_high_hz=values["f18_triad_high_hz"],
        triad_sum_hz=values["f18_triad_sum_hz"],
        bicoherence_squared=values["f18_bicoherence_squared"],
        biphase_rad=values["f18_biphase_rad"],
        phase_randomized_p_value=values["f18_phase_randomized_p_value"],
        iaaft_p_value=values["f18_iaaft_p_value"],
        dual_null_p_value=values["f18_dual_null_p_value"],
        adjusted_p_value=values["f18_adjusted_p_value"],
        triad_available=values["f18_triad_available"],
        significant=values["f18_significant"],
        frame_support=values["f18_frame_support"],
        sample_count=sample_count,
        qualified_sample_count=qualified_count,
        analysis_rate_hz=analysis_rate_hz,
        segment_samples=segment_samples,
        frame_count=frame_count,
        declared_triad_count=counters[3],
        measurable_triad_count=counters[4],
        off_grid_triad_count=counters[5],
        above_nyquist_triad_count=counters[6],
        dropped_triad_count=counters[7],
        iaaft_converged_count=counters[8],
    )
    validate_f18_result(restored)
    checked_f18_reasons(restored, reasons)
    return restored


def _support(result: F18Result, span: float) -> Support:
    sample = f18_count(result.sample_count, "sample_count")
    qualified = f18_count(result.qualified_sample_count, "qualified_sample_count")
    frames = f18_count(result.frame_count, "frame_count")
    if sample <= 0 or qualified <= 0 or sample < qualified or frames < contract.MINIMUM_FRAMES:
        _fail("invalid F18 support counts")
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


def _summaries(result: F18Result) -> tuple[ScalarSummary, ...]:
    return tuple(
        ScalarSummary(name=name, value=float(value), unit=Unit.COUNT)
        for name, value in zip(_SUMMARY_NAMES, _counter_values(result), strict=True)
    )


def _summary_counts(family: FamilyResult) -> tuple[int, ...]:
    summaries = family.comparison_summary
    if (
        len(summaries) != len(_SUMMARY_NAMES)
        or tuple(item.name for item in summaries) != _SUMMARY_NAMES
    ):
        _fail("F18 persisted accounting summaries are not canonical")
    values: list[int] = []
    for item in summaries:
        if item.unit is not Unit.COUNT or item.circular or not float(item.value).is_integer():
            _fail("F18 persisted accounting summary is invalid")
        values.append(int(item.value))
    return tuple(values)


def _counter_values(result: F18Result) -> tuple[int, ...]:
    return (
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


def _spec(  # noqa: PLR0913, PLR0917 - envelope carries declared F18 geometry
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=contract.F18_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F18_UNITS,
        window=Window(
            kind=_WINDOW_KIND,
            duration_s=span,
            sample_count=None,
            overlap_fraction=0.0,
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _fail(detail: str) -> None:
    raise CharacterizationError("status_invariant", detail)
