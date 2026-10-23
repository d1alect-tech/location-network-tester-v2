from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Final

import numpy as np
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from lnt import acquire, session_projection
from lnt.catalog.reconcile import reconcile_catalog
from lnt.context.events import read_event_history
from lnt.context.store import ContextStore
from lnt.instrument import FakeHantekScope
from lnt.ripple.adapter_declaration import ADAPTER_CONTEXT_KEYS, AdapterDeclaration
from lnt.scope_io import CancellationToken, CancelledResult
from lnt.session_store import write_session
from lnt.simulate import simulate_session
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMode,
    ComponentValuesBasis,
    SeriesPosition,
)
from lnt.ui import operations
from lnt.ui.app import create_app
from lnt.ui.models import CaptureRequest, parse_job_request
from lnt.ui.operations import LntBackend
from tests.test_manifest import make_manifest

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from httpx2 import Response


def _isolate_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local / "LNT" / "catalog.sqlite3"


def test_simulate_publishes_context_before_catalog_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    database = _isolate_catalog(monkeypatch, tmp_path)
    target = tmp_path / "sessions" / "synthetic"

    # When
    session = simulate_session(
        out_dir=target,
        profile="quiet",
        duration_s=0.05,
        sample_rate_hz=20_000.0,
        seed=7,
        label="bench",
    )

    # Then
    view = ContextStore(session, "syn-quiet-seed7").load()
    assert view.health == "context_valid"
    assert view.snapshot is not None
    assert view.snapshot.fields["sample.rate_hz"].value == 20_000.0
    assert (session / "context.events.jsonl").is_file()
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT session_id, health FROM catalog_sessions WHERE storage_path = ?",
            (str(session.resolve()),),
        ).fetchone()
    assert row == ("syn-quiet-seed7", "ok")


def test_capture_publishes_telemetry_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    _isolate_catalog(monkeypatch, tmp_path)
    raw = np.full(1_000, 128, dtype=np.uint8)
    telemetry = AcquisitionTelemetry(
        requested_samples=1_000,
        captured_samples=1_000,
        callback_count=1,
        block_lengths=(1_000,),
        callback_gaps_s=(),
        expected_block_interval_s=0.001,
        short_block_count=0,
        ch1_clip_low_count=0,
        ch1_clip_high_count=0,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=False,
    )
    monkeypatch.setattr(acquire, "open_real_scope", object)

    def fake_capture(*_args: object, **_kwargs: object) -> tuple[object, object, object]:
        return raw, raw, telemetry

    monkeypatch.setattr(acquire, "run_capture", fake_capture)

    # When
    session = acquire.capture_session(
        out_dir=tmp_path / "sessions" / "capture",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
    )

    # Then
    manifest_id = session_projection.session_id_from_manifest(session)
    view = ContextStore(session, manifest_id).load()
    assert view.snapshot is not None
    assert view.snapshot.fields["acquisition.captured_samples"].value == 1_000.0


