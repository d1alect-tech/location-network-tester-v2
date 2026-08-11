import json
import re
from typing import Final

import pytest

from lnt.ui.job_state import advance, new_job
from lnt.ui.models import JobKind, JobStage, JobStatus

EXPECTED_PAYLOAD_KEYS: Final = {
    "schema_version",
    "version",
    "job_id",
    "kind",
    "status",
    "stage",
    "series_index",
    "series_total",
    "written_sessions",
    "result",
    "error_code",
    "error_message",
}


class TestNewJob:
    def test_new_job_has_queued_initial_state_and_unique_hex_id(self) -> None:
        first = new_job(JobKind.SIMULATE)
        second = new_job(JobKind.SIMULATE)

        assert (
            first.schema_version,
            first.version,
            first.kind,
            first.status,
            first.stage,
            first.series_index,
            first.series_total,
            first.written_sessions,
            first.result,
            first.error_code,
            first.error_message,
        ) == (
            1,
            1,
            JobKind.SIMULATE,
            JobStatus.QUEUED,
            JobStage.QUEUED,
            None,
            None,
            (),
            None,
            None,
            None,
        )
        assert re.fullmatch(r"[0-9a-f]{32}", first.job_id)
        assert first.job_id != second.job_id
        assert first.is_terminal() is False


class TestLegalTransitions:
    def test_full_series_job_succeeds_with_monotonic_versions(self) -> None:
        queued = new_job(JobKind.SIMULATE)
        running = advance(
            queued,
            status=JobStatus.RUNNING,
            stage=JobStage.SIMULATING,
            series_index=1,
            series_total=2,
        )
        first_written = advance(running, add_session="session-1")
        second_written = advance(first_written, series_index=2, add_session="session-2")
        succeeded = advance(
            second_written,
            status=JobStatus.SUCCEEDED,
            stage=JobStage.DONE,
            result={"session_count": 2},
        )

        snapshots = (queued, running, first_written, second_written, succeeded)
        assert [snapshot.version for snapshot in snapshots] == [1, 2, 3, 4, 5]
        assert succeeded.written_sessions == ("session-1", "session-2")
        assert (succeeded.series_index, succeeded.series_total) == (2, 2)
        assert succeeded.result == {"session_count": 2}
        assert succeeded.is_terminal() is True

    def test_running_job_can_be_cancelled(self) -> None:
        queued = new_job(JobKind.CAPTURE)
        running = advance(queued, status=JobStatus.RUNNING, stage=JobStage.CAPTURING)
        cancelling = advance(running, status=JobStatus.CANCELLING)

        cancelled = advance(cancelling, status=JobStatus.CANCELLED, stage=JobStage.DONE)

        assert cancelled.status is JobStatus.CANCELLED
        assert cancelled.version == 4
        assert cancelled.is_terminal() is True

    def test_queued_job_can_enter_cancelling_before_worker_starts(self) -> None:
        queued = new_job(JobKind.ANALYZE)

        cancelling = advance(queued, status=JobStatus.CANCELLING)

        assert cancelling.status is JobStatus.CANCELLING
        assert cancelling.version == 2

    def test_cancelling_job_can_succeed_after_final_series_completes(self) -> None:
        running = advance(new_job(JobKind.SIMULATE), status=JobStatus.RUNNING)
        cancelling = advance(running, status=JobStatus.CANCELLING)

        succeeded = advance(cancelling, status=JobStatus.SUCCEEDED, result={"complete": True})

        assert succeeded.status is JobStatus.SUCCEEDED
        assert succeeded.result == {"complete": True}

    @pytest.mark.parametrize(
        "error_code",
        ["input_error", "device_not_found", "internal_error"],
    )
    def test_running_job_can_fail_with_supported_error_code(self, error_code: str) -> None:
        queued = new_job(JobKind.DEVICE_CHECK)
        running = advance(queued, status=JobStatus.RUNNING, stage=JobStage.CHECKING_DEVICE)

        failed = advance(
            running,
            status=JobStatus.FAILED,
            stage=JobStage.DONE,
            error_code=error_code,
            error_message="проверка завершилась ошибкой",
        )

        assert failed.error_code == error_code
        assert failed.error_message == "проверка завершилась ошибкой"
        assert failed.result is None
        assert failed.is_terminal() is True


class TestIllegalTransitions:
    def test_advance_after_success_raises(self) -> None:
        running = advance(new_job(JobKind.SELFTEST), status=JobStatus.RUNNING)
        succeeded = advance(running, status=JobStatus.SUCCEEDED, result={"ok": True})

        with pytest.raises(ValueError, match="заверш"):
            advance(succeeded, stage=JobStage.DONE)

    @pytest.mark.parametrize(
        "terminal_status",
        [JobStatus.SUCCEEDED, JobStatus.CANCELLED, JobStatus.FAILED],
    )
    def test_queued_job_cannot_finish_directly(self, terminal_status: JobStatus) -> None:
        queued = new_job(JobKind.COMPARE)

        with pytest.raises(ValueError, match="переход"):
            advance(queued, status=terminal_status)

    def test_success_requires_result(self) -> None:
        running = advance(new_job(JobKind.ANALYZE), status=JobStatus.RUNNING)

        with pytest.raises(ValueError, match="результат"):
            advance(running, status=JobStatus.SUCCEEDED)

    def test_failure_requires_error_code(self) -> None:
        running = advance(new_job(JobKind.CAPTURE), status=JobStatus.RUNNING)

        with pytest.raises(ValueError, match="код"):
            advance(running, status=JobStatus.FAILED, error_message="ошибка")

    def test_cancelled_job_rejects_result(self) -> None:
        cancelling = advance(new_job(JobKind.SIMULATE), status=JobStatus.CANCELLING)

        with pytest.raises(ValueError, match="результат"):
            advance(cancelling, status=JobStatus.CANCELLED, result={"partial": True})


class TestPayload:
    def test_payload_has_canonical_json_shape(self) -> None:
        queued = new_job(JobKind.SIMULATE)
        running = advance(
            queued,
            status=JobStatus.RUNNING,
            stage=JobStage.SIMULATING,
            series_index=1,
            series_total=1,
            add_session="session-1",
        )
        succeeded = advance(
            running,
            status=JobStatus.SUCCEEDED,
            stage=JobStage.DONE,
            result={"metrics": {"score": 0.75}},
        )

        payload = succeeded.to_payload()

        assert set(payload) == EXPECTED_PAYLOAD_KEYS
        assert payload["kind"] == "simulate"
        assert payload["status"] == "succeeded"
        assert payload["stage"] == "done"
        assert payload["written_sessions"] == ["session-1"]
        assert json.loads(json.dumps(payload)) == payload
