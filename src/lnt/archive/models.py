"""Типизированный контракт архива LNT v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, NewType

ARCHIVE_SCHEMA_VERSION: Final = 1
MANIFEST_NAME: Final = "archive-manifest.json"
SHA256_HEX_LENGTH: Final = 64
ArchivePath = NewType("ArchivePath", str)


@dataclass(frozen=True, slots=True, kw_only=True)
class ArchiveEntry:
    """Ожидаемый обычный файл и его содержимое."""

    path: ArchivePath
    size: int
    sha256: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ArchiveProvenance:
    """Происхождение явной выборки архива."""

    build_id: str
    created_at: str
    source_session_ids: tuple[str, ...]
    source_experiment_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ArchiveManifest:
    """Проверенный manifest версии 1."""

    provenance: ArchiveProvenance
    entries: tuple[ArchiveEntry, ...]
    archive_schema_version: int = ARCHIVE_SCHEMA_VERSION


@dataclass(frozen=True, slots=True, kw_only=True)
class ArchiveLimits:
    """Жёсткие пределы недоверенного ZIP."""

    max_compressed_bytes: int = 2 * 1024**3
    max_expanded_bytes: int = 8 * 1024**3
    max_file_count: int = 100_000
    max_per_file_bytes: int = 4 * 1024**3


@dataclass(frozen=True, slots=True, kw_only=True)
class ArchivePlan:
    """Результат list/verify/dry-run без записи."""

    manifest: ArchiveManifest
    compressed_bytes: int
    expanded_bytes: int
