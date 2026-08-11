"""E2E-контракты команд обслуживания каталога."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from lnt.cli import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _minimal_manifest(path: Path, session_id: str = "fixture") -> None:
    path.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "created_utc": "2026-08-11T12:00:00Z",
        "completed_utc": "2026-08-11T12:00:01Z",
        "source": "synthetic",
        "session_type": "measurement",
        "sample_rate_hz": 1.0,
        "duration_s": 1.0,
        "sample_count": 1,
        "line_frequency_hz": 50.0,
        "profile": "quiet",
        "baseline_session": None,
        "parameters": {},
        "ch1": {
            "filename": "ch1.npy",
            "role": "hf_probe",
            "unit": "V",
            "front_end": "fixture",
            "range_code": 1,
            "probe_multiplier": 1.0,
        },
        "ch2": None,
        "acquisition_telemetry": None,
        "synthetic_truth": None,
    }
    (path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    (path / "ch1.npy").write_bytes(b"fixture")


def test_catalog_reindex_status_and_verify_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    _minimal_manifest(root / "one")

    # When
    reindex_code = main(
        ["catalog", "reindex", "--root", str(root), "--database", str(database), "--json"],
    )
    reindex_payload = json.loads(capsys.readouterr().out)
    status_code = main(["catalog", "status", "--database", str(database), "--json"])
    status_payload = json.loads(capsys.readouterr().out)
    verify_code = main(
        ["catalog", "verify", "--root", str(root), "--database", str(database), "--json"],
    )
    verify_payload = json.loads(capsys.readouterr().out)

    # Then
    assert (reindex_code, status_code, verify_code) == (0, 0, 0)
    assert reindex_payload["inserted"] == 1
    assert status_payload["health"] == {"ok": 1}
    assert verify_payload["drift_paths"] == []


def test_catalog_verify_exits_one_on_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    root = tmp_path / "sessions"
    database = tmp_path / "catalog.sqlite3"
    session = root / "one"
    _minimal_manifest(session)
    main(["catalog", "reindex", "--root", str(root), "--database", str(database)])
    capsys.readouterr()
    (session / "manifest.json").write_text("{}", encoding="utf-8")

    # When
    code = main(["catalog", "verify", "--root", str(root), "--database", str(database)])

    # Then
    assert code == 1
    assert "расхождение" in capsys.readouterr().out.lower()


def test_import_context_dry_run_never_changes_copied_fixture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given
    copied = tmp_path / "copied-fixture"
    _minimal_manifest(copied)
    legacy = copied / "context.legacy.json"
    legacy.write_text(json.dumps({"tags": ["lab"]}), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in copied.iterdir()}

    # When
    code = main(["catalog", "import-context", "--dry-run", str(copied), "--json"])
    payload = json.loads(capsys.readouterr().out)

    # Then
    assert code == 0
    assert payload["would_import"] is True
    assert {path.name: path.read_bytes() for path in copied.iterdir()} == before
    assert not (copied / "context.json").exists()
