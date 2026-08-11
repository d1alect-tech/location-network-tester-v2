from __future__ import annotations

import hashlib
import json
import zipfile
from typing import TYPE_CHECKING

import pytest

from lnt.archive import (
    ArchiveError,
    ArchiveLimits,
    ExportSelection,
    create_archive,
    restore_archive,
)
from lnt.cli import main

if TYPE_CHECKING:
    from pathlib import Path


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _session(root: Path, identifier: str) -> Path:
    directory = root / identifier
    (directory / "analysis" / "run-1").mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "session_id": identifier}), encoding="utf-8"
    )
    (directory / "ch1.npy").write_bytes(b"\x93NUMPY-test")
    (directory / "context.json").write_text('{"schema_version":1}', encoding="utf-8")
    (directory / "context.events.jsonl").write_text('{"revision":1}\n', encoding="utf-8")
    (directory / "analysis" / "run-1" / "metrics.json").write_text("{}", encoding="utf-8")
    (directory / "report.html").write_text("<html>stored only</html>", encoding="utf-8")
    (directory / "capture.log").write_text("secret-ish log", encoding="utf-8")
    return directory


def test_create_restore_round_trip_preserves_all_exported_hashes(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    source = _session(sessions, "s-1")
    original = _hashes(source)
    output = tmp_path / "backup.zip"
    create_archive(
        output,
        ExportSelection(root=sessions, session_ids=("s-1",), experiment_ids=()),
    )

    destination = tmp_path / "restored"
    plan = restore_archive(output, destination)

    restored = _hashes(destination / "sessions" / "s-1")
    assert restored == {
        name: digest for name, digest in original.items() if not name.endswith(".log")
    }
    assert all("catalog.sqlite3" not in str(entry.path) for entry in plan.manifest.entries)


def test_dry_run_performs_no_write(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    _session(sessions, "s-1")
    archive = tmp_path / "backup.zip"
    create_archive(
        archive,
        ExportSelection(root=sessions, session_ids=("s-1",), experiment_ids=()),
    )
    destination = tmp_path / "restored"

    plan = restore_archive(archive, destination, dry_run=True)

    assert len(plan.manifest.entries) == 6
    assert not destination.exists()
    assert not tuple(tmp_path.glob(".lnt-import-staging-*"))


def test_wrong_hash_fails_before_destination(tmp_path: Path) -> None:
    archive = tmp_path / "wrong.zip"
    manifest = {
        "archive_schema_version": 1,
        "provenance": {
            "build_id": "test",
            "created_at": "2026-08-11T00:00:00Z",
            "source_session_ids": ["s"],
            "source_experiment_ids": [],
        },
        "entries": [{"path": "sessions/s/x", "size": 1, "sha256": "0" * 64}],
    }
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("archive-manifest.json", json.dumps(manifest))
        output.writestr("sessions/s/x", b"a")

    with pytest.raises(ArchiveError, match="SHA-256"):
        restore_archive(archive, tmp_path / "restored")

    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize(
    "limits",
    [
        ArchiveLimits(max_file_count=0),
        ArchiveLimits(max_expanded_bytes=8, max_per_file_bytes=100),
        ArchiveLimits(max_expanded_bytes=100, max_per_file_bytes=8),
    ],
    ids=["file-count", "expanded", "per-file"],
)
def test_limits_reject_archive_before_destination(tmp_path: Path, limits: ArchiveLimits) -> None:
    sessions = tmp_path / "sessions"
    _session(sessions, "s-1")
    archive = tmp_path / "backup.zip"
    create_archive(
        archive,
        ExportSelection(root=sessions, session_ids=("s-1",), experiment_ids=()),
    )

    with pytest.raises(ArchiveError):
        restore_archive(archive, tmp_path / "restored", limits=limits)

    assert not (tmp_path / "restored").exists()


def test_rename_crash_leaves_only_named_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = tmp_path / "sessions"
    _session(sessions, "s-1")
    archive = tmp_path / "backup.zip"
    create_archive(
        archive,
        ExportSelection(root=sessions, session_ids=("s-1",), experiment_ids=()),
    )

    def fail_rename(_source: Path, _destination: Path) -> None:
        raise OSError("injected crash")

    monkeypatch.setattr("lnt.archive.restore.os.rename", fail_rename)
    with pytest.raises(ArchiveError, match="quarantine"):
        restore_archive(archive, tmp_path / "restored")

    assert not (tmp_path / "restored").exists()
    quarantines = tuple(tmp_path.glob(".lnt-import-staging-*"))
    assert len(quarantines) == 1


def test_cli_inventory_and_typed_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sessions = tmp_path / "sessions"
    _session(sessions, "s-1")
    archive = tmp_path / "backup.zip"
    assert (
        main(["archive", "create", str(archive), "--root", str(sessions), "--session", "s-1"]) == 0
    )
    assert main(["archive", "list", str(archive)]) == 0
    assert main(["archive", "verify", str(archive)]) == 0
    assert (
        main(
            ["archive", "restore", str(archive), "--dest", str(tmp_path / "restored"), "--dry-run"]
        )
        == 0
    )
    assert main(["archive", "verify", str(tmp_path / "missing.zip")]) == 2
    captured = capsys.readouterr()
    assert "Архив проверен" in captured.out
    assert "Ошибка:" in captured.err
