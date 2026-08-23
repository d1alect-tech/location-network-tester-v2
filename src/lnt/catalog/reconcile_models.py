"""Типы результатов сканирования и обслуживания каталога."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from pathlib import Path

type SessionHealth = Literal[
    "ok",
    "corrupt_manifest",
    "missing_files",
    "partial",
    "duplicate_id",
    "context_invalid",
    "analysis_invalid",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class ScannedDirectory:
    """Безопасно обнаруженный непосредственный каталог сессии."""

    path: Path
    fingerprint: str
    reparse_point: bool
    manifest_text: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogSession:
    """Path-keyed проекция, сохраняющая дубликаты session ID."""

    storage_path: str
    session_id: str
    path_fingerprint: str
    health: SessionHealth
    manifest_schema: int | None = None
    created_utc: str | None = None
    source: str | None = None
    session_type: str | None = None
    profile: str | None = None
    sample_rate_hz: float | None = None
    duration_s: float | None = None
    sample_count: int | None = None
    label: str | None = None
    channels: str | None = None
    context_fields: tuple[tuple[str, str], ...] = ()
    context_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ReconcileResult:
    """Счётчики одной атомарной сверки."""

    scanned: int
    inserted: int
    updated: int
    skipped: int
    deleted: int


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyResult:
    """Расхождения файловой системы и сохранённых fingerprints.

    ``baseline_created`` поднимается в deep-режиме (GAP-1), когда снимок
    содержимого raw-файлов был создан при этом запуске (drift тогда пуст).
    """

    drift_paths: tuple[str, ...]
    baseline_created: bool = False


class CatalogStatus(TypedDict):
    """JSON-совместимый статус каталога."""

    health: dict[str, int]
    last_reconcile: dict[str, str | int] | None
