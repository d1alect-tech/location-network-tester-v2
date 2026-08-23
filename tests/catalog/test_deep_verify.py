"""GAP-1 regression: глубокая сверка каталога ловит смену байтов raw-файла."""

from __future__ import annotations

import os
import sqlite3
from typing import TYPE_CHECKING

import numpy as np

from lnt.catalog.reconcile import reconcile_catalog, verify_catalog
from lnt.session_store import write_session
from lnt.types import (
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
)

if TYPE_CHECKING:
    from pathlib import Path


def _manifest(session_id: str, sample_count: int = 256) -> SessionManifest:
    return SessionManifest(
        schema_version=1,
        session_id=session_id,
        created_utc="2026-08-20T10:00:00Z",
        completed_utc="2026-08-20T10:00:01Z",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=250_000.0,
        duration_s=sample_count / 250_000.0,
        sample_count=sample_count,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters={},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="high_z",
            range_code=5,
            probe_multiplier=1.0,
        ),
        ch2=None,
        acquisition_telemetry=None,
        synthetic_truth=None,
    )


def _flip_last_byte_preserving_stat(path: Path) -> None:
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 0xFF
    stat_before = path.stat()
    path.write_bytes(bytes(raw))
    os.utime(path, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))


def test_deep_verify_detects_byte_flip_that_shallow_misses(tmp_path: Path) -> None:
    # Given: сессия в каталоге, сверенный catalog и deep-базовый снимок.
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    root.mkdir()
    ch1 = (np.arange(256, dtype=np.float32) / 256).astype(np.float32)
    session_dir = write_session(
        session_dir=root / "gap1-sess",
        manifest=_manifest("gap1-sess"),
        ch1=ch1,
        ch2=None,
    )
    reconcile_catalog(root, database)
    baseline = verify_catalog(root, database, deep=True)
    assert baseline.drift_paths == ()
    assert baseline.baseline_created is True

    # When: байт flip при сохранённых размере и mtime.
    _flip_last_byte_preserving_stat(session_dir / "ch1.npy")

    # Then: shallow verify (stat-сверка) не видит подмену — документированное
    # поведение быстрых бюджетов; health остаётся ok (эталонного хеша нет).
    shallow = verify_catalog(root, database)
    assert shallow.drift_paths == ()

    # And: deep verify хеширует содержимое raw .npy и обнаруживает drift.
    deep = verify_catalog(root, database, deep=True)
    assert deep.drift_paths == (str(session_dir),)
    assert deep.baseline_created is False


def test_deep_verify_clean_tree_reports_no_drift(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    root.mkdir()
    ch1 = np.ones(64, dtype=np.float32)
    write_session(
        session_dir=root / "clean-sess",
        manifest=_manifest("clean-sess", sample_count=64),
        ch1=ch1,
        ch2=None,
    )
    reconcile_catalog(root, database)
    first = verify_catalog(root, database, deep=True)
    assert first.baseline_created is True
    second = verify_catalog(root, database, deep=True)
    assert second.drift_paths == ()
    assert second.baseline_created is False
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT health FROM catalog_sessions WHERE session_id = 'clean-sess'"
        ).fetchone()
    assert row is not None
    assert row[0] == "ok"


def test_reconcile_fingerprint_stays_shallow_for_budgets(tmp_path: Path) -> None:
    # Обычный reindex не читает raw-массивы: byte-flip с сохранённым mtime
    # остаётся skipped (бюджеты Todo 10 не деградируют).
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    root.mkdir()
    ch1 = np.zeros(128, dtype=np.float32)
    session_dir = write_session(
        session_dir=root / "budget-sess",
        manifest=_manifest("budget-sess", sample_count=128),
        ch1=ch1,
        ch2=None,
    )
    first = reconcile_catalog(root, database)
    assert first.inserted == 1
    _flip_last_byte_preserving_stat(session_dir / "ch1.npy")
    second = reconcile_catalog(root, database)
    assert second.skipped == 1
