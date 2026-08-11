from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import anyio
import pytest
from fastapi import Depends, FastAPI, HTTPException
from starlette.testclient import TestClient

from lnt.analysis import AnalysisResult
from lnt.compare import ComparisonResult
from lnt.errors import InputError
from lnt.runtime.store import JobStore
from lnt.scope_io import NEVER_CANCELLED, CancellationToken
from lnt.selftest import SelftestResult
from lnt.types import SeriesPosition
from lnt.ui.dependencies import (
    AppServices,
    get_services,
    install_services,
    map_domain_error,
    require_csrf,
    resolve_session_or_404,
)
from lnt.ui.device import DeviceStatus
from lnt.ui.jobs import (
    JobBusyError,
    JobManager,
    JobNotCancellableError,
    UnknownJobError,
)
from lnt.ui.models import CaptureRequest, SimulateRequest
from lnt.ui.security import SecurityContext
from tests.test_ui_sessions import write_manifest

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


def _submit() -> Mapping[str, bool]:
    return {"ok": True}


def _root(
    installed: Annotated[AppServices, Depends(get_services)],
) -> Mapping[str, str]:
    return {"root": str(installed.root)}


def _build_app(services: AppServices | None) -> FastAPI:
    app = FastAPI()
    if services is not None:
        install_services(app, services)
    app.add_api_route(
        "/submit",
        _submit,
        methods=["POST"],
        dependencies=[Depends(require_csrf)],
    )
    app.add_api_route("/root", _root, methods=["GET"])
    return app


@pytest.fixture
def services(tmp_path: Path) -> Iterator[AppServices]:
    backend: JobBackend = _UnusedBackend()
    runtime_db = tmp_path / "runtime.sqlite3"
    manager = JobManager(backend=backend, root=tmp_path, store=JobStore(runtime_db))
    yield AppServices(
        root=tmp_path,
        catalog_db=tmp_path / ".lnt" / "catalog.sqlite3",
        runtime_db=runtime_db,
        jobs=manager,
    )
    anyio.run(manager.aclose)


@pytest.fixture
def client(services: AppServices) -> Iterator[TestClient]:
    with TestClient(_build_app(services)) as test_client:
        yield test_client


def test_post_without_nonce_header_is_rejected(client: TestClient) -> None:
    response = client.post("/submit")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "mutation_nonce_invalid"


def test_post_with_wrong_nonce_value_is_rejected(client: TestClient) -> None:
    response = client.post("/submit", headers={"X-LNT-Mutation-Nonce": "wrong"})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "mutation_nonce_invalid"


def test_post_with_launch_nonce_is_accepted(client: TestClient) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    security = app.state.lnt_security
    assert isinstance(security, SecurityContext)
    response = client.post(
        "/submit",
        headers={"X-LNT-Mutation-Nonce": security.mutation_nonce},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_get_services_returns_installed_root(client: TestClient, services: AppServices) -> None:
    response = client.get("/root")

    assert response.status_code == 200
    assert response.json() == {"root": str(services.root)}


def test_get_services_without_installation_returns_internal_error() -> None:
    with TestClient(_build_app(None)) as client:
        response = client.get("/root")

    assert response.status_code == 500
    assert response.json() == {"detail": "сервисы не инициализированы"}


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (InputError("неверный вход"), 422, "неверный вход"),
        (JobBusyError(), 409, "уже выполняется задача"),
        (UnknownJobError(), 404, "задача не найдена"),
        (JobNotCancellableError(), 409, "задача уже завершена"),
    ],
)
def test_map_domain_error_returns_expected_http_error(
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    mapped = map_domain_error(error)

    assert (mapped.status_code, mapped.detail) == (status_code, detail)


def test_map_domain_error_reraises_unknown_error() -> None:
    error = RuntimeError("дефект")

    with pytest.raises(RuntimeError) as captured:
        map_domain_error(error)

    assert captured.value is error


def test_resolve_session_or_404_returns_existing_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "existing-session"
    write_manifest(session_dir)

    resolved = resolve_session_or_404(tmp_path, session_dir.name)

    assert resolved == session_dir


def test_resolve_session_or_404_maps_valid_missing_name_to_not_found(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as captured:
        resolve_session_or_404(tmp_path, "missing-session")

    assert (captured.value.status_code, captured.value.detail) == (404, "сессия не найдена")


def test_resolve_session_or_404_maps_malformed_name_to_unprocessable(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as captured:
        resolve_session_or_404(tmp_path, "a/b")

    assert captured.value.status_code == 422
    assert captured.value.detail == "небезопасное имя каталога сессии: 'a/b'"
