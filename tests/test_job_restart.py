from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from lnt.app_paths import resolve_app_paths
from lnt.runtime.store import JobStore
from lnt.ui.app import create_app
from lnt.ui.job_state import advance, new_job
from lnt.ui.models import JobKind, JobStatus

if TYPE_CHECKING:
    from pathlib import Path

_CSRF = {"X-LNT-Request": "ui"}


def test_restart_interrupts_nonterminal_job_and_accepts_new_job(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.sqlite3"
    store_a = JobStore(runtime_db)
    abandoned = new_job(JobKind.CAPTURE)
    store_a.create(abandoned, input_reference={"device": "hantek"})
    store_a.record(advance(abandoned, status=JobStatus.RUNNING))

    with TestClient(create_app(root=tmp_path / "sessions", runtime_db=runtime_db)) as client_b:
        recovered = client_b.get(f"/api/jobs/{abandoned.job_id}")
        created = client_b.post("/api/jobs", headers=_CSRF, json={"kind": "selftest"})

    assert recovered.status_code == 200
    assert recovered.json()["status"] == "interrupted"
    assert recovered.json()["error_code"] == "process_interrupted"
    assert created.status_code == 202
    assert created.json()["job_id"] != abandoned.job_id


def test_runtime_database_is_app_scoped_and_injectable(
    tmp_path: Path,
    runtime_db: Path,
) -> None:

    with TestClient(create_app(root=tmp_path / "sessions", runtime_db=runtime_db)) as client:
        response = client.post("/api/jobs", headers=_CSRF, json={"kind": "selftest"})

    assert response.status_code == 202
    assert runtime_db.exists()


def test_default_runtime_database_uses_isolated_localappdata(tmp_path: Path) -> None:
    expected = resolve_app_paths().runtime_db

    with TestClient(create_app(root=tmp_path / "sessions")):
        pass

    assert expected.exists()
    assert str(expected).startswith(str(tmp_path))
