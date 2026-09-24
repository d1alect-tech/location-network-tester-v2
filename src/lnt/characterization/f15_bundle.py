"""F15 persistence mapper for deterministic fixed-k medoids."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f15_arrays import FEATURE_METADATA_TABLE_ID, feature_metadata, published
from lnt.characterization.f15_result import DECLARED_CODES, LABEL_LIMIT, F15Settings
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

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f15_result import F15Result
    from lnt.characterization.tables import TableBlock

F15_ID: Final = "f15_interpretable_modes"
F15_INDEX: Final = 14
_F15_UNITS: Final = (Unit.V, Unit.RATIO, Unit.COUNT, Unit.S)
_F15_WINDOW_KIND: Final = "fixed"
_MAXIMUM_LABELS: Final = F15Settings.locked().maximum_labels


def build_f15_family(
    result: F15Result,
    family: CharacterizationFamily,
    band: Band,
    *,
    measured_channel: str = "ch1",
    record_duration_s: float | None = None,
) -> tuple[FamilyResult, dict[str, np.ndarray], dict[str, TableBlock]]:
    """Map F15 result fields to a validated family envelope and artifacts."""
    if family.id != F15_ID:
        raise CharacterizationError("family_order", "f15 mapper needs the f15 family")
    reasons = _checked_codes(result.reason_codes)
    span = _span(record_duration_s, result)
    if result.status is Status.UNAVAILABLE:
        _check_unavailable(result)
        if not reasons:
            raise CharacterizationError("status_invariant", "unavailable f15 needs reasons")
        spec = _spec(family, band, measured_channel, result.window_s, Status.UNAVAILABLE, reasons)
        return family_envelope(spec, zero_support()), {}, {}
    if result.status is Status.AVAILABLE and reasons:
        raise CharacterizationError("status_invariant", "available f15 must have no reasons")
    if result.status is Status.PARTIAL and not reasons:
        raise CharacterizationError("status_invariant", "partial f15 needs reasons")
    if result.status not in (Status.AVAILABLE, Status.PARTIAL):
        raise CharacterizationError("status_invariant", "unknown f15 status")
    _check_cap(result, reasons)
    arrays, refs = published(result, partial=result.status is Status.PARTIAL)
    table = feature_metadata(result)
    spec = _spec(family, band, measured_channel, result.window_s, result.status, reasons)
    envelope = family_envelope(
        spec,
        _support(result, span, reasons),
        array_refs=tuple(refs),
        table_refs=(TableReference(table_id=FEATURE_METADATA_TABLE_ID, role="feature_metadata"),),
        comparison_summary=_summaries(result),
    )
    return envelope, arrays, {FEATURE_METADATA_TABLE_ID: table}


def _checked_codes(codes: tuple[str, ...]) -> tuple[str, ...]:
    if any(not code or code not in DECLARED_CODES for code in codes):
        raise CharacterizationError("status_invariant", "f15 reasons must use declared codes")
    if len(set(codes)) != len(codes):
        raise CharacterizationError("status_invariant", "f15 reasons must be unique")
    if codes != tuple(sorted(codes)):
        raise CharacterizationError("status_invariant", "f15 reasons must be sorted")
    return codes


def _spec(  # noqa: PLR0913, PLR0917 - envelope carries declared F15 geometry
    family: CharacterizationFamily,
    band: Band,
    measured_channel: str,
    window_s: float,
    status: Status,
    reasons: tuple[str, ...],
) -> FamilySpec:
    return FamilySpec(
        family_id=F15_ID,
        method=family.method,
        method_version=family.method_version,
        status=status,
        reasons=reasons,
        units=_F15_UNITS,
        window=Window(
            kind=_F15_WINDOW_KIND,
            duration_s=window_s,
            sample_count=None,
            overlap_fraction=0.0,
        ),
        band=band,
        signal_plane=signal_plane_for(measured_channel),
    )


def _support(result: F15Result, span: float, reasons: tuple[str, ...]) -> Support:
    complete = int(result.complete_window_count)
    qualified = int(result.qualified_window_count)
    unretained = int(result.unretained_window_count)
    if (
        complete < 0
        or qualified < 0
        or unretained < 0
        or qualified > complete
        or unretained != complete - qualified
        or qualified != int(result.labels.size)
        or qualified > _MAXIMUM_LABELS
    ):
        raise CharacterizationError("status_invariant", "invalid f15 support counts")
    end_s = complete * result.window_s
    if end_s > span + 1e-12:
        raise CharacterizationError("status_invariant", "f15 windows exceed the record")
    selection = "even_floor_index" if LABEL_LIMIT in reasons else "all"
    return Support(
        start_s=0.0,
        end_s=end_s,
        duration_s=end_s,
        sample_count=complete,
        observation_count=qualified,
        missing_count=unretained,
        stored_count=qualified,
        selection_rule=selection,
    )


def _summaries(result: F15Result) -> tuple[ScalarSummary, ...]:
    values = (
        ("f15_complete_window_count", result.complete_window_count, Unit.COUNT),
        ("f15_qualified_window_count", result.qualified_window_count, Unit.COUNT),
        ("f15_unretained_window_count", result.unretained_window_count, Unit.COUNT),
        ("f15_stored_label_count", result.labels.size, Unit.COUNT),
        ("f15_maximum_labels", _MAXIMUM_LABELS, Unit.COUNT),
        ("f15_swap_passes", result.swap_passes, Unit.COUNT),
    )
    return tuple(
        ScalarSummary(name=name, value=float(value), unit=unit) for name, value, unit in values
    )


def _span(value: float | None, result: F15Result) -> float:
    window_s = float(result.window_s)
    if not math.isfinite(window_s) or window_s <= 0.0:
        raise CharacterizationError("status_invariant", "f15 window duration must be positive")
    duration = window_s * max(int(result.complete_window_count), 1) if value is None else value
    span = float(duration)
    if not math.isfinite(span) or span <= 0.0:
        raise CharacterizationError("status_invariant", "f15 record duration must be positive")
    return span


def _check_cap(result: F15Result, reasons: tuple[str, ...]) -> None:
    complete = int(result.complete_window_count)
    capped = complete > _MAXIMUM_LABELS
    if capped != (LABEL_LIMIT in reasons):
        raise CharacterizationError("status_invariant", "f15 label cap accounting is inconsistent")
    if int(result.qualified_window_count) > _MAXIMUM_LABELS:
        raise CharacterizationError("status_invariant", "f15 stored labels exceed the cap")


def _check_unavailable(result: F15Result) -> None:
    empty = (
        result.qualified_window_count == 0
        and result.feature_medians.shape == (0,)
        and result.feature_mads.shape == (0,)
        and result.standardized_features.shape == (0, 7)
        and result.window_indices.shape == (0,)
        and result.medoid_indices.shape == (0,)
        and result.medoid_features.shape == (0, 7)
        and result.medoid_rms_v.shape == (0,)
        and result.labels.shape == (0,)
        and result.dwell_labels.shape == (0,)
        and result.dwell_durations_s.shape == (0,)
        and result.transition_counts.shape == (0, 0)
        and result.transition_probabilities.shape == (0, 0)
        and result.stability_ari.shape == (0,)
    )
    if not empty or int(result.unretained_window_count) != int(result.complete_window_count):
        raise CharacterizationError("status_invariant", "unavailable f15 must use empty domains")
