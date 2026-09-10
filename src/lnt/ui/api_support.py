"""Общие безопасные адаптеры новых HTTP API."""

import sqlite3
from pathlib import Path

from fastapi import HTTPException, status

from lnt.catalog.connection import open_catalog_reader
from lnt.catalog.query_repository import CatalogQueryRepository
from lnt.errors import InputError
from lnt.ui.sessions import SessionAmbiguousError, SessionNotFoundError, resolve_session_dir


def session_directory(session_id: str, catalog_db: Path, root: Path) -> Path:
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
    try:
        directory = resolve_session_dir(root, session_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="сессия не найдена"
        ) from error
    except SessionAmbiguousError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="идентификатор сессии неоднозначен",
        ) from error
    except InputError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    try:
        indexed_directory = Path(row.storage_path).resolve(strict=True)
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="сессия не найдена"
        ) from error
    if directory.resolve(strict=True) != indexed_directory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="сессия не найдена")
    return directory


def catalog_unavailable(error: sqlite3.Error | OSError) -> HTTPException:
    """Преобразует инфраструктурную ошибку каталога в 503."""
    del error
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="каталог временно недоступен",
    )