def test_catalog_failure_after_rename_marks_session_and_reindex_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    database = _isolate_catalog(monkeypatch, tmp_path)
    target = tmp_path / "sessions" / "synthetic"
    real_reconcile: Callable[..., object] = session_projection.reconcile_catalog

    def fail_reconcile(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(
        session_projection,
        "reconcile_catalog",
        fail_reconcile,
    )

    # When
    session = simulate_session(
        out_dir=target,
        profile="quiet",
        duration_s=0.05,
        sample_rate_hz=20_000.0,
        seed=8,
    )

    # Then
    assert (session / ".reconcile-needed").is_file()
    assert ContextStore(session, "syn-quiet-seed8").load().health == "context_valid"
    monkeypatch.setattr(session_projection, "reconcile_catalog", real_reconcile)
    reconcile_catalog(session.parent, database)
    with sqlite3.connect(database) as connection:
        health = connection.execute(
            "SELECT health FROM catalog_sessions WHERE session_id = ?",
            ("syn-quiet-seed8",),
        ).fetchone()
    assert health == ("ok",)


def test_crash_before_session_rename_exposes_no_final_directory(tmp_path: Path) -> None:
    # Given
    manifest = make_manifest(sample_count=8)
    samples = np.zeros(8, dtype=np.float32)
    target = tmp_path / "session"

    # When
    with pytest.raises(RuntimeError, match="injected"):
        write_session(
            session_dir=target,
            manifest=manifest,
            ch1=samples,
            ch2=samples,
            before_publish=lambda _partial: (_ for _ in ()).throw(RuntimeError("injected")),
        )

    # Then
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# ripple: рельс декларации адаптера CaptureRequest -> context.json (N3)
# ---------------------------------------------------------------------------

_DECLARATION: Final = AdapterDeclaration(
    cap_nf=100.0,
    series_r_ohm=470.0,
    preconnected=True,
    component_values_basis=ComponentValuesBasis.OPERATOR_MEASURED,
)
_DECLARATION_PAYLOAD: Final[dict[str, object]] = {
    "preconnected": True,
    "cap_nf": 100.0,
    "series_r_ohm": 470.0,
    "component_values_basis": "operator_measured",
}


def _fake_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет захват прибора детерминированными отсчётами без железа."""
    raw = np.full(1_000, 128, dtype=np.uint8)
    telemetry = AcquisitionTelemetry(
        requested_samples=1_000,
        captured_samples=1_000,
        callback_count=1,
        block_lengths=(1_000,),
        callback_gaps_s=(),
        expected_block_interval_s=0.001,
        short_block_count=0,
        ch1_clip_low_count=0,
        ch1_clip_high_count=0,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=False,
    )

    def fake_run_capture(*_args: object, **_kwargs: object) -> tuple[object, object, object]:
        return raw, raw, telemetry

    monkeypatch.setattr(acquire, "run_capture", fake_run_capture)


def _capture_session(
    monkeypatch: pytest.MonkeyPatch,
    out_dir: Path,
    *,
    adapter_declaration: AdapterDeclaration | None = _DECLARATION,
    series: SeriesPosition | None = None,
) -> Path:
    """Захватывает одноканальную RC-сессию с фейк-прибором и опциональной декларацией."""
    _fake_capture(monkeypatch)
    return acquire.capture_session(
        out_dir=out_dir,
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        channel_mode=ChannelMode.CH1_ONLY,
        scope_factory=FakeHantekScope,
        adapter_declaration=adapter_declaration,
        series=series,
    )


def _adapter_keys(fields: Mapping[str, object]) -> set[str]:
    return {key for key in fields if key.startswith("adapter.")}


def test_capture_with_declaration_publishes_adapter_context_write_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    _isolate_catalog(monkeypatch, tmp_path)

    # When
    session = _capture_session(monkeypatch, tmp_path / "sessions" / "cap")

    # Then
    manifest_id = session_projection.session_id_from_manifest(session)
    cache = json.loads((session / "context.json").read_text(encoding="utf-8"))
    events = read_event_history(session / "context.events.jsonl", manifest_id)
    snapshot = ContextStore(session, manifest_id).load().snapshot
    assert snapshot is not None
    assert _adapter_keys(snapshot.fields) == set(ADAPTER_CONTEXT_KEYS)
    assert _adapter_keys(cache["fields"]) == set(ADAPTER_CONTEXT_KEYS)
    assert cache["revision"] == 1
    assert len(events) == 1
    assert events[0].actor == "lnt.capture"
    assert events[0].event_id == f"initial-{manifest_id}"
    assert events[0].new_revision == 1
    assert set(ADAPTER_CONTEXT_KEYS) <= set(events[0].changed_keys)
    assert snapshot.fields["adapter.cap_nf"].value == 100.0
    assert snapshot.fields["adapter.series_r_ohm"].value == 470.0
    assert snapshot.fields["adapter.preconnected"].value is True
    assert snapshot.fields["adapter.component_values_basis"].value == "operator_measured"


def test_capture_declaration_fields_project_into_catalog_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    database = _isolate_catalog(monkeypatch, tmp_path)

    # When
    session = _capture_session(monkeypatch, tmp_path / "sessions" / "cap")

    # Then
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT field_key, field_value FROM catalog_context_fields WHERE storage_path = ?",
            (str(session.resolve()),),
        ).fetchall()
    values = dict(rows)
    assert set(ADAPTER_CONTEXT_KEYS) <= set(values)
    assert json.loads(values["adapter.cap_nf"]) == 100.0
    assert json.loads(values["adapter.series_r_ohm"]) == 470.0
    assert json.loads(values["adapter.preconnected"]) is True
    assert json.loads(values["adapter.component_values_basis"]) == "operator_measured"


def test_capture_without_declaration_keeps_context_without_adapter_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    _isolate_catalog(monkeypatch, tmp_path)

    # When
    session = _capture_session(
        monkeypatch,
        tmp_path / "sessions" / "cap",
        adapter_declaration=None,
    )

    # Then
    manifest_id = session_projection.session_id_from_manifest(session)
    snapshot = ContextStore(session, manifest_id).load().snapshot
    assert snapshot is not None
    assert _adapter_keys(snapshot.fields) == set()
    assert snapshot.revision == 1
    assert snapshot.fields["acquisition.captured_samples"].value == 1_000.0
    events = read_event_history(session / "context.events.jsonl", manifest_id)
    assert len(events) == 1
    assert events[0].actor == "lnt.capture"


def test_capture_series_children_each_own_initial_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    _isolate_catalog(monkeypatch, tmp_path)
    sessions_root = tmp_path / "sessions"

    # When
    first = _capture_session(
        monkeypatch,
        sessions_root / "series-001",
        series=SeriesPosition(index=1, total=2, interval_s=0.0),
    )
    second = _capture_session(
        monkeypatch,
        sessions_root / "series-002",
        series=SeriesPosition(index=2, total=2, interval_s=0.0),
    )

    # Then
    manifest_ids: list[str] = []
    for child in (first, second):
        manifest_id = session_projection.session_id_from_manifest(child)
        manifest_ids.append(manifest_id)
        events = read_event_history(child / "context.events.jsonl", manifest_id)
        snapshot = ContextStore(child, manifest_id).load().snapshot
        assert snapshot is not None
        assert len(events) == 1
        assert events[0].event_id == f"initial-{manifest_id}"
        assert events[0].actor == "lnt.capture"
        assert events[0].new_revision == 1
        assert _adapter_keys(snapshot.fields) == set(ADAPTER_CONTEXT_KEYS)
    assert manifest_ids[0] != manifest_ids[1]


def test_cancellation_before_publish_removes_partial_and_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    _isolate_catalog(monkeypatch, tmp_path)
    _fake_capture(monkeypatch)
    probes = {"count": 0}

    def cancel_after_first_probe() -> bool:
        probes["count"] += 1
        return probes["count"] > 1

    sessions_root = tmp_path / "sessions"

    # When
    result = acquire.capture_session(
        out_dir=sessions_root / "cap",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        channel_mode=ChannelMode.CH1_ONLY,
        scope_factory=FakeHantekScope,
        adapter_declaration=_DECLARATION,
        cancellation_token=CancellationToken(cancel_after_first_probe),
    )

    # Then
    assert isinstance(result, CancelledResult)
    assert not (sessions_root / "cap").exists()
    assert list(sessions_root.iterdir()) == []
    assert not list(sessions_root.rglob("context.json"))
    assert not list(sessions_root.rglob("context.events.jsonl"))


def test_capture_one_passes_declaration_domain_to_capture_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    recorded: list[dict[str, object]] = []

    def _recorder(**kwargs: object) -> Path:
        recorded.append(kwargs)
        return tmp_path / "out"

    monkeypatch.setattr(operations, "capture_session", _recorder)
    backend = LntBackend()
    with_declaration = parse_job_request(
        {"kind": "capture", "channels": 1, "adapter_declaration": _DECLARATION_PAYLOAD}
    )
    without_declaration = parse_job_request({"kind": "capture"})

    # When
    assert isinstance(with_declaration, CaptureRequest)
    assert isinstance(without_declaration, CaptureRequest)
    backend.capture_one(with_declaration, tmp_path / "out", None, CancellationToken())
    backend.capture_one(without_declaration, tmp_path / "out2", None, CancellationToken())

    # Then
    assert recorded[0]["adapter_declaration"] == _DECLARATION
    assert recorded[1]["adapter_declaration"] is None


def test_capture_request_parses_declaration_and_defaults_to_none() -> None:
    # Given / When
    request = parse_job_request(
        {"kind": "capture", "channels": 1, "adapter_declaration": _DECLARATION_PAYLOAD}
    )
    default = parse_job_request({"kind": "capture"})

    # Then
    assert isinstance(request, CaptureRequest)
    assert isinstance(default, CaptureRequest)
    assert request.adapter_declaration is not None
    assert request.adapter_declaration.preconnected is True
    assert request.adapter_declaration.cap_nf == 100.0
    assert request.adapter_declaration.series_r_ohm == 470.0
    assert request.adapter_declaration.component_values_basis == "operator_measured"
    assert default.adapter_declaration is None


def _post_job(client: TestClient, body: dict[str, object]) -> Response:
    headers = {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}
    return client.post("/api/jobs", headers=headers, json=body)


def test_capture_request_rejects_unknown_declaration_fields() -> None:
    # Given
    payload: dict[str, object] = {
        "kind": "capture",
        "channels": 1,
        "adapter_declaration": {**_DECLARATION_PAYLOAD, "cap_pf": 1.0},
    }

    # When / Then
    with pytest.raises(ValidationError):
        parse_job_request(payload)


def test_simulate_job_rejects_adapter_declaration(tmp_path: Path) -> None:
    # Given
    body: dict[str, object] = {
        "kind": "simulate",
        "profile": "quiet",
        "adapter_declaration": _DECLARATION_PAYLOAD,
    }

    # When
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        response = _post_job(client, body)

    # Then
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"channels": 2},
        {"self_noise": True, "channels": 1},
        {"channels": 1, "input": "transformer"},
    ],
)
def test_capture_job_rejects_declaration_outside_single_channel_rc(
    tmp_path: Path,
    overrides: dict[str, object],
) -> None:
    # Given
    body: dict[str, object] = {"kind": "capture", "adapter_declaration": _DECLARATION_PAYLOAD}
    body.update(overrides)

    # When
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        response = _post_job(client, body)

    # Then
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"channels": 2},
        {"self_noise": True, "channels": 1},
        {"channels": 1, "input": "transformer"},
    ],
)
def test_capture_request_rejects_declaration_outside_single_channel_rc(
    overrides: dict[str, object],
) -> None:
    # Given
    payload: dict[str, object] = {"kind": "capture", "adapter_declaration": _DECLARATION_PAYLOAD}
    payload.update(overrides)

    # When / Then
    with pytest.raises(ValidationError) as excinfo:
        parse_job_request(payload)

    assert "ripple-декларация совместима только с одноканальным RC-захватом" in str(excinfo.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"cap_nf": 0.0},
        {"cap_nf": -5.0},
        {"series_r_ohm": -1.0},
        {"component_values_basis": "bogus"},
    ],
)
def test_capture_job_rejects_nonphysical_declaration_values(
    tmp_path: Path,
    overrides: dict[str, object],
) -> None:
    # Given
    declaration = {**_DECLARATION_PAYLOAD, **overrides}
    body: dict[str, object] = {
        "kind": "capture",
        "channels": 1,
        "adapter_declaration": declaration,
    }

    # When
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        response = _post_job(client, body)

    # Then
    assert response.status_code == 422
