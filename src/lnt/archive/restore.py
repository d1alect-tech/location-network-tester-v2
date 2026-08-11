"""Crash-safe потоковая материализация проверенного архива."""

from __future__ import annotations

import hashlib
import os
import uuid
import zipfile
from typing import TYPE_CHECKING

from .errors import ArchiveError
from .inspect import inspect_archive
from .models import ArchiveLimits, ArchivePlan

if TYPE_CHECKING:
    from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def restore_archive(  # noqa: C901 - streaming transaction boundary
    archive_path: Path,
    destination: Path,
    *,
    limits: ArchiveLimits | None = None,
    dry_run: bool = False,
) -> ArchivePlan:
    """Проверяет архив и одним rename публикует один новый archive root."""
    if destination.exists():
        raise ArchiveError(f"назначение уже существует: {destination}")
    if not destination.parent.is_dir():
        raise ArchiveError(f"родитель назначения не существует: {destination.parent}")
    effective = limits or ArchiveLimits()
    plan = inspect_archive(archive_path, effective)
    if dry_run:
        return plan
    staging = destination.parent / f".lnt-import-staging-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
    except OSError as error:
        raise ArchiveError("не удалось создать staging на целевом томе") from error
    try:
        with zipfile.ZipFile(archive_path) as archive:
            by_name = {info.filename: info for info in archive.infolist()}
            expanded = 0
            for entry in plan.manifest.entries:
                target = staging.joinpath(*str(entry.path).split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                written = 0
                with archive.open(by_name[str(entry.path)]) as source, target.open("xb") as output:
                    while chunk := source.read(_CHUNK_SIZE):
                        written += len(chunk)
                        expanded += len(chunk)
                        if written > effective.max_per_file_bytes:
                            raise ArchiveError(  # noqa: TRY301
                                f"stream превысил per-file limit: {entry.path}"
                            )
                        if expanded > effective.max_expanded_bytes:
                            raise ArchiveError("stream превысил expanded limit")  # noqa: TRY301
                        output.write(chunk)
                        digest.update(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if written != entry.size or digest.hexdigest() != entry.sha256:
                    raise ArchiveError(  # noqa: TRY301
                        f"stream изменился после verify: {entry.path}"
                    )
        os.rename(staging, destination)  # noqa: PTH104 - crash injection seam
    except ArchiveError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ArchiveError(f"восстановление прервано; quarantine: {staging.name}") from error
    return plan
