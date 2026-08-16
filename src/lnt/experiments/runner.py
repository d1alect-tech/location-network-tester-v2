"""Safe persisted state machine for guided experiment protocols."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, final, override

from lnt.capture_preflight import FindingSeverity, PreflightFinding
from lnt.comparability import recommend_exclusion
from lnt.experiments.runner_models import (
    CompletedMember,
    ConfirmationRecord,
    FindingRecord,
    PlannedMember,
    ProtocolRunMode,
    ProtocolRunRecord,
    ProtocolRunStatus,
)
from lnt.experiments.runner_store import ProtocolRunStore
from lnt.runtime import OperationClass, OperationScheduler

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.acquisition_quality import AcquisitionQuality
    from lnt.experiments.model import Experiment


@dataclass(frozen=True, slots=True)
class CaptureArtifact:
    """Output of the existing real or simulator capture seam."""

    session_id: str
    storage_ref: str
    artifact_refs: tuple[str, ...]
    quality: AcquisitionQuality


@dataclass(frozen=True, slots=True)
class AutoConfirmationRejectedError(Exception):
    """Real physical interventions can never be auto-confirmed."""

    code: str = "real_intervention_auto_confirmation_forbidden"

    @override
    def __str__(self) -> str:
        return "физическое вмешательство нельзя подтвердить автоматически в реальном режиме"


@dataclass(frozen=True, slots=True)
class RandomizationSeedRequiredError(Exception):
    """A randomized protocol cannot start without a persisted seed."""

    code: str = "protocol_randomization_seed_required"

    @override
    def __str__(self) -> str:
        return "для рандомизации протокола требуется сохранённый seed"


@final
class ProtocolRunner:
    """Advances only at persisted boundaries and serializes hardware work."""

    def __init__(
        self,
        *,
        store: ProtocolRunStore,
        scheduler: OperationScheduler,
        preflight: Callable[[], tuple[PreflightFinding, ...]],
        capture: Callable[[int], CaptureArtifact],
    ) -> None:
        """Bind injected durable, scheduling, preflight, and capture seams."""
        self.store = store
        self._scheduler = scheduler
        self._preflight = preflight
        self._capture = capture

    def start(
        self,
        *,
        run_id: str,
        experiment: Experiment,
        mode: ProtocolRunMode,
        seed: int | None = None,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> ProtocolRunRecord:
        """Build and persist an explicit plan, then advance to a safe boundary."""
        declared = tuple(member.order for member in experiment.members)
        randomized = "random" in experiment.protocol.order_scheme.casefold()
        if randomized and seed is None:
            raise RandomizationSeedRequiredError
        generated = list(declared)
        if randomized:
            random.Random(seed).shuffle(generated)  # noqa: S311 - scientific reproducibility
        steps = {step.order: step for step in experiment.steps}
        members = {member.order: member for member in experiment.members}
        plan = tuple(
            PlannedMember(
                protocol_order=order,
                condition_id=steps[order].condition_id,
                instruction=steps[order].instruction,
                block_key=members[order].block_key,
                pairing_key=members[order].pairing_key,
            )
            for order in generated
        )
        record = self.store.create(
            ProtocolRunRecord(
                run_id=run_id,
                experiment_id=experiment.experiment_id,
                mode=mode,
                status=ProtocolRunStatus.RUNNING,
                revision=1,
                seed=seed if randomized else None,
                generated_order=tuple(generated),
                plan=plan,
                next_member_index=0,
                completed_members=(),
            )
        )
        return self._advance(record, is_cancelled)

    def resume(
        self, run_id: str, *, is_cancelled: Callable[[], bool] = lambda: False
    ) -> ProtocolRunRecord:
        """Resume running work but preserve an awaiting-confirmation boundary."""
        record = self.store.load(run_id)
        if record.status is ProtocolRunStatus.RUNNING:
            return self._advance(record, is_cancelled)
        return record

    def confirm(
        self,
        run_id: str,
        *,
        actor: str,
        auto_confirm: bool = False,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> ProtocolRunRecord:
        """Record explicit readiness and only then permit capture."""
        record = self.store.load(run_id)
        if record.mode is ProtocolRunMode.REAL and auto_confirm:
            raise AutoConfirmationRejectedError
        if record.status is not ProtocolRunStatus.AWAITING_CONFIRMATION:
            return record
        confirmation = ConfirmationRecord(actor=actor, auto_confirmed=auto_confirm)
        confirmed = self._record(
            record.model_copy(
                update={
                    "status": ProtocolRunStatus.RUNNING,
                    "current_confirmation": confirmation,
                }
            ),
            "intervention_confirmed",
            actor,
        )
        return self._finish_member(confirmed, is_cancelled)

    def close(self) -> None:
        """Release scheduler executors after all submitted boundaries finish."""
        self._scheduler.close()

    def _advance(
        self, record: ProtocolRunRecord, is_cancelled: Callable[[], bool]
    ) -> ProtocolRunRecord:
        if record.next_member_index >= len(record.plan):
            return self._record(
                record.model_copy(update={"status": ProtocolRunStatus.COMPLETED}), "run_completed"
            )
        if is_cancelled():
            return self._record(
                record.model_copy(update={"status": ProtocolRunStatus.CANCELLED}), "run_cancelled"
            )
        findings = self._scheduler.submit(OperationClass.HARDWARE, self._preflight).result()
        preflight_done = self._record(
            record.model_copy(
                update={"current_preflight": tuple(_finding(item) for item in findings)}
            ),
            "preflight_completed",
        )
        member = preflight_done.plan[preflight_done.next_member_index]
        requested = self._record(
            preflight_done.model_copy(
                update={
                    "status": ProtocolRunStatus.AWAITING_CONFIRMATION,
                    "requested_physical_change": member.instruction,
                }
            ),
            "intervention_requested",
        )
        if requested.mode is ProtocolRunMode.SIMULATOR:
            return self.confirm(
                requested.run_id,
                actor="simulator",
                auto_confirm=True,
                is_cancelled=is_cancelled,
            )
        return requested

    def _finish_member(
        self, record: ProtocolRunRecord, is_cancelled: Callable[[], bool]
    ) -> ProtocolRunRecord:
        member = record.plan[record.next_member_index]
        artifact = self._scheduler.submit(
            OperationClass.HARDWARE, lambda: self._capture(member.protocol_order)
        ).result()
        captured = self._record(record, "capture_completed")
        assigned = self._record(captured, "assignment_recorded")
        findings = tuple(_preflight(item) for item in assigned.current_preflight)
        recommendations = recommend_exclusion(
            member_id=artifact.session_id,
            quality=artifact.quality,
            preflight_findings=findings,
        )
        qc_done = self._record(assigned, "qc_completed")
        confirmation = qc_done.current_confirmation
        if confirmation is None:
            raise ProtocolStateError("confirmation_missing")
        completed = CompletedMember(
            protocol_order=member.protocol_order,
            condition_id=member.condition_id,
            block_key=member.block_key,
            pairing_key=member.pairing_key,
            session_id=artifact.session_id,
            storage_ref=artifact.storage_ref,
            artifact_refs=artifact.artifact_refs,
            confirmation=confirmation,
            qc_recommendations=tuple(item.reason_code for item in recommendations),
        )
        boundary = self._record(
            qc_done.model_copy(
                update={
                    "next_member_index": qc_done.next_member_index + 1,
                    "completed_members": (*qc_done.completed_members, completed),
                    "requested_physical_change": None,
                    "current_confirmation": None,
                    "current_preflight": (),
                }
            ),
            "member_completed",
        )
        return self._advance(boundary, is_cancelled)

    def _record(
        self, record: ProtocolRunRecord, transition: str, actor: str = "system"
    ) -> ProtocolRunRecord:
        return self.store.record(
            record.model_copy(update={"revision": record.revision + 1}),
            transition=transition,
            actor=actor,
        )


def _finding(source: PreflightFinding) -> FindingRecord:
    return FindingRecord(
        severity=source.severity.value,
        code=source.code,
        message_ru=source.message_ru,
        recovery_action_ru=source.recovery_action_ru,
    )


def _preflight(source: FindingRecord) -> PreflightFinding:
    return PreflightFinding(
        severity=FindingSeverity(source.severity),
        code=source.code,
        message_ru=source.message_ru,
        recovery_action_ru=source.recovery_action_ru,
    )


@dataclass(frozen=True, slots=True)
class ProtocolStateError(Exception):
    """Persisted state violates a runner invariant."""

    code: str

    @override
    def __str__(self) -> str:
        return f"запуск протокола содержит недопустимое состояние: {self.code}"


__all__ = [
    "AutoConfirmationRejectedError",
    "CaptureArtifact",
    "ProtocolRunMode",
    "ProtocolRunStatus",
    "ProtocolRunStore",
    "ProtocolRunner",
    "RandomizationSeedRequiredError",
]
