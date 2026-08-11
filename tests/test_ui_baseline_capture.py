import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import override

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from lnt.errors import InputError
from lnt.types import SeriesPosition
from lnt.ui import operations
from lnt.ui.app import create_app
from lnt.ui.dependencies import CSRF_HEADER, CSRF_VALUE
from lnt.ui.models import CaptureRequest, parse_job_request
from lnt.ui.operations import LntBackend

_CSRF = {CSRF_HEADER: CSRF_VALUE}


def _capture_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"kind": "capture"}
    payload.update(overrides)
    return payload


def test_capture_request_accepts_safe_baseline_name() -> None:
    request = parse_job_request(_capture_payload(baseline_session="base-noise"))

    assert isinstance(request, CaptureRequest)
    assert request.baseline_session == "base-noise"


def test_capture_request_defaults_baseline_to_none() -> None:
    request = parse_job_request(_capture_payload())

    assert isinstance(request, CaptureRequest)
    assert request.baseline_session is None


@pytest.mark.parametrize("hostile", ["..", "a/b", "a\\b", "../x", ".hidden"])
def test_capture_request_rejects_traversal_baseline(hostile: str) -> None:
    with pytest.raises(ValidationError):
        parse_job_request(_capture_payload(baseline_session=hostile))


def test_capture_request_rejects_baseline_with_self_noise() -> None:
    with pytest.raises(ValidationError) as excinfo:
        parse_job_request(_capture_payload(self_noise=True, baseline_session="x"))

    message = str(excinfo.value)
    message.encode("cp1251")
    assert "самошум не принимает базовую сессию" in message


def test_capture_one_passes_sibling_baseline_to_capture_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[dict[str, object]] = []

    def _recorder(**kwargs: object) -> Path:
        recorded.append(kwargs)
        return tmp_path / "out"

    monkeypatch.setattr(operations, "capture_session", _recorder)
    backend = LntBackend()

    with_baseline = parse_job_request(_capture_payload(baseline_session="base-noise"))
    assert isinstance(with_baseline, CaptureRequest)
    backend.capture_one(with_baseline, tmp_path / "out", None)

    without_baseline = parse_job_request(_capture_payload())
    assert isinstance(without_baseline, CaptureRequest)
    backend.capture_one(without_baseline, tmp_path / "out2", None)

    assert recorded[0]["baseline_session"] == "../base-noise"
    assert recorded[1]["baseline_session"] is None


@dataclass(frozen=True, slots=True)
class _RecordingBackend(LntBackend):
    requests: list[CaptureRequest] = field(default_factory=list)

    @override
    def capture_one(
        self,
        request: CaptureRequest,
        out_dir: Path,
        series: SeriesPosition | None,
    ) -> Path:
        del out_dir, series
        self.requests.append(request)
        raise InputError("останов записи в тесте")


def _poll_terminal(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        payload: dict[str, object] = client.get(f"/api/jobs/{job_id}").json()
        if payload["status"] in {"succeeded", "cancelled", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("задача не завершилась за 5 секунд")


def test_capture_job_route_carries_baseline_session(tmp_path: Path) -> None:
    backend = _RecordingBackend()
    with TestClient(create_app(root=tmp_path, backend=backend)) as client:
        accepted = client.post(
            "/api/jobs",
            headers=_CSRF,
            json=_capture_payload(baseline_session="base-noise"),
        )
        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]
        _poll_terminal(client, job_id)

        rejected = client.post(
            "/api/jobs",
            headers=_CSRF,
            json=_capture_payload(baseline_session="../evil"),
        )

    assert len(backend.requests) == 1
    assert backend.requests[0].baseline_session == "base-noise"
    assert rejected.status_code == 422
