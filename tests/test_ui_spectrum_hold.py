"""Max-hold след спектра в payload (очередь B2): ADD-ключ, формат spectrum.csv цел."""

import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

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
from lnt.spectrum_hold import HOLD_SPECTRUM_FILENAME, write_hold_spectrum
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
class _IdleBackend:
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


def _build_client(root: Path) -> TestClient:
    backend: JobBackend = _IdleBackend()
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
    return TestClient(app)


@pytest.fixture(scope="module")
def hold_client() -> Iterator[tuple[TestClient, Path]]:
    """Сессия с max-hold сайдкаром рядом с spectrum.csv."""
    with tempfile.TemporaryDirectory(prefix="hold-routes") as tmp:
        root = Path(tmp)
        session_dir = simulate_session(
            out_dir=root / "analyzed",
            profile="bad",
            duration_s=2.4,
            sample_rate_hz=500_000,
            seed=6022,
        )
        result = analyze_measurement_session(session_dir)
        write_analysis(session_dir, result)
        write_hold_spectrum(session_dir, result.spectrum)
        client = _build_client(root)
        with client:
            yield client, session_dir


def test_spectrum_serves_max_hold_trace_aligned(
    hold_client: tuple[TestClient, Path], tmp_path: Path
) -> None:
    del tmp_path
    client, session_dir = hold_client
    assert (session_dir / HOLD_SPECTRUM_FILENAME).is_file()

    response = client.get("/api/sessions/analyzed/spectrum")

    assert response.status_code == 200
    payload = response.json()
    # Старые ключи на месте, spectrum.csv не тронут (две колонки).
    assert "frequency_hz" in payload
    assert "psd_v2_per_hz" in payload
    assert "point_count" in payload
    table = np.loadtxt(session_dir / "spectrum.csv", delimiter=",", skiprows=1)
    assert table.shape[1] == 2
    # ADD-ключ: та же сетка, та же длина, поточечно не ниже mean.
    assert "psd_max_hold_v2_per_hz" in payload
    assert len(payload["psd_max_hold_v2_per_hz"]) == len(payload["psd_v2_per_hz"])
    hold = np.asarray(payload["psd_max_hold_v2_per_hz"], dtype=np.float64)
    mean = np.asarray(payload["psd_v2_per_hz"], dtype=np.float64)
    assert np.all(hold >= mean)


def test_spectrum_without_sidecar_omits_hold_key(
    hold_client: tuple[TestClient, Path], tmp_path: Path
) -> None:
    del tmp_path
    client, session_dir = hold_client
    (session_dir / HOLD_SPECTRUM_FILENAME).unlink()

    response = client.get("/api/sessions/analyzed/spectrum")

    assert response.status_code == 200
    payload = response.json()
    assert "psd_max_hold_v2_per_hz" not in payload
    assert "psd_v2_per_hz" in payload


def test_corrupt_sidecar_keeps_main_spectrum(
    hold_client: tuple[TestClient, Path], tmp_path: Path
) -> None:
    del tmp_path
    client, session_dir = hold_client
    (session_dir / HOLD_SPECTRUM_FILENAME).write_bytes(b"frequency_hz\nnot-a-number\n")

    response = client.get("/api/sessions/analyzed/spectrum")

    assert response.status_code == 200
    payload = response.json()
    assert "psd_max_hold_v2_per_hz" not in payload
    assert "psd_v2_per_hz" in payload
