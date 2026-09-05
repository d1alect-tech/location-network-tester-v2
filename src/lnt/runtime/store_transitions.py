"""Чистые правила переходов задач (лист store.py, issue #8)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.ui.job_state import JobSnapshot

from lnt.ui.models import JobStatus

__all__ = [
    "_ALLOWED",
    "_TERMINAL",
    "_TRACEBACK_MARKER",
    "_compact_error",
    "_next_statuses",
]

_TRACEBACK_MARKER: Final = "Traceback (most recent call last)"
_TERMINAL: Final = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.INTERRUPTED},
)
_ALLOWED: Final[Mapping[JobStatus, frozenset[JobStatus]]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLING, JobStatus.INTERRUPTED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.CANCELLING,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.INTERRUPTED,
        },
    ),
    JobStatus.CANCELLING: frozenset(
        {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.INTERRUPTED},
    ),
}


def _next_statuses(snapshot: JobSnapshot) -> frozenset[JobStatus]:
    return frozenset({snapshot.status, *_ALLOWED.get(snapshot.status, frozenset())})


def _compact_error(code: str | None, message: str | None) -> str | None:
    if message is None:
        return None
    if _TRACEBACK_MARKER in message or code == "internal_error":
        return "внутренняя ошибка"
    return message[:500]
