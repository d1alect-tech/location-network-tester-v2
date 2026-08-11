"""Строгий JSON boundary manifest архива."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING

from .errors import ArchiveError
from .models import (
    ARCHIVE_SCHEMA_VERSION,
    SHA256_HEX_LENGTH,
    ArchiveEntry,
    ArchiveManifest,
    ArchiveProvenance,
)
from .paths import collision_key, validate_member_name

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue


def parse_manifest(payload: bytes) -> ArchiveManifest:
    """Преобразует недоверенный JSON в замкнутую модель v1."""
    try:
        raw = json.loads(payload)
        if not isinstance(raw, dict) or set(raw) != {
            "archive_schema_version",
            "provenance",
            "entries",
        }:
            raise ArchiveError("неверная структура manifest")
        version = raw["archive_schema_version"]
        provenance = _parse_provenance(raw["provenance"])
        raw_entries = raw["entries"]
        if not isinstance(raw_entries, list):
            raise ArchiveError("entries должен быть массивом")
        entries = tuple(_parse_entry(value) for value in raw_entries)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        raise ArchiveError("manifest не является допустимым JSON v1") from error
    if version != ARCHIVE_SCHEMA_VERSION:
        raise ArchiveError(f"неподдерживаемая версия manifest: {version!r}")
    keys = [collision_key(entry.path) for entry in entries]
    if len(keys) != len(set(keys)):
        raise ArchiveError("дубликат или case-fold коллизия в manifest")
    _validate_sources(provenance, entries)
    return ArchiveManifest(provenance=provenance, entries=entries)


def manifest_bytes(manifest: ArchiveManifest) -> bytes:
    """Кодирует manifest детерминированно."""
    value: JsonValue = {
        "archive_schema_version": manifest.archive_schema_version,
        "provenance": {
            "build_id": manifest.provenance.build_id,
            "created_at": manifest.provenance.created_at,
            "source_session_ids": list(manifest.provenance.source_session_ids),
            "source_experiment_ids": list(manifest.provenance.source_experiment_ids),
        },
        "entries": [
            {"path": str(entry.path), "size": entry.size, "sha256": entry.sha256}
            for entry in manifest.entries
        ],
    }
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _parse_provenance(value: JsonValue) -> ArchiveProvenance:
    if not isinstance(value, dict) or set(value) != {
        "build_id",
        "created_at",
        "source_session_ids",
        "source_experiment_ids",
    }:
        raise ArchiveError("неверная provenance")
    build_id = value["build_id"]
    created_at = value["created_at"]
    sessions = _parse_ids(value["source_session_ids"])
    experiments = _parse_ids(value["source_experiment_ids"])
    if not isinstance(build_id, str) or not build_id or not isinstance(created_at, str):
        raise ArchiveError("неверная provenance")
    return ArchiveProvenance(
        build_id=build_id,
        created_at=created_at,
        source_session_ids=sessions,
        source_experiment_ids=experiments,
    )


def _parse_ids(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ArchiveError("идентификаторы provenance должны быть строками")
    ids = tuple(item for item in value if isinstance(item, str))
    if len(ids) != len(set(ids)) or any(str(validate_member_name(item)) != item for item in ids):
        raise ArchiveError("небезопасные или повторные идентификаторы provenance")
    if any("/" in item or "\\" in item for item in ids):
        raise ArchiveError("идентификатор должен быть одним компонентом")
    return ids


def _parse_entry(value: JsonValue) -> ArchiveEntry:
    if not isinstance(value, Mapping) or set(value) != {"path", "size", "sha256"}:
        raise ArchiveError("неверная запись manifest")
    path, size, digest = value["path"], value["size"], value["sha256"]
    if not isinstance(path, str) or not isinstance(size, int) or isinstance(size, bool):
        raise ArchiveError("неверные path/size manifest")
    if size < 0 or not isinstance(digest, str) or len(digest) != SHA256_HEX_LENGTH:
        raise ArchiveError("неверные size/SHA-256 manifest")
    try:
        int(digest, 16)
    except ValueError as error:
        raise ArchiveError("SHA-256 manifest не hexadecimal") from error
    if digest != digest.lower():
        raise ArchiveError("SHA-256 manifest должен быть lowercase")
    return ArchiveEntry(path=validate_member_name(path), size=size, sha256=digest)


def _validate_sources(provenance: ArchiveProvenance, entries: tuple[ArchiveEntry, ...]) -> None:
    allowed = {
        *(f"sessions/{identifier}/" for identifier in provenance.source_session_ids),
        *(f"experiments/{identifier}/" for identifier in provenance.source_experiment_ids),
    }
    if not allowed or any(
        not any(str(entry.path).startswith(root) for root in allowed) for entry in entries
    ):
        raise ArchiveError("entry не принадлежит выбранному source ID")
