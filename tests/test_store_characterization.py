"""Характеризационные тесты фасада store.py перед расслоением (issue #8, C4-хвост).

Эти тесты фиксируют НАБЛЮДАЕМОЕ поведение долговечного хранилища ДО тонкого
фасада и обязаны остаться зелёными ПОСЛЕ него: они и есть межверсионное
доказательство того, что кодек SQLite-персистентности не поехал.

Три слоя пинов:
* сквозной round-trip реального sqlite-хранилища (создать → закрыть → открыть);
* точный сериализованный текст снимка и прогресса для фиксированного входа;
* таблица переходов вместе с точным русским текстом отказа.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Final

import pytest

from lnt.runtime.store import (
    _ALLOWED,
    _TERMINAL,
    _TRACEBACK_MARKER,
    IllegalJobTransitionError,
    JobStore,
    _compact_error,
    _dump_progress,
    _dump_snapshot,
    _load_snapshot,
    _next_statuses,
)
from lnt.ui.job_state import JobSnapshot, advance, new_job
from lnt.ui.models import JobKind, JobStage, JobStatus

if TYPE_CHECKING:
    from pathlib import Path

# Независимый источник истины: таблица переходов выписана вручную, а не
# получена из кода, поэтому расхождение с реализацией провалит тест.
_EXPECTED_ALLOWED: Final[dict[JobStatus, frozenset[JobStatus]]] = {
    JobStatus.QUEUED: frozenset(
        {JobStatus.RUNNING, JobStatus.CANCELLING, JobStatus.INTERRUPTED},
    ),
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

_PINNED_SNAPSHOT: Final = JobSnapshot(
    schema_version=1,
    version=4,
    job_id="pinned-job",
    kind=JobKind.CAPTURE,
    status=JobStatus.SUCCEEDED,
    stage=JobStage.DONE,
    series_index=2,
    series_total=3,
    written_sessions=("сессия-1", "сессия-2"),
    result={"session": "сессия-2", "ok": True},
    error_code=None,
    error_message="ошибка «кавычки»",
)

_PINNED_SNAPSHOT_JSON: Final = (
    '{"schema_version": 1, "version": 4, "job_id": "pinned-job", "kind": "capture", '
    '"status": "succeeded", "stage": "done", "series_index": 2, "series_total": 3, '
    '"written_sessions": ["сессия-1", "сессия-2"], '
    '"result": {"session": "сессия-2", "ok": true}, '
    '"error_code": null, "error_message": "ошибка «кавычки»"}'
)

_PINNED_PROGRESS_JSON: Final = (
    '{"stage": "done", "series_index": 2, "series_total": 3, '
    '"written_sessions": ["сессия-1", "сессия-2"]}'
)


def _read(path: Path, sql: str, params: tuple[object, ...]) -> list[tuple[object, ...]]:
    with sqlite3.connect(path) as connection:
        return connection.execute(sql, params).fetchall()


def _seed_store(path: Path) -> dict[str, str]:
    """Наполняет свежее хранилище задачами во всех интересных состояниях."""
    store = JobStore(path)

    only_queued = new_job(JobKind.SELFTEST)
    store.create(only_queued, input_reference={"kind": "selftest"})

    still_running = new_job(JobKind.SIMULATE)
    store.create(still_running, input_reference={"profile": "quiet"})
    store.record(
        advance(
            still_running,
            status=JobStatus.RUNNING,
            stage=JobStage.SIMULATING,
            series_index=0,
            series_total=5,
            add_session="b-1",
        ),
    )

    succeeded = new_job(JobKind.SIMULATE)
    store.create(succeeded, input_reference={"profile": "bad"})
    running = advance(
        succeeded,
        status=JobStatus.RUNNING,
        stage=JobStage.SIMULATING,
        series_index=1,
        series_total=2,
        add_session="s-1",
    )
    store.record(running)
    store.record(
        advance(
            running,
            status=JobStatus.SUCCEEDED,
            stage=JobStage.DONE,
            add_session="s-2",
            result={"session": "s-2"},
        ),
    )

    failed = new_job(JobKind.CAPTURE)
    store.create(failed)
    store.record(advance(failed, status=JobStatus.RUNNING, stage=JobStage.CAPTURING))
    store.transition(
        failed.job_id,
        JobStatus.FAILED,
        error_code="internal_error",
        error_message=f"{_TRACEBACK_MARKER}:\nсекрет",
    )

    cancelled = new_job(JobKind.ANALYZE)
    store.create(cancelled)
    store.transition(cancelled.job_id, JobStatus.CANCELLING)
    store.transition(cancelled.job_id, JobStatus.CANCELLED)

    return {
        "queued": only_queued.job_id,
        "running": still_running.job_id,
        "succeeded": succeeded.job_id,
        "failed": failed.job_id,
        "cancelled": cancelled.job_id,
    }


def _expected_snapshots(ids: dict[str, str]) -> dict[str, JobSnapshot]:
    """Ожидаемые снимки, выписанные вручную (не производные от хранилища)."""
    return {
        "queued": JobSnapshot(
            schema_version=1,
            version=1,
            job_id=ids["queued"],
            kind=JobKind.SELFTEST,
            status=JobStatus.QUEUED,
            stage=JobStage.QUEUED,
            series_index=None,
            series_total=None,
            written_sessions=(),
            result=None,
            error_code=None,
            error_message=None,
        ),
        "running": JobSnapshot(
            schema_version=1,
            version=2,
            job_id=ids["running"],
            kind=JobKind.SIMULATE,
            status=JobStatus.RUNNING,
            stage=JobStage.SIMULATING,
            series_index=0,
            series_total=5,
            written_sessions=("b-1",),
            result=None,
            error_code=None,
            error_message=None,
        ),
        "succeeded": JobSnapshot(
            schema_version=1,
            version=3,
            job_id=ids["succeeded"],
            kind=JobKind.SIMULATE,
            status=JobStatus.SUCCEEDED,
            stage=JobStage.DONE,
            series_index=1,
            series_total=2,
            written_sessions=("s-1", "s-2"),
            result={"session": "s-2"},
            error_code=None,
            error_message=None,
        ),
        "failed": JobSnapshot(
            schema_version=1,
            version=3,
            job_id=ids["failed"],
            kind=JobKind.CAPTURE,
            status=JobStatus.FAILED,
            stage=JobStage.DONE,
            series_index=None,
            series_total=None,
            written_sessions=(),
            result=None,
            error_code="internal_error",
            error_message="внутренняя ошибка",
        ),
        "cancelled": JobSnapshot(
            schema_version=1,
            version=3,
            job_id=ids["cancelled"],
            kind=JobKind.ANALYZE,
            status=JobStatus.CANCELLED,
            stage=JobStage.DONE,
            series_index=None,
            series_total=None,
            written_sessions=(),
            result=None,
            error_code=None,
            error_message=None,
        ),
    }


def test_reopened_store_round_trips_every_field_of_every_state(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    ids = _seed_store(database)
    expected = _expected_snapshots(ids)

    reopened = JobStore(database)

    for key, snapshot in expected.items():
        assert reopened.get(ids[key]) == snapshot, f"снимок «{key}» не пережил переоткрытие"


def test_reopened_store_replays_event_journal_in_version_order(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    ids = _seed_store(database)

    reopened = JobStore(database)

    assert [(e.version, e.status) for e in reopened.events(ids["succeeded"])] == [
        (1, JobStatus.QUEUED),
        (2, JobStatus.RUNNING),
        (3, JobStatus.SUCCEEDED),
    ]
    assert [(e.version, e.status) for e in reopened.events(ids["cancelled"])] == [
        (1, JobStatus.QUEUED),
        (2, JobStatus.CANCELLING),
        (3, JobStatus.CANCELLED),
    ]
    replayed = reopened.event_snapshots(ids["succeeded"], page_size=10, after_version=1)
    assert [item.version for item in replayed] == [2, 3]
    assert replayed[-1].written_sessions == ("s-1", "s-2")


def test_reopened_store_pages_snapshots_newest_first(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    ids = _seed_store(database)

    reopened = JobStore(database)

    page = reopened.list_snapshots(page_size=2)
    assert [item.job_id for item in page] == [ids["cancelled"], ids["failed"]]
    tail = reopened.list_snapshots(page_size=3, offset=2)
    assert [item.job_id for item in tail] == [ids["succeeded"], ids["running"], ids["queued"]]


def test_on_disk_columns_keep_their_exact_serialized_text(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    ids = _seed_store(database)

    row = _read(
        database,
        """SELECT operation_kind, status, version, input_reference, result_reference,
        progress, error_code, error_message FROM jobs WHERE job_id = ?""",
        (ids["succeeded"],),
    )[0]

    assert row == (
        "simulate",
        "succeeded",
        3,
        '{"profile": "bad"}',
        '{"session": "s-2"}',
        (
            '{"stage": "done", "series_index": 1, "series_total": 2, '
            '"written_sessions": ["s-1", "s-2"]}'
        ),
        None,
        None,
    )
    event = _read(
        database,
        "SELECT snapshot FROM job_events WHERE job_id = ? AND version = ?",
        (ids["succeeded"], 3),
    )[0]
    assert json.loads(str(event[0])) == {
        "schema_version": 1,
        "version": 3,
        "job_id": ids["succeeded"],
        "kind": "simulate",
        "status": "succeeded",
        "stage": "done",
        "series_index": 1,
        "series_total": 2,
        "written_sessions": ["s-1", "s-2"],
        "result": {"session": "s-2"},
        "error_code": None,
        "error_message": None,
    }


def test_queued_job_without_input_reference_stores_null(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    ids = _seed_store(database)

    row = _read(
        database,
        "SELECT input_reference, result_reference, progress FROM jobs WHERE job_id = ?",
        (ids["failed"],),
    )[0]

    assert row == (
        None,
        None,
        '{"stage": "done", "series_index": null, "series_total": null, "written_sessions": []}',
    )


def test_dump_snapshot_pins_exact_json_text() -> None:
    assert _dump_snapshot(_PINNED_SNAPSHOT) == _PINNED_SNAPSHOT_JSON


def test_dump_progress_pins_exact_json_text() -> None:
    assert _dump_progress(_PINNED_SNAPSHOT) == _PINNED_PROGRESS_JSON


def test_load_snapshot_reads_the_pinned_json_text_back() -> None:
    assert _load_snapshot(_PINNED_SNAPSHOT_JSON) == _PINNED_SNAPSHOT


def test_allowed_table_matches_the_hand_written_expectation() -> None:
    assert dict(_ALLOWED) == _EXPECTED_ALLOWED
    assert {status.value for status in _TERMINAL} == {
        "succeeded",
        "failed",
        "cancelled",
        "interrupted",
    }
    assert _TRACEBACK_MARKER == "Traceback (most recent call last)"


def test_next_statuses_always_includes_the_current_status() -> None:
    for status, allowed in _EXPECTED_ALLOWED.items():
        snapshot = JobSnapshot(
            schema_version=1,
            version=1,
            job_id="probe",
            kind=JobKind.SIMULATE,
            status=status,
            stage=JobStage.QUEUED,
            series_index=None,
            series_total=None,
            written_sessions=(),
            result=None,
            error_code=None,
            error_message=None,
        )
        assert _next_statuses(snapshot) == frozenset({status, *allowed})


def test_compact_error_pins_its_exact_russian_replacement() -> None:
    assert _compact_error(None, None) is None
    assert _compact_error("internal_error", None) is None
    assert _compact_error("internal_error", "обычный текст") == "внутренняя ошибка"
    assert _compact_error("input_error", f"{_TRACEBACK_MARKER}:\nсекрет") == "внутренняя ошибка"
    assert _compact_error("input_error", "короткое сообщение") == "короткое сообщение"
    assert _compact_error(None, "я" * 600) == "я" * 500


@pytest.mark.parametrize(
    "target",
    [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.QUEUED],
)
def test_transition_rejects_forbidden_target_with_exact_text(
    tmp_path: Path,
    target: JobStatus,
) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")
    queued = new_job(JobKind.SIMULATE)
    store.create(queued)

    with pytest.raises(IllegalJobTransitionError) as excinfo:
        store.transition(queued.job_id, target)

    assert str(excinfo.value) == (
        f"недопустимый переход задачи {queued.job_id}: queued -> {target.value}"
    )


def test_transition_out_of_terminal_state_is_rejected_with_exact_text(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")
    queued = new_job(JobKind.CAPTURE)
    store.create(queued)
    store.record(advance(queued, status=JobStatus.RUNNING))
    store.transition(queued.job_id, JobStatus.FAILED, error_code="input_error")

    with pytest.raises(IllegalJobTransitionError) as excinfo:
        store.transition(queued.job_id, JobStatus.RUNNING)

    assert str(excinfo.value) == (f"недопустимый переход задачи {queued.job_id}: failed -> running")


def test_record_rejects_replayed_version_with_exact_text(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")
    queued = new_job(JobKind.SIMULATE)
    store.create(queued)
    running = advance(queued, status=JobStatus.RUNNING)
    store.record(running)

    with pytest.raises(IllegalJobTransitionError) as excinfo:
        store.record(running)

    assert str(excinfo.value) == (
        f"недопустимый переход задачи {queued.job_id}: running -> running"
    )


def test_interrupt_nonterminal_touches_only_live_jobs(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    ids = _seed_store(database)

    reopened = JobStore(database)
    interrupted = reopened.interrupt_nonterminal()

    assert interrupted == (ids["queued"], ids["running"])
    for key in ("queued", "running"):
        snapshot = reopened.get(ids[key])
        assert snapshot.status is JobStatus.INTERRUPTED
        assert snapshot.stage is JobStage.DONE
        assert snapshot.error_code == "process_interrupted"
        assert snapshot.error_message == "задача прервана перезапуском приложения"
    assert reopened.get(ids["succeeded"]).status is JobStatus.SUCCEEDED


def test_prune_keeps_referenced_and_recent_terminal_jobs(tmp_path: Path) -> None:
    database = tmp_path / "runtime.sqlite3"
    ids = _seed_store(database)

    reopened = JobStore(database)
    removed = reopened.prune_unreferenced_terminal(keep=1)

    assert removed == (ids["failed"],)
    assert reopened.get(ids["succeeded"]).written_sessions == ("s-1", "s-2")
    assert reopened.get(ids["cancelled"]).status is JobStatus.CANCELLED


def test_missing_job_raises_key_error(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "runtime.sqlite3")

    with pytest.raises(KeyError):
        store.get("отсутствует")
