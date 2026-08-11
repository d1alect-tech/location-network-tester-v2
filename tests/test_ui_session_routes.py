from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from lnt.analysis import AnalysisResult, analyze_measurement_session, write_analysis
from lnt.compare import ComparisonResult
from lnt.runtime.store import JobStore
from lnt.scope_io import NEVER_CANCELLED, CancellationToken
from lnt.selftest import SelftestResult
from lnt.simulate import simulate_session
from lnt.types import SeriesPosition
from lnt.ui.dependencies import AppServices, install_services
from lnt.ui.device import DeviceStatus
from lnt.ui.jobs import JobManager
from lnt.ui.models import CaptureRequest, SimulateRequest
from lnt.ui.routes_sessions import router

if TYPE_CHECKING:
    from lnt.ui.operations import JobBackend


@dataclass(frozen=True, slots=True)
class _UnusedBackend:
    def simulate_one(
        self,
        request: SimulateRequest,
        out_dir: Path,
        series: SeriesPosition | None,
    ) -> Path:
        del request, out_dir, series
        raise AssertionError("задачи не должны запускаться")

    def capture_one(
        self,
        request: CaptureRequest,
        out_dir: Path,
        series: SeriesPosition | None,
        cancellation_token: CancellationToken = NEVER_CANCELLED,
    ) -> Path:
        del request, out_dir, series, cancellation_token
        raise AssertionError("задачи не должны запускаться")

    def analyze_and_write(self, session_dir: Path) -> AnalysisResult:
        del session_dir
        raise AssertionError("задачи не должны запускаться")

    def compare(self, session_a: Path, session_b: Path) -> ComparisonResult:
        del session_a, session_b
        raise AssertionError("задачи не должны запускаться")

    def selftest(self) -> SelftestResult:
        raise AssertionError("задачи не должны запускаться")

    def device_check(self) -> DeviceStatus:
        raise AssertionError("задачи не должны запускаться")


@dataclass(frozen=True, slots=True)
class SessionRoutesFixture:
    root: Path
    client: TestClient
    unanalyzed_client: TestClient


def _build_app(root: Path, manager: JobManager) -> FastAPI:
    app = FastAPI()
    install_services(
        app,
        AppServices(
            root=root,
            catalog_db=root / ".lnt" / "catalog.sqlite3",
            runtime_db=root / ".lnt" / "runtime.sqlite3",
            jobs=manager,
        ),
    )
    app.include_router(router)
    return app


@pytest.fixture(scope="module")
def session_routes(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SessionRoutesFixture]:
    root = tmp_path_factory.mktemp("session-routes")
    analyzed_dir = simulate_session(
        out_dir=root / "analyzed",
        profile="bad",
        duration_s=2.4,
        sample_rate_hz=500_000,
        seed=6022,
    )
    write_analysis(analyzed_dir, analyze_measurement_session(analyzed_dir))
    corrupt_dir = root / "corrupt"
    corrupt_dir.mkdir()
    (corrupt_dir / "manifest.json").write_bytes(b"\xff")

    unanalyzed_root = tmp_path_factory.mktemp("session-routes-unanalyzed")
    simulate_session(
        out_dir=unanalyzed_root / "unanalyzed",
        profile="quiet",
        duration_s=0.05,
        sample_rate_hz=100_000,
        seed=6023,
    )
    backend: JobBackend = _UnusedBackend()
    manager = JobManager(
        backend=backend,
        root=root,
        store=JobStore(root / ".lnt" / "runtime.sqlite3"),
    )
    unanalyzed_manager = JobManager(
        backend=backend,
        root=unanalyzed_root,
        store=JobStore(unanalyzed_root / ".lnt" / "runtime.sqlite3"),
    )
    with (
        TestClient(_build_app(root, manager)) as client,
        TestClient(_build_app(unanalyzed_root, unanalyzed_manager)) as unanalyzed_client,
    ):
        yield SessionRoutesFixture(
            root=root,
            client=client,
            unanalyzed_client=unanalyzed_client,
        )
    anyio.run(manager.aclose)
    anyio.run(unanalyzed_manager.aclose)


def test_health_reports_ok(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["build_id"]


def test_config_reports_profiles_and_capture_defaults(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["root"] == str(session_routes.root)
    assert "bad" in payload["profiles"]
    assert payload["defaults"]["capture"]["range_v"] == 5.0


def test_sessions_lists_valid_and_corrupt_entries(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get("/api/sessions")

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert len(sessions) == 2
    invalid = next(entry for entry in sessions if entry["status"] == "invalid")
    assert invalid["name"] == "corrupt"
    assert "ошибка manifest.json" in invalid["error"]


def test_session_detail_reports_manifest_and_analysis(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get("/api/sessions/analyzed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["schema_version"] == 1
    assert payload["analysis"] is not None
    assert payload["spectrum_available"] is True
    assert payload["waveform_available"] is True


def test_session_detail_maps_missing_name_to_not_found(
    session_routes: SessionRoutesFixture,
) -> None:
    response = session_routes.client.get("/api/sessions/missing-session")

    assert response.status_code == 404


def test_session_detail_maps_malformed_name_to_unprocessable(
    session_routes: SessionRoutesFixture,
) -> None:
    response = session_routes.client.get("/api/sessions/...")

    assert response.status_code == 422


def test_spectrum_is_bounded_and_log_safe(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get("/api/sessions/analyzed/spectrum")

    assert response.status_code == 200
    payload = response.json()
    assert payload["point_count"] <= 5_000
    assert all(frequency > 0.0 for frequency in payload["frequency_hz"])


def test_spectrum_rejects_excessive_point_limit(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get("/api/sessions/analyzed/spectrum?max_points=99999")

    assert response.status_code == 422


def test_waveform_is_bounded(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get("/api/sessions/analyzed/waveform?channel=ch1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["channel"] == "ch1"
    assert payload["point_count"] <= 4_000


def test_waveform_rejects_unknown_channel(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.client.get(
        "/api/sessions/analyzed/waveform?channel=ch3",
    )

    assert response.status_code == 422


def test_spectrum_requires_analyzed_session(session_routes: SessionRoutesFixture) -> None:
    response = session_routes.unanalyzed_client.get("/api/sessions/unanalyzed/spectrum")

    assert response.status_code == 422
    assert "не проанализирована" in response.json()["detail"]
