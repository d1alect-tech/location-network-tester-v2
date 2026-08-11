"""Детерминированная сборка явной выборки файлов LNT."""

from __future__ import annotations

import hashlib
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from lnt.analysis_store.identity import CodeIdentity

from .errors import ArchiveError
from .manifest import manifest_bytes
from .models import MANIFEST_NAME, ArchiveEntry, ArchiveManifest, ArchivePath, ArchiveProvenance
from .paths import validate_member_name

if TYPE_CHECKING:
    from pathlib import Path

_ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
_EXCLUDED_NAMES: Final = frozenset({"catalog.sqlite3"})
_EXCLUDED_SUFFIXES: Final = (".log", ".lock")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportSelection:
    """Явная выборка ID относительно session root."""

    root: Path
    session_ids: tuple[str, ...]
    experiment_ids: tuple[str, ...]


def create_archive(output: Path, selection: ExportSelection) -> ArchiveManifest:
    """Создаёт новый ZIP без секретов, логов и disposable catalog."""
    if output.exists():
        raise ArchiveError(f"архив уже существует: {output}")
    sources = _selected_sources(selection)
    files = tuple(sorted(_collect_files(sources), key=lambda item: str(item[0])))
    entries = tuple(_entry(archive_path, source_path) for archive_path, source_path in files)
    manifest = ArchiveManifest(
        provenance=ArchiveProvenance(
            build_id=CodeIdentity.current().identity_string,
            created_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            source_session_ids=selection.session_ids,
            source_experiment_ids=selection.experiment_ids,
        ),
        entries=entries,
    )
    temporary = output.with_name(f".{output.name}.partial-{uuid.uuid4().hex}")
    try:
        with zipfile.ZipFile(temporary, "x", allowZip64=True) as archive:
            _write_bytes(archive, MANIFEST_NAME, manifest_bytes(manifest), zipfile.ZIP_DEFLATED)
            for archive_path, source_path in files:
                compression = (
                    zipfile.ZIP_STORED
                    if source_path.suffix.lower() == ".npy"
                    else zipfile.ZIP_DEFLATED
                )
                _write_file(archive, archive_path, source_path, compression)
        temporary.rename(output)
    except (OSError, zipfile.BadZipFile) as error:
        raise ArchiveError("не удалось создать архив") from error
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def _selected_sources(selection: ExportSelection) -> tuple[tuple[ArchivePath, Path], ...]:
    if not selection.session_ids and not selection.experiment_ids:
        raise ArchiveError("нужно выбрать session или experiment")
    result: list[tuple[ArchivePath, Path]] = []
    for kind, base, identifiers in (
        ("sessions", selection.root, selection.session_ids),
        ("experiments", selection.root.parent / "experiments", selection.experiment_ids),
    ):
        for identifier in identifiers:
            validate_member_name(identifier)
            if "/" in identifier or "\\" in identifier:
                raise ArchiveError(f"ID должен быть одним компонентом: {identifier!r}")
            source = base / identifier
            if not source.is_dir():
                raise ArchiveError(f"выбранный объект не найден: {kind}/{identifier}")
            result.append((ArchivePath(f"{kind}/{identifier}"), source))
    return tuple(result)


def _collect_files(sources: tuple[tuple[ArchivePath, Path], ...]) -> list[tuple[ArchivePath, Path]]:
    result: list[tuple[ArchivePath, Path]] = []
    for prefix, directory in sources:
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ArchiveError(f"source symlink запрещён: {path}")
            if (
                not path.is_file()
                or path.name in _EXCLUDED_NAMES
                or path.name.endswith(_EXCLUDED_SUFFIXES)
            ):
                continue
            relative = path.relative_to(directory).as_posix()
            result.append((validate_member_name(f"{prefix}/{relative}"), path))
    return result


def _entry(path: ArchivePath, source: Path) -> ArchiveEntry:
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return ArchiveEntry(path=path, size=size, sha256=digest.hexdigest())


def _write_bytes(archive: zipfile.ZipFile, name: str, payload: bytes, compression: int) -> None:
    info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
    info.compress_type = compression
    info.create_system = 0
    info.external_attr = 0
    archive.writestr(info, payload)


def _write_file(
    archive: zipfile.ZipFile,
    path: ArchivePath,
    source: Path,
    compression: int,
) -> None:
    info = zipfile.ZipInfo(str(path), _ZIP_TIMESTAMP)
    info.compress_type = compression
    info.create_system = 0
    info.external_attr = 0
    with (
        source.open("rb") as input_stream,
        archive.open(info, "w", force_zip64=True) as output_stream,
    ):
        while chunk := input_stream.read(1024 * 1024):
            output_stream.write(chunk)
