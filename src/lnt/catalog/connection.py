"""Фабрики SQLite-соединений и транзакций каталога."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final
from urllib.parse import quote

from lnt.app_paths import resolve_app_paths
from lnt.catalog.lock import catalog_writer_lock

DEFAULT_BUSY_TIMEOUT_MS: Final = 5_000
DEFAULT_LOCK_TIMEOUT_S: Final = 5.0


def _casefold(value: str) -> str:
    return value.casefold()


def catalog_path(path: Path | None = None) -> Path:
    """Возвращает внедрённый путь либо LocalAppData-путь приложения."""
    return resolve_app_paths().catalog_db if path is None else path


def _configure(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.create_function("casefold", 1, _casefold, deterministic=True)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")


@contextmanager
def open_catalog_reader(path: Path | None = None) -> Generator[sqlite3.Connection]:
    """Открывает существующий каталог строго read-only."""
    selected = catalog_path(path).resolve()
    uri = f"file:{quote(selected.as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    try:
        _configure(connection)
        yield connection
    finally:
        connection.close()


@contextmanager
def writer_transaction(
    path: Path | None = None,
    *,
    lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
) -> Generator[sqlite3.Connection]:
    """Удерживает process-lock и одну атомарную SQLite writer-транзакцию."""
    selected = catalog_path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    lock_path = selected.with_suffix(f"{selected.suffix}.lock")
    with catalog_writer_lock(lock_path, timeout_s=lock_timeout_s):
        connection = sqlite3.connect(selected, isolation_level=None)
        try:
            _configure(connection)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
        finally:
            connection.close()
