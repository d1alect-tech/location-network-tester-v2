"""SQLite-хранилище снимков и неизменяемой истории задач.

Retention запускается только явно: сохраняются последние N терминальных задач,
а результаты, ссылающиеся на записанные сессии, не удаляются никогда.

Фасад: чистые кодеки живут в ``store_codecs``, правила переходов — в
``store_transitions``; здесь остаются только транзакции над базой.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

from lnt.runtime.migrations import apply_migrations
from lnt.runtime.store_codecs import _dump_progress, _dump_snapshot, _load_snapshot
from lnt.runtime.store_transitions import (
    _ALLOWED,
    _TERMINAL,
    _TRACEBACK_MARKER,
    _compact_error,
    _next_statuses,
)
from lnt.ui.job_state import JobSnapshot, advance
from lnt.ui.models import JobStage, JobStatus

__all__ = [
    "_ALLOWED",
    "_TERMINAL",
    "_TRACEBACK_MARKER",
    "IllegalJobTransitionError",
    "JobEvent",
    "JobStore",
    "_compact_error",
    "_dump_progress",
    "_dump_snapshot",
    "_load_snapshot",
    "_next_statuses",
]


@dataclass(frozen=True, slots=True)
class IllegalJobTransitionError(Exception):
    """Запрошен запрещённый или повторный переход состояния."""

    job_id: str
    current: JobStatus
    requested: JobStatus

    @override
    def __str__(self) -> str:
        """Возвращает компактное русское описание конфликта."""
        return f"недопустимый переход задачи {self.job_id}: {self.current} -> {self.requested}"


@dataclass(frozen=True, slots=True)
class JobEvent:
    """Минимальная запись в неизменяемом журнале задачи."""

    version: int
    status: JobStatus


class JobStore:
    """Выполняет короткие транзакции над отдельной runtime-базой."""

    def __init__(self, path: Path) -> None:
        """Открывает или создаёт хранилище по внедрённому пути."""
        self.path: Path = path
        apply_migrations(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def create(
        self,
        snapshot: JobSnapshot,
        *,
        input_reference: Mapping[str, object] | None = None,
    ) -> None:
        """Создаёт уникальную queued-задачу и её первое событие."""
        payload = _dump_snapshot(snapshot)
        progress = _dump_progress(snapshot)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO jobs(
                    job_id, operation_kind, status, version, input_reference,
                    result_reference, progress, error_code, error_message,
                    created_utc, updated_utc
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL,
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))""",
                (
                    snapshot.job_id,
                    snapshot.kind.value,
                    snapshot.status.value,
                    snapshot.version,
                    json.dumps(input_reference, ensure_ascii=False) if input_reference else None,
                    progress,
                ),
            )
            self._append_event(connection, snapshot, payload)

    def get(self, job_id: str) -> JobSnapshot:
        """Возвращает последний долговечный снимок задачи."""
        with self._connect() as connection:
            row = connection.execute(
                """SELECT snapshot FROM job_events
                WHERE job_id = ? ORDER BY version DESC LIMIT 1""",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _load_snapshot(str(row[0]))

    def events(self, job_id: str) -> tuple[JobEvent, ...]:
        """Возвращает журнал переходов в порядке версий."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT version, status FROM job_events WHERE job_id = ? ORDER BY version",
                (job_id,),
            ).fetchall()
        return tuple(JobEvent(version=int(row[0]), status=JobStatus(str(row[1]))) for row in rows)

    def list_snapshots(self, *, page_size: int, offset: int = 0) -> tuple[JobSnapshot, ...]:
        """Возвращает bounded страницу последних снимков от новых к старым."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT e.snapshot FROM jobs j
                JOIN job_events e ON e.job_id=j.job_id AND e.version=j.version
                ORDER BY j.queue_order DESC LIMIT ? OFFSET ?""",
                (page_size, offset),
            ).fetchall()
        return tuple(_load_snapshot(str(row[0])) for row in rows)

    def event_snapshots(
        self,
        job_id: str,
        *,
        page_size: int,
        after_version: int = 0,
    ) -> tuple[JobSnapshot, ...]:
        """Переигрывает bounded часть durable журнала после указанной версии."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT snapshot FROM job_events WHERE job_id=? AND version>?
                ORDER BY version LIMIT ?""",
                (job_id, after_version, page_size),
            ).fetchall()
        return tuple(_load_snapshot(str(row[0])) for row in rows)

    def record(self, snapshot: JobSnapshot) -> None:
        """Атомарно записывает следующий легальный снимок и событие."""
        current = self.get(snapshot.job_id)
        valid_version = snapshot.version == current.version + 1
        if not valid_version or snapshot.status not in _next_statuses(current):
            raise IllegalJobTransitionError(snapshot.job_id, current.status, snapshot.status)
        message = _compact_error(snapshot.error_code, snapshot.error_message)
        stored = (
            snapshot
            if message == snapshot.error_message
            else replace(snapshot, error_message=message)
        )
        with self._connect() as connection:
            connection.execute(
                """UPDATE jobs SET status = ?, version = ?, result_reference = ?,
                progress = ?, error_code = ?, error_message = ?,
                updated_utc = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE job_id = ?""",
                (
                    stored.status.value,
                    stored.version,
                    json.dumps(stored.result, ensure_ascii=False) if stored.result else None,
                    _dump_progress(stored),
                    stored.error_code,
                    stored.error_message,
                    stored.job_id,
                ),
            )
            self._append_event(connection, stored, _dump_snapshot(stored))

    def transition(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> JobSnapshot:
        """Строит и сохраняет переход с компактной ошибкой."""
        current = self.get(job_id)
        if status not in _ALLOWED.get(current.status, frozenset()):
            raise IllegalJobTransitionError(job_id, current.status, status)
        updated = advance(
            current,
            status=status,
            stage=JobStage.DONE if status in _TERMINAL else None,
            error_code=error_code,
            error_message=_compact_error(error_code, error_message),
        )
        self.record(updated)
        return self.get(job_id)

    def interrupt_nonterminal(self) -> tuple[str, ...]:
        """Завершает оставшиеся после смерти процесса задачи как interrupted."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT job_id FROM jobs WHERE status NOT IN (?, ?, ?, ?) ORDER BY queue_order",
                tuple(status.value for status in _TERMINAL),
            ).fetchall()
        interrupted = tuple(str(row[0]) for row in rows)
        for job_id in interrupted:
            self.transition(
                job_id,
                JobStatus.INTERRUPTED,
                error_code="process_interrupted",
                error_message="задача прервана перезапуском приложения",
            )
        return interrupted

    def prune_unreferenced_terminal(self, *, keep: int) -> tuple[str, ...]:
        """Удаляет старые terminal без ссылок, сохраняя последние ``keep``."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT job_id, progress FROM jobs WHERE status IN (?, ?, ?, ?)
                ORDER BY queue_order DESC""",
                tuple(status.value for status in _TERMINAL),
            ).fetchall()
            candidates = [
                str(row[0]) for row in rows if not json.loads(str(row[1]))["written_sessions"]
            ]
            removed = tuple(reversed(candidates[keep:]))
            connection.executemany(
                "DELETE FROM jobs WHERE job_id = ?",
                ((job_id,) for job_id in removed),
            )
        return removed

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        snapshot: JobSnapshot,
        payload: str,
    ) -> None:
        connection.execute(
            """INSERT INTO job_events(job_id, version, status, snapshot, created_utc)
            VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))""",
            (snapshot.job_id, snapshot.version, snapshot.status.value, payload),
        )
