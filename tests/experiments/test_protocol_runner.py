from pathlib import Path
from threading import Event

import pytest

from lnt.acquisition_quality import AcquisitionQuality
from lnt.experiments.model import Experiment
from lnt.experiments.runner import (
    AutoConfirmationRejectedError,
    CaptureArtifact,
    ProtocolRunMode,
    ProtocolRunner,
    ProtocolRunStatus,
    ProtocolRunStore,
)
from lnt.experiments.values import Protocol, ProtocolStep
from lnt.runtime import OperationScheduler

from .factories import make_experiment


class FakeCapture:
    def __init__(self, root: Path) -> None:
        self.root: Path = root
        self.calls: int = 0

    def __call__(self, member_order: int) -> CaptureArtifact:
        self.calls += 1
        session_id = f"captured-{member_order}"
        session_dir = self.root / session_id
        session_dir.mkdir(parents=True)
        return CaptureArtifact(
            session_id=session_id,
            storage_ref=session_id,
            artifact_refs=(f"{session_id}/manifest.json",),
            quality=AcquisitionQuality(
                quality_thresholds_version=1,
                channels=(),
                findings=(),
                maximum_callback_gap_s=0.0,
                short_block_count=0,
            ),
        )


def _runner(tmp_path: Path, *, capture: FakeCapture | None = None) -> ProtocolRunner:
    return ProtocolRunner(
        store=ProtocolRunStore(tmp_path / "runs"),
        scheduler=OperationScheduler(cpu_workers=1, cpu_queue_limit=1),
        preflight=lambda: (),
        capture=capture or FakeCapture(tmp_path / "sessions"),
    )


def _aba_experiment() -> Experiment:
    source = make_experiment(Protocol.ABA)
    return source.model_copy(
        update={
            "steps": (
                ProtocolStep(order=1, condition_id="condition-a", instruction="Подключите A"),
                ProtocolStep(order=2, condition_id="condition-b", instruction="Подключите B"),
                ProtocolStep(order=3, condition_id="condition-a", instruction="Верните A"),
            ),
            "members": (
                *source.members,
                source.members[0].model_copy(update={"session_id": "session-a2", "order": 3}),
            ),
        }
    )


