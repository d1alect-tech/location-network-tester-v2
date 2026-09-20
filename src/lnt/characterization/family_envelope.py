"""Shared FamilyResult envelope construction for every characterization family."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from lnt.characterization.models import ArrayReference, FamilyResult, TableReference
from lnt.characterization.records import (
    Band,
    Filter,
    Inference,
    Qc,
    ScalarSummary,
    SignalPlane,
    Status,
    Support,
    Unit,
    Window,
)

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily

MISSING_RULE: Final = "exclude_and_count"
NOT_COMPUTED: Final = ("not_computed",)
NO_FILTER: Final = Filter(kind="none", order=None, phase="none")
PLACEHOLDER_UNITS: Final = (Unit.HZ, Unit.V, Unit.RAD, Unit.RATIO)
PLACEHOLDER_WINDOW: Final = Window(
    kind="fixed", duration_s=0.2, sample_count=None, overlap_fraction=0.0
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FamilySpec:
    """Declared identity, outcome and geometry of one family envelope."""

    family_id: str
    method: str
    method_version: int
    status: Status
    reasons: tuple[str, ...]
    units: tuple[Unit, ...]
    window: Window
    band: Band
    signal_plane: SignalPlane


def signal_plane_for(measured_channel: str) -> SignalPlane:
    """Map the declared measured channel onto its persisted signal plane."""
    return (
        SignalPlane.CH1_SCOPE_INPUT
        if measured_channel == "ch1"
        else SignalPlane.CH2_TRANSFORMER_SECONDARY
    )


def zero_support() -> Support:
    """Empty support for a family that computed nothing."""
    return Support(
        start_s=0.0, end_s=0.0, duration_s=0.0, sample_count=0,
        observation_count=0, missing_count=0, stored_count=0, selection_rule="all"
    )  # fmt: skip


def family_envelope(
    spec: FamilySpec,
    support: Support,
    *,
    array_refs: tuple[ArrayReference, ...] = (),
    table_refs: tuple[TableReference, ...] = (),
    comparison_summary: tuple[ScalarSummary, ...] = (),
) -> FamilyResult:
    """Build one envelope so every family carries the same declared invariant."""
    return FamilyResult(
        family_id=spec.family_id, status=spec.status, reason_codes=spec.reasons,
        method=spec.method, method_version=spec.method_version,
        units=spec.units, window=spec.window, band=spec.band, filter=NO_FILTER,
        n=support.observation_count, support=support, missing_rule=MISSING_RULE,
        qc=Qc(passed=spec.status is Status.AVAILABLE, reason_codes=spec.reasons),
        signal_plane=spec.signal_plane, inference=Inference(),
        array_refs=array_refs, table_refs=table_refs, comparison_summary=comparison_summary
    )  # fmt: skip


def not_computed_family(family: CharacterizationFamily, band: Band) -> FamilyResult:
    """One not-yet-implemented family envelope carrying its declared method."""
    return family_envelope(
        FamilySpec(
            family_id=family.id,
            method=family.method,
            method_version=family.method_version,
            status=Status.UNAVAILABLE,
            reasons=NOT_COMPUTED,
            units=PLACEHOLDER_UNITS,
            window=PLACEHOLDER_WINDOW,
            band=band,
            signal_plane=SignalPlane.CH1_SCOPE_INPUT,
        ),
        zero_support(),
    )
