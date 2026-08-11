from __future__ import annotations

import json
import stat
import zipfile
from typing import TYPE_CHECKING

import pytest

from lnt.archive import ArchiveError, restore_archive

if TYPE_CHECKING:
    from pathlib import Path


def _write_archive(path: Path, names: tuple[str, ...], *, symlink: bool = False) -> None:
    entries = [
        {
            "path": name,
            "size": 1,
            "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
        }
        for name in names
    ]
    manifest = {
        "archive_schema_version": 1,
        "provenance": {
            "build_id": "test",
            "created_at": "2026-08-11T00:00:00Z",
            "source_session_ids": ["s"],
            "source_experiment_ids": [],
        },
        "entries": entries,
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("archive-manifest.json", json.dumps(manifest))
        for index, name in enumerate(names):
            info = zipfile.ZipInfo(name)
            if symlink and index == 0:
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"a")


@pytest.mark.parametrize(
    ("names", "symlink"),
    [
        (("sessions/s/../evil",), False),
        (("sessions/s/C:\\evil",), False),
        (("//server/share/evil",), False),
        (("//./device",), False),
        (("sessions/s/file.txt:stream",), False),
        (("sessions/s/CON.txt",), False),
        (("sessions/s/file.",), False),
        (("sessions/s/file ",), False),
        (("sessions/s/Data/x", "sessions/s/data/X"), False),
        (("sessions/s/link",), True),
    ],
    ids=[
        "parent",
        "drive",
        "unc",
        "device",
        "ads",
        "reserved",
        "trailing-dot",
        "trailing-space",
        "casefold-collision",
        "symlink",
    ],
)
def test_restore_rejects_hostile_path_before_final_destination(
    tmp_path: Path,
    names: tuple[str, ...],
    symlink: bool,
) -> None:
    archive_path = tmp_path / "hostile.zip"
    destination = tmp_path / "restored"
    _write_archive(archive_path, names, symlink=symlink)

    with pytest.raises(ArchiveError):
        restore_archive(archive_path, destination)

    assert not destination.exists()


def test_restore_rejects_duplicate_zip_member_before_final_destination(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.zip"
    destination = tmp_path / "restored"
    manifest = {
        "archive_schema_version": 1,
        "provenance": {
            "build_id": "test",
            "created_at": "2026-08-11T00:00:00Z",
            "source_session_ids": ["s"],
            "source_experiment_ids": [],
        },
        "entries": [
            {
                "path": "sessions/s/safe.txt",
                "size": 1,
                "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
            }
        ],
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("archive-manifest.json", json.dumps(manifest))
        archive.writestr("sessions/s/safe.txt", b"a")
        archive.writestr("sessions/s/safe.txt", b"a")

    with pytest.raises(ArchiveError):
        restore_archive(archive_path, destination)

    assert not destination.exists()
