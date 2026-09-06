"""RBW-шкала спектра и input-referred endpoint: контракт для фронта."""

import json
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import numpy as np
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from lnt.analysis import analyze_measurement_session, write_analysis
from lnt.compare import ComparisonResult
from lnt.runtime.store import JobStore
from lnt.scope_io import NEVER_CANCELLED, CancellationToken
from lnt.selftest import SelftestResult
from lnt.simulate import simulate_session
from lnt.support import SupportBundleResult
from lnt.types import SeriesPosition
from lnt.ui.analysis_v2_wire import AnalyzeWriteResult
from lnt.ui.dependencies import AppServices, install_services
from lnt.ui.device import DeviceStatus
from lnt.ui.jobs import JobManager
from lnt.ui.models import CaptureRequest, SimulateRequest
from lnt.ui.operations import BackupResult
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

    def analyze_and_write(self, session_dir: Path) -> AnalyzeWriteResult:
        del session_dir
        raise AssertionError("задачи не должны запускаться")

    def compare(self, session_a: Path, session_b: Path) -> ComparisonResult:
        del session_a, session_b
        raise AssertionError("задачи не должны запускаться")

    def selftest(self) -> SelftestResult:
        raise AssertionError("задачи не должны запускаться")

    def device_check(self) -> DeviceStatus:
        raise AssertionError("задачи не должны запускаться")

    def backup(self, root: Path) -> BackupResult:
        del root
        raise AssertionError("задачи не должны запускаться")

    def support_bundle(self) -> SupportBundleResult:
        raise AssertionError("задачи не должны запускаться")


def _build_client(root: Path) -> tuple[TestClient, JobManager]:
    backend: JobBackend = _UnusedBackend()
    manager = JobManager(
        backend=backend,
        root=root,
        store=JobStore(root / ".lnt" / "runtime.sqlite3"),
    )
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
    return TestClient(app), manager


@pytest.fixture(scope="module")
def analyzed_client() -> Iterator[TestClient]:
    """Проанализированная synthetic schema-v1 сессия (input-reference недоступен)."""
    with tempfile.TemporaryDirectory(prefix="rbw-routes") as tmp:
        root = Path(tmp)
        session_dir = simulate_session(
            out_dir=root / "analyzed",
            profile="bad",
            duration_s=2.4,
            sample_rate_hz=500_000,
            seed=6022,
        )
        write_analysis(session_dir, analyze_measurement_session(session_dir))
        client, manager = _build_client(root)
        with client:
            yield client
        anyio.run(manager.aclose)


def test_spectrum_reports_rbw_meta(analyzed_client: TestClient, tmp_path: Path) -> None:
    del tmp_path
    response = analyzed_client.get("/api/sessions/analyzed/spectrum")

    assert response.status_code == 200
    payload = response.json()
    # Обратная совместимость: старые ключи на месте.
    assert "frequency_hz" in payload
    assert "psd_v2_per_hz" in payload
    assert "point_count" in payload
    # RBW-контракт шкалы.
    assert isinstance(payload["resolution_hz"], (int, float))
    assert payload["resolution_hz"] > 0.0
    assert isinstance(payload["band_low_hz"], (int, float))
    assert isinstance(payload["band_high_hz"], (int, float))
    assert payload["band_low_hz"] < payload["band_high_hz"]


def test_spectrum_rbw_matches_metrics(analyzed_client: TestClient, tmp_path: Path) -> None:
    del tmp_path
    response = analyzed_client.get("/api/sessions/analyzed/spectrum")

    assert response.status_code == 200
    assert response.json()["resolution_hz"] > 0.0


def test_input_referred_unavailable_conflicts_with_reason(
    analyzed_client: TestClient,
) -> None:
    response = analyzed_client.get("/api/sessions/analyzed/spectrum-input-referred")

    assert response.status_code == 409
    assert "manifest_schema_v1" in response.json()["detail"]


def test_input_referred_missing_file_not_found(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    simulate_session(
        out_dir=root / "fresh",
        profile="quiet",
        duration_s=0.05,
        sample_rate_hz=100_000,
        seed=6023,
    )
    client, manager = _build_client(root)
    try:
        with client:
            response = client.get("/api/sessions/fresh/spectrum-input-referred")
    finally:
        anyio.run(manager.aclose)

    assert response.status_code == 404


def test_input_referred_available_returns_full_contract(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    root.mkdir()
    session_dir = simulate_session(
        out_dir=root / "referred",
        profile="bad",
        duration_s=2.4,
        sample_rate_hz=500_000,
        seed=6024,
    )
    write_analysis(session_dir, analyze_measurement_session(session_dir))
    metrics_path = session_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    reference = metrics["ch1_input_reference"]
    reference["status"] = "available"
    reference["reason_code"] = None
    reference["qualified_bin_count"] = 8
    reference["total_bin_count"] = 16
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False), encoding="utf-8")
    freqs = np.linspace(3_000.0, 10_000.0, 8)
    psd = np.full(8, 1e-12)
    np.savetxt(
        session_dir / "spectrum_input_referred.csv",
        np.column_stack([freqs, psd]),
        delimiter=",",
        header="frequency_hz,input_referred_excess_psd_v2_per_hz",
        comments="",
        fmt="%.9g",
    )
    client, manager = _build_client(root)
    try:
        with client:
            response = client.get("/api/sessions/referred/spectrum-input-referred")
    finally:
        anyio.run(manager.aclose)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["reason_code"] is None
    assert payload["qualified_bin_count"] == 8
    assert payload["total_bin_count"] == 16
    assert payload["point_count"] == 8
    assert len(payload["frequency_hz"]) == 8
    assert len(payload["input_referred_excess_psd_v2_per_hz"]) == 8
    assert all(value > 0.0 for value in payload["frequency_hz"])
    assert isinstance(payload["resolution_hz"], (int, float))
    assert payload["resolution_hz"] > 0.0
