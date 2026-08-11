"""Интеграционные контракты перестраиваемого каталога сессий."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from lnt.catalog import apply_migrations
from lnt.catalog.reconcile import reconcile_catalog, verify_catalog
from lnt.manifest import manifest_to_json
from lnt.types import ChannelMeta, ChannelRole, SessionManifest, SessionSource, SessionType


def _session(root: Path, directory: str, session_id: str) -> Path:
    path = root / directory
    path.mkdir(parents=True)
    manifest = SessionManifest(
        schema_version=1,
        session_id=session_id,
        created_utc="2026-08-11T12:00:00Z",
        completed_utc="2026-08-11T12:00:01Z",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=1.0,
        duration_s=1.0,
        sample_count=1,
        line_frequency_hz=50.0,
        profile="quiet",
        baseline_session=None,
        parameters={"label": directory},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="fixture",
            range_code=1,
            probe_multiplier=1.0,
        ),
        ch2=None,
        acquisition_telemetry=None,
        synthetic_truth=None,
    )
    (path / "manifest.json").write_text(manifest_to_json(manifest), encoding="utf-8")
    (path / "ch1.npy").write_bytes(b"fixture")
    return path


def _semantic_rows(database: Path) -> list[tuple[str, str, str, str]]:
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(
            """SELECT storage_path, session_id, health, path_fingerprint
            FROM catalog_sessions ORDER BY storage_path""",
        ).fetchall()


def test_reconcile_is_incremental_idempotent_and_removes_deleted_dirs(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    first = _session(root, "first", "session-1")
    apply_migrations(database)

    # When
    initial = reconcile_catalog(root, database)
    unchanged = reconcile_catalog(root, database)
    shutil.rmtree(first)
    deleted = reconcile_catalog(root, database)

    # Then
    assert (initial.inserted, unchanged.skipped, deleted.deleted) == (1, 1, 1)
    assert _semantic_rows(database) == []


def test_corrupt_partial_missing_and_duplicate_sessions_remain_visible(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    first = _session(root, "duplicate-a", "same-id")
    _session(root, "duplicate-b", "same-id")
    corrupt = root / "corrupt"
    corrupt.mkdir()
    (corrupt / "manifest.json").write_text("{", encoding="utf-8")
    missing = _session(root, "missing", "missing-id")
    (missing / "ch1.npy").unlink()
    partial = root / "write.partial-deadbeef"
    partial.mkdir()
    (first / "metrics.json").write_text("{", encoding="utf-8")
    apply_migrations(database)

    # When
    reconcile_catalog(root, database)

    # Then
    health = {path: state for path, _id, state, _fingerprint in _semantic_rows(database)}
    assert health == {
        str(corrupt.resolve()): "corrupt_manifest",
        str(first.resolve()): "duplicate_id",
        str((root / "duplicate-b").resolve()): "duplicate_id",
        str(missing.resolve()): "missing_files",
        str(partial.resolve()): "partial",
    }


def test_invalid_context_and_analysis_are_classified_without_hiding(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    context = _session(root, "bad-context", "context-id")
    (context / "context.json").write_text("{}", encoding="utf-8")
    analysis = _session(root, "bad-analysis", "analysis-id")
    (analysis / "metrics.json").write_text(json.dumps({"session_id": "other"}), encoding="utf-8")
    apply_migrations(database)

    # When
    reconcile_catalog(root, database)

    # Then
    health = {Path(path).name: state for path, _id, state, _fp in _semantic_rows(database)}
    assert health == {"bad-analysis": "analysis_invalid", "bad-context": "context_invalid"}


def test_rebuild_after_database_deletion_reproduces_semantic_rows(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    _session(root, "one", "one")
    _session(root, "two", "two")
    apply_migrations(database)
    reconcile_catalog(root, database)
    expected = _semantic_rows(database)

    # When
    database.unlink()
    apply_migrations(database)
    reconcile_catalog(root, database, rebuild=True)

    # Then
    assert _semantic_rows(database) == expected


def test_verify_reports_fingerprint_drift_without_writing(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    session = _session(root, "one", "one")
    apply_migrations(database)
    reconcile_catalog(root, database)
    (session / "manifest.json").write_text("{}", encoding="utf-8")

    # When
    result = verify_catalog(root, database)

    # Then
    assert result.drift_paths == (str(session.resolve()),)


def test_manifest_filename_escape_is_rejected_without_outside_access(tmp_path: Path) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    session = _session(root, "escape", "escape")
    payload = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    payload["ch1"]["filename"] = "../outside.npy"
    (session / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    outside = root / "outside.npy"
    outside.write_bytes(b"must-not-be-read-or-written")
    apply_migrations(database)

    # When
    reconcile_catalog(root, database)

    # Then
    assert _semantic_rows(database)[0][2] == "corrupt_manifest"
    assert outside.read_bytes() == b"must-not-be-read-or-written"
