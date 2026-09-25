"""F12: persistence mapper для declared-scale спектральной куртозиса."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f12_arrays import (
    SELECTED_SCALE_ID,
    checked_cap_order,
    checked_scale_domain,
    decode_f12_result,
    published,
)
from lnt.characterization.f12_contract import (
    CLIPPED,
    DECLARED_CODES,
    F12_ID,
    F12_INDEX,
    MAXIMUM_SPECTRAL_KURTOSIS_NAME,
    METHOD,
    PHASE_REFERENCE_UNAVAILABLE,
    SELECTED_BAND_HIGH_NAME,
    SELECTED_BAND_LOW_NAME,
    SURROGATE_SUPPORT_NAME,
    WINDOW_SUPPORT_NAME,
    ZERO_POWER,
)
from lnt.characterization.f12_tables import (
    KURTOSIS_TABLE_ID,
    kurtosis_metadata,
    locked_declarations,
)
from lnt.characterization.f12_validation import validate_f12_result
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
    from lnt.characterization.f12_result import F12Result
    from lnt.characterization.tables import TableBlock

__all__ = [
    "F12_ID",
    "F12_INDEX",
    "KURTOSIS_TABLE_ID",
    "build_f12_family",
    "decode_f12_result",
]

_F12_UNITS: Final = (Unit.HZ, Unit.RATIO, Unit.COUNT)
_METHOD_VERSION: Final = 1
_WINDOW_KIND: Final = "record"
_TABLE_ROLE: Final = "spectral_kurtosis_metadata"
# WINDOW_SUPPORT_NAME публикует analyzed_scale_count: единственный счётчик F12,
# который считает объявленные STFT окна, набравшие поддержку.
_TERMINAL: Final = (PHASE_REFERENCE_UNAVAILABLE, ZERO_POWER, CLIPPED)
_COUNTER_FIELDS: Final = (
    ("f12_sample_count", "sample_count"),
    ("f12_qualified_sample_count", "qualified_sample_count"),
    (WINDOW_SUPPORT_NAME, "analyzed_scale_count"),
    ("f12_candidate_count", "candidate_count"),
    ("f12_significant_bin_count", "significant_bin_count"),
    ("f12_stored_significant_bin_count", "stored_significant_bin_count"),
    (SURROGATE_SUPPORT_NAME, "surrogate_count"),
)


def build_f12_family(
    result: F12Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Собрать F12 envelope, finite arrays и таблицу conventions."""
    if family.id != F12_ID or family.method != METHOD or family.method_version != _METHOD_VERSION:
        raise CharacterizationError("family_order", "f12 mapper needs the f12 family")
    declarations = locked_declarations(family)
    reasons = _checked_codes(result.reason_codes)
    span = _span(record_duration_s)
    _status(result.status, reasons)
    validate_f12_result(result)
    if result.status is Status.UNAVAILABLE:
        spec = _spec(family, band, measured_channel, span, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}, {}
    checked_scale_domain(result)
    checked_cap_order(result)
    arrays, references = published(result, partial=result.status is Status.PARTIAL)
    spec = _spec(family, band, measured_channel, span, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(result, span),
        array_refs=tuple(references),
        table_refs=(TableReference(table_id=KURTOSIS_TABLE_ID, role=_TABLE_ROLE),),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays, {KURTOSIS_TABLE_ID: kurtosis_metadata(declarations)}


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if (
        any(code not in DECLARED_CODES for code in codes)
        or len(set(codes)) != len(codes)
        or codes != tuple(sorted(codes))
    ):
        raise CharacterizationError("status_invariant", "f12 reasons are not canonical")
    return codes


def _status(status: object, reasons: tuple[str, ...]) -> None:
    if not isinstance(status, Status):
        raise CharacterizationError("status_invariant", "unknown F12 status")
    if (status is Status.AVAILABLE and reasons) or (status is not Status.AVAILABLE and not reasons):
        raise CharacterizationError("status_invariant", "invalid F12 status/reasons")
    if status is not Status.UNAVAILABLE and any(code in reasons for code in _TERMINAL):
        raise CharacterizationError("status_invariant", "terminal F12 reason cannot be partial")


def _span(value: float) -> float:
    span = float(value)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "f12 record duration must be positive")
    return span


def _support(result: F12Result, span: float) -> Support:
    sample = _count(result.sample_count, "sample_count")
    qualified = _count(result.qualified_sample_count, "qualified_sample_count")
    if sample <= 0 or qualified <= 0 or sample < qualified:
        raise CharacterizationError("status_invariant", "invalid f12 support counts")
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


def _summaries(result: F12Result) -> tuple[ScalarSummary, ...]:
    """Опубликовать счётчики, измеренный maximum и полосу только когда она есть."""
    maximum = result.maximum_spectral_kurtosis
    if maximum is None:
        raise CharacterizationError("status_invariant", "built F12 result must publish a maximum")
    counts = (
        ScalarSummary(name=name, value=float(getattr(result, field)), unit=Unit.COUNT)
        for name, field in _COUNTER_FIELDS
    )
    return (
        *counts,
        ScalarSummary(name=MAXIMUM_SPECTRAL_KURTOSIS_NAME, value=maximum, unit=Unit.RATIO),
        *_band_summaries(result),
    )


def _band_summaries(result: F12Result) -> tuple[ScalarSummary, ...]:
    """Структурно отсутствующая полоса публикуется отсутствием, а не нулём."""
    scale, low, high = (
        result.selected_scale_index,
        result.selected_band_low_hz,
        result.selected_band_high_hz,
    )
    if result.significant_bin_count == 0:
        if any(value is not None for value in (scale, low, high)):
            raise CharacterizationError("status_invariant", "f12 absent band is not explicit")
        return ()
    if scale is None or low is None or high is None:
        raise CharacterizationError("status_invariant", "f12 selected band is not published")
    return (
        ScalarSummary(name=SELECTED_BAND_LOW_NAME, value=low, unit=Unit.HZ),
        ScalarSummary(name=SELECTED_BAND_HIGH_NAME, value=high, unit=Unit.HZ),
        ScalarSummary(name=SELECTED_SCALE_ID, value=float(scale), unit=Unit.COUNT),
    )


def _spec(  # noqa: PLR0913, PLR0917 - конверт несёт declared F12 geometry
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    span: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F12_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F12_UNITS,
        window=Window(
            kind=_WINDOW_KIND,
            duration_s=span,
            sample_count=None,
            overlap_fraction=0.0,
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CharacterizationError("status_invariant", f"f12 {name} must be a nonnegative integer")
    return value
