"""Top-level immutable characterization bundle models."""

from __future__ import annotations

from dataclasses import dataclass

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.ids import FAMILY_IDS
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
    validate_unit_name,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ArrayReference:
    """Typed reference to one finite NPZ numeric member."""

    array_id: str
    role: str
    unit: Unit
    dtype: str
    shape: tuple[int, ...]
    validity_mask_id: str | None = None
    offsets_id: str | None = None

    def __post_init__(self) -> None:
        """Validate identity, shape, and auxiliary reference separation."""
        validate_unit_name(self.array_id, self.unit)
        if (
            not self.role
            or not self.dtype
            or not self.shape
            or any(size < 0 for size in self.shape)
            or self.array_id in {self.validity_mask_id, self.offsets_id}
        ):
            raise CharacterizationError("array_reference", "invalid array reference")


@dataclass(frozen=True, slots=True, kw_only=True)
class TableReference:
    """Typed reference to one table block."""

    table_id: str
    role: str

    def __post_init__(self) -> None:
        """Validate nonempty table identity and role."""
        if not self.table_id or not self.role:
            raise CharacterizationError("table_reference", "invalid table reference")


@dataclass(frozen=True, slots=True, kw_only=True)
class FamilyResult:
    """One of the exact eighteen family result envelopes."""

    family_id: str
    status: Status
    reason_codes: tuple[str, ...]
    method: str
    method_version: int
    units: tuple[Unit, ...]
    window: Window
    band: Band
    filter: Filter
    n: int
    support: Support
    missing_rule: str
    qc: Qc
    signal_plane: SignalPlane
    inference: Inference
    array_refs: tuple[ArrayReference, ...]
    table_refs: tuple[TableReference, ...]
    comparison_summary: tuple[ScalarSummary, ...]

    def __post_init__(self) -> None:
        """Enforce status, support, and missingness invariants."""
        outputs = bool(self.array_refs or self.table_refs or self.comparison_summary)
        reasons_valid = bool(self.reason_codes) and all(self.reason_codes)
        invalid = (
            self.family_id not in FAMILY_IDS
            or not self.method
            or self.method_version <= 0
            or not self.units
            or len(set(self.units)) != len(self.units)
            or self.n != self.support.observation_count
            or self.n < 0
            or not self.missing_rule
            or len(set(self.reason_codes)) != len(self.reason_codes)
            or self.qc.reason_codes != self.reason_codes
            or self.qc.passed != (self.status is Status.AVAILABLE)
            or (
                self.status is Status.PARTIAL
                and any(reference.validity_mask_id is None for reference in self.array_refs)
            )
            or (self.status is Status.AVAILABLE and (self.reason_codes or not outputs))
            or (self.status is Status.PARTIAL and (not reasons_valid or not outputs))
            or (self.status is Status.UNAVAILABLE and (not reasons_valid or outputs))
        )
        if invalid:
            raise CharacterizationError(
                "status_invariant", f"invalid family result {self.family_id}"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationBundle:
    """Schema-1 result bundle containing all families exactly once."""

    families: tuple[FamilyResult, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        """Require schema one and all exact ordered family IDs."""
        if self.schema_version != 1:
            raise CharacterizationError("schema_version", "unsupported schema version")
        if tuple(item.family_id for item in self.families) != FAMILY_IDS:
            raise CharacterizationError("family_order", "exactly 18 ordered families are required")
