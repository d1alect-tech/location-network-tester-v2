from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt import acquire, session_projection
from lnt.catalog.reconcile import reconcile_catalog
from lnt.context.store import ContextStore
from lnt.session_store import write_session
from lnt.simulate import simulate_session
from lnt.types import AcquisitionTelemetry
from tests.test_manifest import make_manifest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


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
