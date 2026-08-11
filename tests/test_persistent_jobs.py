from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from lnt.catalog.migrations import apply_migrations
from lnt.runtime.store import IllegalJobTransitionError, JobStore
from lnt.ui.job_state import advance, new_job
from lnt.ui.models import JobKind, JobStatus

if TYPE_CHECKING:
    from pathlib import Path


def test_store_persists_jobs_events_and_rejects_duplicate_transition(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")
    queued = new_job(JobKind.SIMULATE)
    store.create(queued, input_reference={"profile": "mains_50hz"})
    running = advance(queued, status=JobStatus.RUNNING)
    store.record(running)

    with pytest.raises(IllegalJobTransitionError):
        store.record(running)

    reopened = JobStore(tmp_path / "runtime.sqlite3")
    assert reopened.get(queued.job_id) == running
    assert [event.status for event in reopened.events(queued.job_id)] == [
        JobStatus.QUEUED,
        JobStatus.RUNNING,
    ]


def test_store_rejects_illegal_direct_terminal_transition(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")
    queued = new_job(JobKind.SIMULATE)
    store.create(queued)

    with pytest.raises(IllegalJobTransitionError):
        store.transition(queued.job_id, JobStatus.FAILED, error_code="input_error")


def test_retention_is_explicit_deterministic_and_preserves_session_outcomes(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")
    completed: list[str] = []
    for index in range(3):
        queued = new_job(JobKind.SIMULATE)
        store.create(queued)
        running = advance(
            queued,
            status=JobStatus.RUNNING,
            add_session=("kept" if index == 0 else None),
        )
        store.record(running)
        store.transition(queued.job_id, JobStatus.FAILED, error_code="input_error")
        completed.append(queued.job_id)

    removed = store.prune_unreferenced_terminal(keep=1)

    assert removed == (completed[1],)
    assert store.get(completed[0]).written_sessions == ("kept",)
    assert store.get(completed[2]).status is JobStatus.FAILED


def test_compact_error_never_stores_traceback(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")
    queued = new_job(JobKind.DEVICE_CHECK)
    store.create(queued)
    store.record(advance(queued, status=JobStatus.RUNNING))

    failed = store.transition(
        queued.job_id,
        JobStatus.FAILED,
        error_code="internal_error",
        error_message="Traceback (most recent call last):\nsecret",
    )

    assert failed.error_message == "внутренняя ошибка"


def test_catalog_database_operations_cannot_touch_runtime_tables(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.sqlite3"
    store = JobStore(runtime_db)
    queued = new_job(JobKind.SIMULATE)
    store.create(queued)
    catalog_db = tmp_path / "catalog.sqlite3"
    apply_migrations(catalog_db)
    with sqlite3.connect(catalog_db) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}

    assert "jobs" not in tables
    assert JobStore(runtime_db).get(queued.job_id).status is JobStatus.QUEUED
