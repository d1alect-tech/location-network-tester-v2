"""GET /api/sessions/{id}/ripple — read-only отдача сохранённого сайдкара.

Контракт (план todo 5 + поправки исполнения 2026-10-20): GET никогда не
считает и не мутирует; absent=404, corrupt/stale/schema-incompatible=409,
ambiguous=409, unsafe ID=422, параметры запроса не принимаются. Тело 200 —
байты сохранённого ``ripple.json`` без пересборки.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pytest
from starlette.testclient import TestClient

from lnt.analysis_v2 import engine_ripple
from lnt.analysis_v2.engine_ripple import run_ripple
from lnt.analysis_v2.ripple_options import RippleRequest, SettlingDeclaration
from lnt.ripple.adapter import AdapterSpec
from lnt.session_store import LoadedSession, load_session, write_session
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
)
from lnt.ui.app import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_FS_HZ = 10_000.0
_COUNT_FULL = 29_000  # как в tests/analysis_v2/test_ripple_engine.py: 2 сегмента Welch
_COUNT_SMALL = 1_000
_AMPLITUDE_V = 0.05
_TONE_HZ = 100.0
_DC_V = 0.5


@dataclass(frozen=True, slots=True)
class RippleRoutesFixture:
    root: Path
    client: TestClient
    meas_dir: Path


def _record(count: int) -> np.ndarray:
    times = np.arange(count, dtype=np.float64) / _FS_HZ
    record = _DC_V + _AMPLITUDE_V * np.sin(2.0 * np.pi * _TONE_HZ * times)
    return record.astype(np.float32)


def _telemetry(count: int) -> AcquisitionTelemetry:
    return AcquisitionTelemetry(
        requested_samples=count,
        captured_samples=count,
        callback_count=1,
        block_lengths=(count,),
        callback_gaps_s=(),
        expected_block_interval_s=count / _FS_HZ,
        short_block_count=0,
        ch1_clip_low_count=0,
        ch1_clip_high_count=0,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=False,
    )


def _manifest(*, session_id: str, count: int) -> SessionManifest:
    return SessionManifest(
        schema_version=1,
        session_id=session_id,
        created_utc="2026-10-20T00:00:00Z",
        completed_utc="2026-10-20T00:00:03Z",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=_FS_HZ,
        duration_s=count / _FS_HZ,
        sample_count=count,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters={},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="ripple route fixture",
            range_code=10,
            probe_multiplier=1.0,
        ),
        ch2=None,
        acquisition_telemetry=_telemetry(count),
        synthetic_truth=None,
    )


def _write_session(root: Path, name: str, *, session_id: str, count: int) -> LoadedSession:
    write_session(
        session_dir=root / name,
        manifest=_manifest(session_id=session_id, count=count),
        ch1=_record(count),
        ch2=None,
    )
    return load_session(root / name)


def _sidecar_path(session_dir: Path) -> Path:
    return session_dir / "ripple.json"


@pytest.fixture(scope="module")
def ripple_routes(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RippleRoutesFixture]:
    root = tmp_path_factory.mktemp("ripple-routes")
    meas_dir = root / "meas"
    measurement = _write_session(root, "meas", session_id="sess-alpha", count=_COUNT_FULL)
    run_ripple(
        RippleRequest(
            session=measurement,
            adapter=AdapterSpec(),
            band_low_hz=99.0,
            band_high_hz=101.0,
            settling=SettlingDeclaration.PRECONNECTED,
        )
    )
    _write_session(root, "plain", session_id="plain-id", count=_COUNT_SMALL)
    _write_session(root, "stale", session_id="stale-id", count=_COUNT_FULL)
    stale = load_session(root / "stale")
    run_ripple(
        RippleRequest(
            session=stale,
            adapter=AdapterSpec(),
            band_low_hz=99.0,
            band_high_hz=101.0,
            settling=SettlingDeclaration.PRECONNECTED,
        )
    )
    _write_session(root, "notjson", session_id="notjson-id", count=_COUNT_SMALL)
    (root / "notjson" / "ripple.json").write_bytes(b'{"schema_version": 1, "session": {')
    _write_session(root, "badschema", session_id="badschema-id", count=_COUNT_SMALL)
    (root / "badschema" / "ripple.json").write_text(
        '{"schema_version": 2, "unexpected": true}\n', encoding="utf-8"
    )
    _write_session(root, "nonfinite", session_id="nonfinite-id", count=_COUNT_SMALL)
    (root / "nonfinite" / "ripple.json").write_text(
        '{"schema_version": 1, "options": {"band_low_hz": 1e999}}\n', encoding="utf-8"
    )
    _write_session(root, "dirthief", session_id="dirthief-id", count=_COUNT_SMALL)
    (root / "dirthief" / "ripple.json").mkdir()
    _write_session(root, "amb-1", session_id="twin-id", count=_COUNT_SMALL)
    _write_session(root, "amb-2", session_id="twin-id", count=_COUNT_SMALL)
    with TestClient(create_app(root=root)) as client:
        yield RippleRoutesFixture(root=root, client=client, meas_dir=meas_dir)


def test_ripple_serves_stored_artifact_bytes(ripple_routes: RippleRoutesFixture) -> None:
    stored = _sidecar_path(ripple_routes.meas_dir).read_bytes()

    response = ripple_routes.client.get("/api/sessions/meas/ripple")

    assert response.status_code == 200
    assert response.content == stored
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["session"]["session_id"] == "sess-alpha"
    # GET без x-lnt-mutation-nonce: read-only маршрут, nonce не требуется.
    assert "x-lnt-mutation-nonce" not in response.request.headers


def test_ripple_resolves_by_manifest_session_id(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/sess-alpha/ripple")

    assert response.status_code == 200
    assert response.json()["session"]["session_id"] == "sess-alpha"


def test_ripple_never_recomputes_or_mutates(ripple_routes: RippleRoutesFixture) -> None:
    sidecar = _sidecar_path(ripple_routes.meas_dir)
    before = (sidecar.stat().st_mtime_ns, hashlib.sha256(sidecar.read_bytes()).hexdigest())
    files_before = {entry.name for entry in ripple_routes.meas_dir.iterdir()}

    original = engine_ripple.run_ripple

    def _forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("GET ripple не должен запускать движок")

    engine_ripple.run_ripple = _forbidden
    try:
        response = ripple_routes.client.get("/api/sessions/meas/ripple")
    finally:
        engine_ripple.run_ripple = original
    after_stat = sidecar.stat().st_mtime_ns
    after_hash = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    files_after = {entry.name for entry in ripple_routes.meas_dir.iterdir()}

    assert response.status_code == 200
    assert (after_stat, after_hash) == before
    assert files_after == files_before


def test_ripple_unknown_session_maps_404(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/ghost/ripple")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_ripple_missing_artifact_maps_404_not_built(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/plain/ripple")

    assert response.status_code == 404
    assert response.json()["reason"] == "not_built"


def test_ripple_corrupt_json_maps_409(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/notjson/ripple")

    assert response.status_code == 409
    assert response.json()["reason"] == "corrupt"


def test_ripple_nonfinite_number_maps_409(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/nonfinite/ripple")

    assert response.status_code == 409
    assert response.json()["reason"] == "corrupt"


def test_ripple_incompatible_schema_maps_409(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/badschema/ripple")

    assert response.status_code == 409
    assert response.json()["reason"] == "schema_incompatible"


def test_ripple_stale_input_maps_409(ripple_routes: RippleRoutesFixture) -> None:
    # manifest.json меняет байты после публикации сайдкара: хэш входа расходится.
    manifest_path = ripple_routes.root / "stale" / "manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")

    response = ripple_routes.client.get("/api/sessions/stale/ripple")

    assert response.status_code == 409
    assert response.json()["reason"] == "stale_input"


def test_ripple_directory_sidecar_maps_409(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/dirthief/ripple")

    assert response.status_code == 409
    assert response.json()["reason"] == "corrupt"


def test_ripple_ambiguous_session_maps_409(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/twin-id/ripple")

    assert response.status_code == 409


def test_ripple_unsafe_session_name_maps_422(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/.hidden/ripple")

    assert response.status_code == 422


def test_ripple_rejects_query_parameters(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/sessions/meas/ripple?band=99-101")

    assert response.status_code == 422


def test_health_still_ok_after_ripple_router(ripple_routes: RippleRoutesFixture) -> None:
    response = ripple_routes.client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
