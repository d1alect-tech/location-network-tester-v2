"""HTTP API фильтруемого каталога с cursor pagination."""

import base64
import binascii
import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from lnt.catalog.connection import catalog_path, open_catalog_reader
from lnt.catalog.query_models import CatalogCursor, CatalogFilters
from lnt.catalog.query_repository import CatalogQueryRepository
from lnt.catalog.reconcile import catalog_status
from lnt.ui.api_support import catalog_unavailable
from lnt.ui.models_catalog import (
    CatalogPageResponse,
    CatalogQuery,
    CatalogSessionResponse,
    HealthFacetsResponse,
    ReindexRunResponse,
    ReindexStatusResponse,
)

router = APIRouter(prefix="/api/catalog")
CatalogQueryParams = Annotated[CatalogQuery, Query()]


def _encode(cursor: CatalogCursor | None) -> str | None:
    if cursor is None:
        return None
    raw = json.dumps(
        [cursor.created_utc, cursor.session_id, cursor.storage_path], separators=(",", ":")
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode(raw: str | None) -> CatalogCursor | None:
    if raw is None:
        return None
    try:
        values = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        created, session_id, storage_path = values
        if not isinstance(session_id, str) or not isinstance(storage_path, str):
            return _invalid_cursor()
        return CatalogCursor(created_utc=created, session_id=session_id, storage_path=storage_path)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "некорректный cursor") from error


def _invalid_cursor() -> CatalogCursor:
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "некорректный cursor")


@router.get(
    "/sessions",
    response_model_exclude_none=True,
)
def sessions(query: CatalogQueryParams) -> CatalogPageResponse:
    """Возвращает фильтруемую страницу без путей по умолчанию."""
    filters = CatalogFilters(
        health=query.health,
        session_type=query.session_type,
        source=query.source,
        profile=query.profile,
        label=query.label,
        tag=query.tag,
        created_from=query.created_from,
        created_to=query.created_to,
    )
    try:
        with open_catalog_reader(catalog_path()) as connection:
            page = CatalogQueryRepository(connection).page(
                filters,
                _decode(query.cursor),
                query.page_size,
            )
    except (sqlite3.Error, OSError) as error:
        raise catalog_unavailable(error) from error
    return CatalogPageResponse(
        items=tuple(
            CatalogSessionResponse(
                id=item.session_id,
                health=item.health,
                created_utc=item.created_utc,
                source=item.source,
                session_type=item.session_type,
                profile=item.profile,
                label=item.label,
                storage_path=item.storage_path if query.include_paths else None,
            )
            for item in page.items
        ),
        next_cursor=_encode(page.next_cursor),
    )


@router.get("/health-facets")
def health_facets() -> HealthFacetsResponse:
    """Возвращает health facets всего каталога."""
    try:
        with open_catalog_reader(catalog_path()) as connection:
            counts = CatalogQueryRepository(connection).health_facets()
    except (sqlite3.Error, OSError) as error:
        raise catalog_unavailable(error) from error
    return HealthFacetsResponse(counts=counts)


@router.get("/reindex-status")
def reindex_status() -> ReindexStatusResponse:
    """Возвращает статус последней переиндексации без raw root path."""
    try:
        payload = catalog_status(catalog_path())
    except (sqlite3.Error, OSError) as error:
        raise catalog_unavailable(error) from error
    last = payload["last_reconcile"]
    return ReindexStatusResponse(
        health=payload["health"],
        last_reconcile=None
        if last is None
        else ReindexRunResponse(
            completed_utc=str(last["completed_utc"]),
            scanned=int(last["scanned"]),
            changed=int(last["changed"]),
            deleted=int(last["deleted"]),
            root_path=None,
        ),
    )