def test_simulator_completes_aba_with_explicit_assignments_and_artifacts(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    result = runner.start(
        run_id="aba-run", experiment=_aba_experiment(), mode=ProtocolRunMode.SIMULATOR
    )

    assert result.status is ProtocolRunStatus.COMPLETED
    assert [member.condition_id for member in result.completed_members] == [
        "condition-a",
        "condition-b",
        "condition-a",
    ]
    assert all(member.artifact_refs for member in result.completed_members)
    assert all(member.confirmation.auto_confirmed for member in result.completed_members)
    assert {event.transition for event in runner.store.events("aba-run")} >= {
        "preflight_completed",
        "intervention_requested",
        "intervention_confirmed",
        "capture_completed",
        "assignment_recorded",
        "qc_completed",
        "member_completed",
    }


def test_repeated_blocks_complete_in_declared_order(tmp_path: Path) -> None:
    source = make_experiment(Protocol.REPEATED_BLOCKS)
    steps = tuple(
        ProtocolStep(order=index, condition_id=condition, instruction=f"Установите {condition}")
        for index, condition in enumerate(
            ("condition-a", "condition-b", "condition-a", "condition-b"), start=1
        )
    )
    members = tuple(
        source.members[(index - 1) % 2].model_copy(
            update={
                "session_id": f"planned-{index}",
                "order": index,
                "block_key": f"block-{(index + 1) // 2}",
            }
        )
        for index in range(1, 5)
    )
    experiment = source.model_copy(update={"steps": steps, "members": members})

    result = _runner(tmp_path).start(
        run_id="blocks", experiment=experiment, mode=ProtocolRunMode.SIMULATOR
    )

    assert [member.protocol_order for member in result.completed_members] == [1, 2, 3, 4]
    assert [member.block_key for member in result.completed_members] == [
        "block-1",
        "block-1",
        "block-2",
        "block-2",
    ]


def test_restart_resumes_exact_awaiting_confirmation_boundary(tmp_path: Path) -> None:
    capture = FakeCapture(tmp_path / "sessions")
    first = _runner(tmp_path, capture=capture)
    pending = first.start(run_id="restart", experiment=_aba_experiment(), mode=ProtocolRunMode.REAL)
    first.close()

    resumed_runner = _runner(tmp_path, capture=capture)
    resumed = resumed_runner.resume("restart")

    assert pending.status is ProtocolRunStatus.AWAITING_CONFIRMATION
    assert resumed == pending
    assert capture.calls == 0


def test_cancellation_between_members_keeps_completed_members(tmp_path: Path) -> None:
    cancelled = Event()
    capture = FakeCapture(tmp_path / "sessions")

    def capture_then_cancel(order: int) -> CaptureArtifact:
        artifact = capture(order)
        cancelled.set()
        return artifact

    runner = ProtocolRunner(
        store=ProtocolRunStore(tmp_path / "runs"),
        scheduler=OperationScheduler(cpu_workers=1, cpu_queue_limit=1),
        preflight=lambda: (),
        capture=capture_then_cancel,
    )

    result = runner.start(
        run_id="cancel",
        experiment=_aba_experiment(),
        mode=ProtocolRunMode.SIMULATOR,
        is_cancelled=cancelled.is_set,
    )

    assert result.status is ProtocolRunStatus.CANCELLED
    assert len(result.completed_members) == 1
    assert result.completed_members[0].protocol_order == 1


def test_real_mode_rejects_auto_confirmation_without_capture(tmp_path: Path) -> None:
    capture = FakeCapture(tmp_path / "sessions")
    runner = _runner(tmp_path, capture=capture)
    runner.start(run_id="safe", experiment=_aba_experiment(), mode=ProtocolRunMode.REAL)

    with pytest.raises(AutoConfirmationRejectedError) as raised:
        runner.confirm("safe", actor="operator", auto_confirm=True)

    assert raised.value.code == "real_intervention_auto_confirmation_forbidden"
    assert "реальном режиме" in str(raised.value)
    assert capture.calls == 0
    assert runner.resume("safe").status is ProtocolRunStatus.AWAITING_CONFIRMATION


def test_unconfirmed_intervention_exposes_requested_change_and_blocks_capture(
    tmp_path: Path,
) -> None:
    capture = FakeCapture(tmp_path / "sessions")
    runner = _runner(tmp_path, capture=capture)

    pending = runner.start(
        run_id="pending", experiment=_aba_experiment(), mode=ProtocolRunMode.REAL
    )

    assert pending.status is ProtocolRunStatus.AWAITING_CONFIRMATION
    assert pending.requested_physical_change == "Подключите A"
    assert capture.calls == 0


def test_randomization_is_reproducible_only_from_persisted_seed(tmp_path: Path) -> None:
    source = _aba_experiment()
    randomized = source.model_copy(
        update={"protocol": source.protocol.model_copy(update={"order_scheme": "randomized"})}
    )
    first = _runner(tmp_path / "one").start(
        run_id="random-1", experiment=randomized, mode=ProtocolRunMode.SIMULATOR, seed=9182
    )
    second = _runner(tmp_path / "two").start(
        run_id="random-2", experiment=randomized, mode=ProtocolRunMode.SIMULATOR, seed=9182
    )

    assert first.generated_order == second.generated_order
    assert first.seed == second.seed == 9182
    assert sorted(first.generated_order) == [1, 2, 3]


def test_qc_recommendations_are_persisted(tmp_path: Path) -> None:
    runner = _runner(tmp_path)

    result = runner.start(run_id="qc", experiment=make_experiment(), mode=ProtocolRunMode.SIMULATOR)

    assert all(member.qc_recommendations == () for member in result.completed_members)
