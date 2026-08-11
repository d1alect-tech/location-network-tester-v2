from pathlib import Path

from fastapi.testclient import TestClient

from lnt.runtime.store import JobStore
from lnt.ui.app import create_app
from lnt.ui.job_state import advance, new_job
from lnt.ui.models import JobKind, JobStatus


def test_durable_jobs_are_listed_after_restart(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.sqlite3"
    store = JobStore(runtime_db)
    abandoned = new_job(JobKind.CAPTURE)
    store.create(abandoned)
    store.record(advance(abandoned, status=JobStatus.RUNNING))

    with TestClient(create_app(root=tmp_path / "sessions", runtime_db=runtime_db)) as client:
        response = client.get("/api/jobs?page_size=20")

    assert response.status_code == 200
    assert response.json()["items"][0]["job_id"] == abandoned.job_id
    assert response.json()["items"][0]["status"] == "interrupted"


def test_job_event_history_is_replayed_after_restart(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.sqlite3"
    store = JobStore(runtime_db)
    abandoned = new_job(JobKind.CAPTURE)
    store.create(abandoned)
    store.record(advance(abandoned, status=JobStatus.RUNNING))

    with TestClient(create_app(root=tmp_path / "sessions", runtime_db=runtime_db)) as client:
        response = client.get(f"/api/jobs/{abandoned.job_id}/history?page_size=20")

    payload = response.json()
    assert response.status_code == 200
    assert [event["version"] for event in payload["items"]] == [1, 2, 3]
    assert payload["items"][-1]["status"] == "interrupted"


def test_device_state_exposes_typed_t14_state(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.get("/api/device/state")

    assert response.status_code == 200
    assert response.json()["state"] in {
        "backend_unavailable",
        "driver_missing",
        "device_absent",
        "bootloader_vid",
        "running_vid",
        "handle_busy",
        "firmware_missing",
        "firmware_upload_failed",
        "ready",
    }
    assert isinstance(response.json()["description_ru"], str)


def test_capture_preflight_returns_t14_report_without_starting_job(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path)) as client:
        nonce = client.get("/api/config").json()["mutation_nonce"]
        response = client.post(
            "/api/capture/preflight",
            headers={"X-LNT-Mutation-Nonce": nonce},
            json={"kind": "capture", "channels": 1},
        )
        jobs = client.get("/api/jobs?page_size=20").json()["items"]

    assert response.status_code == 200
    assert isinstance(response.json()["findings"], list)
    assert jobs == []
