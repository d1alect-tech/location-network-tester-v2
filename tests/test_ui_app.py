import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict, override

import pytest
from starlette.testclient import TestClient

from lnt.selftest import SelftestResult
from lnt.ui.app import create_app
from lnt.ui.dependencies import CSRF_HEADER, CSRF_VALUE
from lnt.ui.operations import LntBackend

_CSRF: Final = {CSRF_HEADER: CSRF_VALUE}
_TERMINAL_STATUSES: Final = frozenset({"succeeded", "cancelled", "failed"})
STATIC_DIR: Final = Path(__file__).resolve().parent.parent / "src/lnt/ui/static"
SESSION_VIEWS_PATH: Final = STATIC_DIR / "session-views.js"


class _JobPayload(TypedDict):
    job_id: str
    status: str


@dataclass(frozen=True, slots=True)
class _InstantBackend(LntBackend):
    @override
    def selftest(self) -> SelftestResult:
        return SelftestResult(
            ok=True,
            message="самопроверка успешна",
            frequency_hz=22_400.0,
            cycles_analyzed=120,
        )


def _start_selftest(client: TestClient) -> str:
    response = client.post("/api/jobs", headers=_CSRF, json={"kind": "selftest"})
    assert response.status_code == 202
    payload: _JobPayload = response.json()
    return payload["job_id"]


def _poll_terminal(client: TestClient, job_id: str) -> _JobPayload:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        payload: _JobPayload = response.json()
        if payload["status"] in _TERMINAL_STATUSES:
            return payload
        time.sleep(0.01)
    raise AssertionError("задача не завершилась за 5 секунд")


def _wait_for_job_threads() -> list[str]:
    deadline = time.monotonic() + 5
    names: list[str] = []
    while time.monotonic() < deadline:
        names = [
            thread.name for thread in threading.enumerate() if thread.name.startswith("lnt-job")
        ]
        if not names:
            return []
        time.sleep(0.01)
    return names


def test_lifespan_creates_nested_root(tmp_path: Path) -> None:
    root = tmp_path / "nested" / "sessions"
    assert not root.exists()

    with TestClient(create_app(root=root, backend=_InstantBackend())):
        assert root.is_dir()


def test_index_serves_panel_html(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="simulate-form"' in response.text
    assert "/static/app.js" in response.text


def test_index_preloads_ibm_plex_sans_regular(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        html = client.get("/").text

    link_tags = re.findall(r"<link\b[^>]*>", html)
    font_preloads = [tag for tag in link_tags if 'rel="preload"' in tag and 'as="font"' in tag]
    assert len(font_preloads) == 1
    tag = font_preloads[0]
    assert 'href="/static/fonts/IBMPlexSans-Regular.woff2"' in tag
    assert 'type="font/woff2"' in tag
    assert "crossorigin" in tag


def test_session_detail_source_is_measurement_first() -> None:
    views = SESSION_VIEWS_PATH.read_text(encoding="utf-8")
    assert "function manifestDisclosure(manifest)" in views
    render = views.split("export function renderSessionDetail", maxsplit=1)[1]
    render = render.split("export function renderDeviceStatus", maxsplit=1)[0]
    helper = views.split("function manifestDisclosure", maxsplit=1)[1]
    helper = helper.split("function analysisView", maxsplit=1)[0]
    manifest_call = "content.append(manifestDisclosure(detail.manifest))"
    assert render.index("content.append(analysisView(detail))") < render.index(manifest_call)
    assert render.index("content.append(waveformControls(detail))") < render.index(manifest_call)
    assert 'element("details", "manifest-disclosure")' in helper
    assert 'element("summary", "", "Манифест")' in helper
    assert "manifestView(manifest)" in helper
    assert "disclosure.open" not in helper


@pytest.mark.parametrize(
    ("path", "minimum_size"),
    [
        ("/static/styles.css", 1),
        ("/static/vendor/plotly-gl2d-3.7.0.min.js", 1_000_000),
        ("/static/fonts/IBMPlexSans-Regular.woff2", 10_000),
        ("/static/fonts/IBMPlexMono-Medium.woff2", 10_000),
        ("/static/fonts/manifest.json", 100),
        ("/static/favicon.svg", 100),
        ("/static/theme.js", 500),
        ("/static/session-filter.js", 200),
        ("/static/plotly-loader.js", 800),
        ("/static/app.js", 50),
        ("/static/app-controller.js", 1_000),
        ("/static/app-dom.js", 1_000),
        ("/static/job-controller.js", 800),
        ("/static/session-controller.js", 800),
        ("/static/views.js", 100),
        ("/static/view-dom.js", 300),
        ("/static/chart-views.js", 1_000),
        ("/static/session-views.js", 1_000),
        ("/static/status-views.js", 1_000),
        ("/static/ch1-input-reference.js", 200),
    ],
)
def test_static_assets_are_served(tmp_path: Path, path: str, minimum_size: int) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        response = client.get(path)

    assert response.status_code == 200
    assert len(response.content) > minimum_size


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_online_documentation_is_disabled(tmp_path: Path, path: str) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        response = client.get(path)

    assert response.status_code == 404


def test_sessions_router_is_included(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jobs_router_requires_csrf(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        response = client.post("/api/jobs", json={"kind": "selftest"})

    assert response.status_code == 403


def test_validation_error_is_compact_russian_text(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        response = client.post("/api/jobs", headers=_CSRF, json={"kind": "nope"})

    assert response.status_code == 422
    detail: str = response.json()["detail"]
    assert "некорректные параметры" in detail
    assert "\n" not in detail
    assert "Input tag" not in detail
    assert "literal_error" not in detail
    detail.encode("cp1251")


def test_selftest_job_round_trip_succeeds(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        job_id = _start_selftest(client)
        terminal = _poll_terminal(client, job_id)

    assert terminal["status"] == "succeeded"


def test_lifespan_shutdown_closes_worker_thread(tmp_path: Path) -> None:
    with TestClient(create_app(root=tmp_path, backend=_InstantBackend())) as client:
        job_id = _start_selftest(client)
        _poll_terminal(client, job_id)
        assert any(thread.name.startswith("lnt-job") for thread in threading.enumerate())

    assert _wait_for_job_threads() == []


def test_sequential_apps_have_independent_job_state(tmp_path: Path) -> None:
    with TestClient(
        create_app(root=tmp_path / "first", backend=_InstantBackend()),
    ) as first_client:
        first_job_id = _start_selftest(first_client)
        assert _poll_terminal(first_client, first_job_id)["status"] == "succeeded"

    with TestClient(
        create_app(root=tmp_path / "second", backend=_InstantBackend()),
    ) as second_client:
        missing = second_client.get(f"/api/jobs/{first_job_id}")
        second_job_id = _start_selftest(second_client)
        terminal = _poll_terminal(second_client, second_job_id)

    assert missing.status_code == 404
    assert terminal["status"] == "succeeded"


def test_index_and_static_no_cache(tmp_path: Path) -> None:
    """Панель и статика всегда ревалидируются: обновление UI не залипает в кэше."""
    app = create_app(root=tmp_path)
    with TestClient(app) as client:
        for path in ("/", "/static/app.js"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.headers["cache-control"] == "no-cache", path
