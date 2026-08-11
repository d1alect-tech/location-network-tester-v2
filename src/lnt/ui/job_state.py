"""Неизменяемые снимки задач панели и легальные переходы статусов."""

# ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: исходник полностью утрачен при сбое диска;
# восстановлен по tests/test_ui_job_state.py и модулям-потребителям.

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final

from lnt.ui.models import JobKind, JobStage, JobStatus

SCHEMA_VERSION: Final = 1

_TERMINAL_STATUSES: Final = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.CANCELLED, JobStatus.FAILED},
)
_ALLOWED_TRANSITIONS: Final[Mapping[JobStatus, frozenset[JobStatus]]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLING}),
    JobStatus.RUNNING: frozenset(
        {JobStatus.CANCELLING, JobStatus.SUCCEEDED, JobStatus.FAILED},
    ),
    JobStatus.CANCELLING: frozenset(
        {JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED},
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSnapshot:
    """Версионированный снимок состояния одной задачи панели."""

    schema_version: int
    version: int
    job_id: str
    kind: JobKind
    status: JobStatus
    stage: JobStage
    series_index: int | None
    series_total: int | None
    written_sessions: tuple[str, ...]
    result: Mapping[str, object] | None
    error_code: str | None
    error_message: str | None

    def is_terminal(self) -> bool:
        """Сообщает, достигла ли задача терминального статуса."""
        return self.status in _TERMINAL_STATUSES

    def to_payload(self) -> dict[str, object]:
        """Возвращает канонический JSON-совместимый снимок для API панели."""
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "job_id": self.job_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "stage": self.stage.value,
            "series_index": self.series_index,
            "series_total": self.series_total,
            "written_sessions": list(self.written_sessions),
            "result": dict(self.result) if self.result is not None else None,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


def new_job(kind: JobKind) -> JobSnapshot:
    """Создаёт поставленную в очередь задачу с уникальным идентификатором."""
    return JobSnapshot(
        schema_version=SCHEMA_VERSION,
        version=1,
        job_id=uuid.uuid4().hex,
        kind=kind,
        status=JobStatus.QUEUED,
        stage=JobStage.QUEUED,
        series_index=None,
        series_total=None,
        written_sessions=(),
        result=None,
        error_code=None,
        error_message=None,
    )


def advance(  # noqa: PLR0913 -- единая точка перехода: все поля снимка kw-only
    snapshot: JobSnapshot,
    *,
    status: JobStatus | None = None,
    stage: JobStage | None = None,
    series_index: int | None = None,
    series_total: int | None = None,
    add_session: str | None = None,
    result: Mapping[str, object] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> JobSnapshot:
    """Возвращает следующий снимок, проверяя легальность перехода статуса."""
    if snapshot.is_terminal():
        raise ValueError(f"задача уже завершена: {snapshot.status.value}")
    next_status = snapshot.status if status is None else status
    if (
        status is not None
        and status is not snapshot.status
        and status not in _ALLOWED_TRANSITIONS[snapshot.status]
    ):
        raise ValueError(f"недопустимый переход {snapshot.status.value} -> {status.value}")
    if next_status is JobStatus.SUCCEEDED and result is None:
        raise ValueError("успешное завершение требует результат")
    if result is not None and next_status is not JobStatus.SUCCEEDED:
        raise ValueError("результат допустим только при успешном завершении")
    if next_status is JobStatus.FAILED and error_code is None:
        raise ValueError("отказ требует код ошибки")
    written = (
        snapshot.written_sessions
        if add_session is None
        else (*snapshot.written_sessions, add_session)
    )
    return replace(
        snapshot,
        version=snapshot.version + 1,
        status=next_status,
        stage=snapshot.stage if stage is None else stage,
        series_index=snapshot.series_index if series_index is None else series_index,
        series_total=snapshot.series_total if series_total is None else series_total,
        written_sessions=written,
        result=snapshot.result if result is None else result,
        error_code=snapshot.error_code if error_code is None else error_code,
        error_message=snapshot.error_message if error_message is None else error_message,
    )
