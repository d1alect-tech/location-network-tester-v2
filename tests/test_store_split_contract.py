"""Контракт разбиения store.py: фасад + два чистых листа (issue #8, волна C0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lnt.runtime import store, store_codecs, store_transitions
from lnt.runtime.store import (
    _ALLOWED,
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


def test_facade_reexports_public_names() -> None:
    assert hasattr(store, "JobStore")
    assert hasattr(store, "JobEvent")
    assert hasattr(store, "IllegalJobTransitionError")
    for name in (
        "_compact_error",
        "_TRACEBACK_MARKER",
        "_TERMINAL",
        "_ALLOWED",
        "_next_statuses",
        "_dump_progress",
        "_dump_snapshot",
        "_load_snapshot",
    ):
        assert hasattr(store, name), f"фасад потерял имя: {name}"


def test_transitions_leaf_exposes_transition_helpers() -> None:
    for name in ("_compact_error", "_TRACEBACK_MARKER", "_TERMINAL", "_ALLOWED", "_next_statuses"):
        assert hasattr(store_transitions, name), f"лист переходов потерял имя: {name}"


def test_codecs_leaf_exposes_codec_helpers() -> None:
    for name in ("_dump_progress", "_dump_snapshot", "_load_snapshot"):
        assert hasattr(store_codecs, name), f"лист кодеков потерял имя: {name}"


def test_leaves_have_no_back_imports() -> None:
    root = Path(__file__).resolve().parent.parent / "src" / "lnt" / "runtime"
    for leaf in ("store_transitions.py", "store_codecs.py"):
        text = (root / leaf).read_text(encoding="utf-8")
        assert "JobStore" not in text, f"{leaf} ссылается на JobStore"
        assert "lnt.runtime" not in text, f"{leaf} импортирует lnt.runtime"
        assert "apply_migrations" not in text, f"{leaf} тянет миграции"


def test_facade_keeps_maintenance_surface() -> None:
    assert callable(store.JobStore.interrupt_nonterminal)
    assert callable(store.JobStore.prune_unreferenced_terminal)


def test_transition_codec_behavior_through_facade() -> None:
    assert _compact_error("x", None) is None
    assert (
        _compact_error("internal_error", "Traceback (most recent call last) …")
        == "внутренняя ошибка"
    )
    assert _compact_error(None, "Traceback (most recent call last) …") == "внутренняя ошибка"
    assert _compact_error(None, "x" * 600) == "x" * 500

    queued = JobSnapshot(
        schema_version=1,
        version=1,
        job_id="contract",
        kind=JobKind.SIMULATE,
        status=JobStatus.QUEUED,
        stage=JobStage.QUEUED,
        series_index=0,
        series_total=1,
        written_sessions=(),
        result=None,
        error_code=None,
        error_message=None,
    )
    assert _ALLOWED[JobStatus.QUEUED] >= {JobStatus.RUNNING}
    assert JobStatus.RUNNING in _next_statuses(queued)
    assert queued.status in _next_statuses(queued)
    restored = _load_snapshot(_dump_snapshot(queued))
    assert restored == queued
    assert "written_sessions" in _dump_progress(queued)


def test_facade_delegates_to_the_leaves_instead_of_duplicating_them() -> None:
    """Фасад обязан переэкспортировать сами объекты листьев, а не их копии."""
    assert store._dump_progress is store_codecs._dump_progress
    assert store._dump_snapshot is store_codecs._dump_snapshot
    assert store._load_snapshot is store_codecs._load_snapshot
    assert store._compact_error is store_transitions._compact_error
    assert store._next_statuses is store_transitions._next_statuses
    assert store._ALLOWED is store_transitions._ALLOWED
    assert store._TERMINAL is store_transitions._TERMINAL
    assert store._TRACEBACK_MARKER is store_transitions._TRACEBACK_MARKER


def test_facade_source_no_longer_redefines_leaf_helpers() -> None:
    """Дубли удалены физически: фасад не содержит определений листовых имён."""
    text = (Path(__file__).resolve().parent.parent / "src/lnt/runtime/store.py").read_text(
        encoding="utf-8",
    )
    for name in ("_dump_progress", "_dump_snapshot", "_load_snapshot", "_compact_error"):
        assert f"def {name}(" not in text, f"фасад всё ещё определяет {name}"
    for name in ("_TRACEBACK_MARKER:", "_TERMINAL:", "_ALLOWED:"):
        assert f"\n{name}" not in text, f"фасад всё ещё объявляет {name}"


def _queued_store(tmp_path: Path) -> tuple[JobStore, JobSnapshot]:
    job_store = JobStore(tmp_path / "runtime.sqlite3")
    queued = new_job(JobKind.SIMULATE)
    job_store.create(queued, input_reference={"profile": "quiet"})
    return job_store, queued


def test_facade_public_api_drives_a_full_job_lifecycle(tmp_path: Path) -> None:
    job_store, queued = _queued_store(tmp_path)

    assert job_store.get(queued.job_id) == queued

    running = advance(queued, status=JobStatus.RUNNING, stage=JobStage.SIMULATING)
    job_store.record(running)
    done = advance(
        running,
        status=JobStatus.SUCCEEDED,
        stage=JobStage.DONE,
        add_session="written-1",
        result={"session": "written-1"},
    )
    job_store.record(done)

    final = job_store.get(queued.job_id)
    assert final.status is JobStatus.SUCCEEDED
    assert final.stage is JobStage.DONE
    assert final.version == 3
    assert final.written_sessions == ("written-1",)
    assert final.result == {"session": "written-1"}
    assert [event.status for event in job_store.events(queued.job_id)] == [
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.SUCCEEDED,
    ]


def test_facade_public_api_pages_snapshots_and_replays_events(tmp_path: Path) -> None:
    job_store, queued = _queued_store(tmp_path)
    job_store.record(advance(queued, status=JobStatus.RUNNING))
    second = new_job(JobKind.CAPTURE)
    job_store.create(second)

    page = job_store.list_snapshots(page_size=1)
    assert [item.job_id for item in page] == [second.job_id]
    assert [item.job_id for item in job_store.list_snapshots(page_size=1, offset=1)] == [
        queued.job_id,
    ]
    replayed = job_store.event_snapshots(queued.job_id, page_size=10, after_version=1)
    assert [item.version for item in replayed] == [2]


def test_facade_public_api_rejects_illegal_transition_with_leaf_rules(tmp_path: Path) -> None:
    job_store, queued = _queued_store(tmp_path)

    with pytest.raises(IllegalJobTransitionError) as excinfo:
        job_store.transition(queued.job_id, JobStatus.SUCCEEDED)

    assert str(excinfo.value) == (
        f"недопустимый переход задачи {queued.job_id}: queued -> succeeded"
    )
    assert JobStatus.SUCCEEDED not in _ALLOWED[JobStatus.QUEUED]


def test_facade_public_api_compacts_errors_through_the_leaf(tmp_path: Path) -> None:
    job_store, queued = _queued_store(tmp_path)
    job_store.record(advance(queued, status=JobStatus.RUNNING))

    failed = job_store.transition(
        queued.job_id,
        JobStatus.FAILED,
        error_code="internal_error",
        error_message="Traceback (most recent call last):\nсекрет",
    )

    assert failed.error_message == "внутренняя ошибка"
    assert failed.stage is JobStage.DONE


def test_facade_public_api_interrupts_and_prunes(tmp_path: Path) -> None:
    job_store, queued = _queued_store(tmp_path)

    assert job_store.interrupt_nonterminal() == (queued.job_id,)
    assert job_store.get(queued.job_id).status is JobStatus.INTERRUPTED
    assert job_store.prune_unreferenced_terminal(keep=0) == (queued.job_id,)
    assert job_store.list_snapshots(page_size=10) == ()
