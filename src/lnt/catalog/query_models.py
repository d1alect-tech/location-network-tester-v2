"""Типизированные параметры и результаты запросов каталога."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SessionHealth(StrEnum):
    """Допустимые health-фильтры каталога."""

    OK = "ok"
    CORRUPT_MANIFEST = "corrupt_manifest"
    MISSING_FILES = "missing_files"
    PARTIAL = "partial"
    DUPLICATE_ID = "duplicate_id"
    CONTEXT_INVALID = "context_invalid"
    ANALYSIS_INVALID = "analysis_invalid"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogFilters:
    """Закрытый набор параметризованных фильтров."""

    health: SessionHealth | None = None
    session_type: str | None = None
    source: str | None = None
    profile: str | None = None
    label: str | None = None
    tag: str | None = None
    created_from: str | None = None
    created_to: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogCursor:
    """Последний ключ стабильной сортировки страницы."""

    created_utc: str | None
    session_id: str
    storage_path: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogRow:
    """Внутренняя строка каталога с путём для доверенных адаптеров."""

    storage_path: str
    session_id: str
    health: str
    created_utc: str | None
    source: str | None
    session_type: str | None
    profile: str | None
    label: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogPage:
    """Одна выборка и ключ продолжения."""

    items: tuple[CatalogRow, ...]
    next_cursor: CatalogCursor | None
