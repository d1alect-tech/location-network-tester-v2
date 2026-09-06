"""D2-backend: полный backup корня, CLI и UI job-kinds backup/support_bundle."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, override

import pytest
from pydantic import ValidationError

from lnt.archive.backup import backup_all_sessions, backup_output_name
from lnt.archive.inspect import inspect_archive
from lnt.cli import main
from lnt.support import SupportBundleResult
from lnt.ui.job_worker import WorkerContext, WorkerSucceeded, execute_job
from lnt.ui.models import JobStage, parse_job_request
from lnt.ui.operations import BackupResult, LntBackend

if TYPE_CHECKING:
    from lnt.ui.job_worker import WorkerUpdate


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


@dataclass(frozen=True, slots=True)
class _FakeBackend(LntBackend):
    """Мгновенный бэкенд для dispatch backup/support_bundle без диска."""

    @override
    def backup(self, root: Path) -> BackupResult:
        del root
        return BackupResult(path=Path("backup-20260101-000000.zip"), entry_count=6)

    @override
    def support_bundle(self) -> SupportBundleResult:
        return SupportBundleResult(
            path=Path("support-bundle-20260101-000000.zip"),
            member_names=("config.json", "device.json"),
        )


def test_backup_output_name_format() -> None:
    stamp = datetime(2026, 9, 6, 12, 30, 45, tzinfo=UTC)
    assert backup_output_name(stamp) == "backup-20260906-123045.zip"


def test_backup_collects_every_session_with_manifest(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    _session(sessions, "s-1")
    _session(sessions, "s-2")
    (sessions / "not-a-session").mkdir(parents=True)
    output = tmp_path / "full-backup.zip"

    manifest = backup_all_sessions(output, sessions)

    assert manifest.provenance.source_session_ids == ("s-1", "s-2")
    plan = inspect_archive(output)
    assert len(plan.manifest.entries) == len(manifest.entries) == 12


def test_backup_empty_root_raises(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()

    with pytest.raises(Exception, match="сессий"):
        backup_all_sessions(tmp_path / "o.zip", root)


def test_cli_backup_end_to_end(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    _session(sessions, "s-1")
    output = tmp_path / "cli-backup.zip"

    assert main(["archive", "backup", str(output), "--root", str(sessions)]) == 0

    assert output.is_file()
    assert len(inspect_archive(output).manifest.entries) == 6


def test_cli_backup_empty_root_is_input_error(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()

    assert main(["archive", "backup", str(tmp_path / "o.zip"), "--root", str(root)]) == 2
    assert not (tmp_path / "o.zip").exists()


def test_parse_backup_and_support_bundle_requests() -> None:
    assert parse_job_request({"kind": "backup"}).kind == "backup"
    assert parse_job_request({"kind": "support_bundle"}).kind == "support_bundle"


def test_parse_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        parse_job_request({"kind": "nope"})


def test_backup_job_succeeds_with_archive_name(tmp_path: Path) -> None:
    seen: list[WorkerUpdate] = []

    result = execute_job(
        WorkerContext(
            backend=_FakeBackend(),
            root=tmp_path,
            is_cancelled=lambda: False,
            report=seen.append,
        ),
        parse_job_request({"kind": "backup"}),
    )

    assert isinstance(result, WorkerSucceeded)
    assert result.result["archive"] == "backup-20260101-000000.zip"
    assert result.result["entry_count"] == 6
    assert seen
    assert seen[0].stage is JobStage.BACKUP


def test_support_bundle_job_succeeds_with_members(tmp_path: Path) -> None:
    seen: list[WorkerUpdate] = []

    result = execute_job(
        WorkerContext(
            backend=_FakeBackend(),
            root=tmp_path,
            is_cancelled=lambda: False,
            report=seen.append,
        ),
        parse_job_request({"kind": "support_bundle"}),
    )

    assert isinstance(result, WorkerSucceeded)
    assert result.result["bundle"] == "support-bundle-20260101-000000.zip"
    assert result.result["members"] == ["config.json", "device.json"]
    assert seen
    assert seen[0].stage is JobStage.SUPPORT_BUNDLE
