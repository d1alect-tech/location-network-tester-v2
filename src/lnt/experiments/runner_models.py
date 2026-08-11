"""Persisted types for safe experiment protocol execution."""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class _FrozenModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class ProtocolRunMode(StrEnum):
    """Whether acquisition uses real hardware or a simulator seam."""

    REAL = "real"
    SIMULATOR = "simulator"


class ProtocolRunStatus(StrEnum):
    """Persisted protocol state visible to a runtime/API boundary."""

    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ConfirmationRecord(_FrozenModel):
    """Audit identity for one physical intervention acknowledgement."""

    actor: str = Field(min_length=1)
    auto_confirmed: bool


class FindingRecord(_FrozenModel):
    """Persistable form of a T14 preflight finding."""

    severity: str
    code: str
    message_ru: str
    recovery_action_ru: str


class PlannedMember(_FrozenModel):
    """Protocol-declared assignment captured before execution starts."""

    protocol_order: int = Field(ge=1)
    condition_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    block_key: str | None
    pairing_key: str | None


class CompletedMember(_FrozenModel):
    """Completed evidence with explicit assignment and QC output."""

    protocol_order: int = Field(ge=1)
    condition_id: str = Field(min_length=1)
    block_key: str | None
    pairing_key: str | None
    session_id: str = Field(min_length=1)
    storage_ref: str = Field(min_length=1)
    artifact_refs: tuple[str, ...]
    confirmation: ConfirmationRecord
    qc_recommendations: tuple[str, ...]


class ProtocolRunRecord(_FrozenModel):
    """Latest restartable snapshot; each replacement also produces an event."""

    schema_version: int = 1
    run_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    mode: ProtocolRunMode
    status: ProtocolRunStatus
    revision: int = Field(ge=1)
    seed: int | None
    generated_order: tuple[int, ...]
    plan: tuple[PlannedMember, ...]
    next_member_index: int = Field(ge=0)
    completed_members: tuple[CompletedMember, ...]
    requested_physical_change: str | None = None
    current_confirmation: ConfirmationRecord | None = None
    current_preflight: tuple[FindingRecord, ...] = ()


class ProtocolRunEvent(_FrozenModel):
    """Append-only transition record with the complete resulting snapshot."""

    revision: int = Field(ge=1)
    transition: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    snapshot: ProtocolRunRecord
