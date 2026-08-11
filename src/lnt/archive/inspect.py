"""Проверка структуры и содержимого ZIP без материализации."""

from __future__ import annotations

import hashlib
import zipfile
from typing import TYPE_CHECKING

from .errors import ArchiveError
from .manifest import parse_manifest
from .models import MANIFEST_NAME, ArchiveLimits, ArchivePlan
from .paths import collision_key, ensure_regular_file, validate_member_name

if TYPE_CHECKING:
    from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def inspect_archive(  # noqa: C901,PLR0912 - single ZIP trust boundary
    path: Path, limits: ArchiveLimits | None = None
) -> ArchivePlan:
    """Проверяет schema, namespace, limits, размеры и SHA-256 всех файлов."""
    effective = limits or ArchiveLimits()
    try:
        compressed_bytes = path.stat().st_size
    except OSError as error:
        raise ArchiveError(f"архив недоступен: {path}") from error
    if compressed_bytes > effective.max_compressed_bytes:
        raise ArchiveError("превышен предел сжатого архива")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names.count(MANIFEST_NAME) != 1:
                raise ArchiveError("manifest должен встречаться ровно один раз")
            manifest_info = infos[names.index(MANIFEST_NAME)]
            if manifest_info.file_size > effective.max_per_file_bytes:
                raise ArchiveError("manifest превышает per-file limit")
            manifest = parse_manifest(
                _read_bounded(archive, manifest_info, effective.max_per_file_bytes)
            )
            data_infos = tuple(info for info in infos if info.filename != MANIFEST_NAME)
            if len(data_infos) > effective.max_file_count:
                raise ArchiveError("превышен предел количества файлов")
            by_path: dict[str, zipfile.ZipInfo] = {}
            for info in data_infos:
                ensure_regular_file(info)
                safe = validate_member_name(info.filename)
                key = collision_key(safe)
                if key in by_path:
                    raise ArchiveError("дубликат или case-fold коллизия ZIP")
                by_path[key] = info
            expected = {collision_key(entry.path): entry for entry in manifest.entries}
            if set(by_path) != set(expected):
                raise ArchiveError("состав ZIP не совпадает с manifest")
            expanded = 0
            for key, info in by_path.items():
                entry = expected[key]
                if entry.size > effective.max_per_file_bytes:
                    raise ArchiveError(f"файл превышает per-file limit: {entry.path}")
                digest, actual = _hash_member(archive, info, effective.max_per_file_bytes)
                expanded += actual
                if expanded > effective.max_expanded_bytes:
                    raise ArchiveError("превышен предел распакованных данных")
                if actual != entry.size or digest != entry.sha256:
                    raise ArchiveError(f"размер или SHA-256 не совпадает: {entry.path}")
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ArchiveError("повреждённый или неподдерживаемый ZIP") from error
    return ArchivePlan(
        manifest=manifest,
        compressed_bytes=compressed_bytes,
        expanded_bytes=expanded,
    )


def _read_bounded(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    with archive.open(info) as source:
        payload = source.read(limit + 1)
    if len(payload) > limit:
        raise ArchiveError(f"файл превышает stream limit: {info.filename}")
    return payload


def _hash_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with archive.open(info) as source:
        while chunk := source.read(_CHUNK_SIZE):
            total += len(chunk)
            if total > limit:
                raise ArchiveError(f"файл превышает stream limit: {info.filename}")
            digest.update(chunk)
    return digest.hexdigest(), total
