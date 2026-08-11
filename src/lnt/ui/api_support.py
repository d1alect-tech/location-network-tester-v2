"""Общие безопасные адаптеры новых HTTP API."""

import sqlite3
from pathlib import Path

from fastapi import HTTPException, status

from lnt.catalog.connection import open_catalog_reader
from lnt.catalog.query_repository import CatalogQueryRepository


def session_directory(session_id: str, catalog_db: Path) -> Path:
    """Разрешает ID только через каталог, не объединяя пользовательский ввод с путём."""
    try:
        with open_catalog_reader(catalog_db) as connection:
            row = CatalogQueryRepository(connection).find(session_id)
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="каталог временно недоступен",
        ) from error
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="сессия не найдена")
    return Path(row.storage_path)


def catalog_unavailable(error: sqlite3.Error | OSError) -> HTTPException:
    """Преобразует инфраструктурную ошибку каталога в 503."""
    del error
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="каталог временно недоступен",
    )
