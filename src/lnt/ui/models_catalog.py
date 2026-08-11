"""Pydantic-контракты чтения каталога."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from lnt.catalog.query_models import SessionHealth


class CatalogSessionResponse(BaseModel):
    """Безопасная строка каталога без пути по умолчанию."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    health: str
    created_utc: str | None
    source: str | None
    session_type: str | None
    profile: str | None
    label: str | None
    storage_path: str | None = None


class CatalogPageResponse(BaseModel):
    """Одна cursor-страница каталога."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    items: tuple[CatalogSessionResponse, ...]
    next_cursor: str | None


class HealthFacetsResponse(BaseModel):
    """Счётчики строк по health."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    counts: dict[str, int]


class ReindexRunResponse(BaseModel):
    """Метаданные последней сверки без раскрытия корня по умолчанию."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    completed_utc: str
    scanned: int
    changed: int
    deleted: int
    root_path: str | None = None


class ReindexStatusResponse(BaseModel):
    """Текущее состояние disposable-каталога."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    health: dict[str, int]
    last_reconcile: ReindexRunResponse | None


class CatalogQuery(BaseModel):
    """Проверенные query-параметры списка сессий."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None
    health: SessionHealth | None = None
    session_type: str | None = None
    source: str | None = None
    profile: str | None = None
    label: str | None = None
    tag: str | None = None
    created_from: str | None = None
    created_to: str | None = None
    include_paths: bool = False
