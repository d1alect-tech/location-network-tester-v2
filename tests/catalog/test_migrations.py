"""Контракт миграций и безопасной перестройки каталога."""

import sqlite3
from pathlib import Path

import pytest

from lnt.catalog import CatalogDowngradeError, apply_migrations, open_catalog_reader
from lnt.catalog.migrations import MIGRATIONS


def test_migrations_are_ordered_and_second_run_is_noop(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "local" / "LNT" / "catalog.sqlite3"

    # When
    first = apply_migrations(catalog_path)
    second = apply_migrations(catalog_path)

    # Then
    assert first == tuple(migration.version for migration in MIGRATIONS)
    assert second == ()
    with open_catalog_reader(catalog_path) as connection:
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version",
        ).fetchall()
    assert [row[0] for row in versions] == [migration.version for migration in MIGRATIONS]


def test_downgrade_is_rejected_with_typed_error(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "catalog.sqlite3"
    apply_migrations(catalog_path)

    # When / Then
    with pytest.raises(CatalogDowngradeError) as raised:
        apply_migrations(catalog_path, target_version=0)
    assert raised.value.reason_code == "catalog_downgrade_unsupported"
    assert "не поддерживается" in str(raised.value)


def test_rebuild_does_not_touch_runtime_database(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "catalog.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    runtime_bytes = b"runtime-history-owned-by-todo-16\x00\xff"
    runtime_path.write_bytes(runtime_bytes)
    apply_migrations(catalog_path)

    # When
    catalog_path.unlink()
    apply_migrations(catalog_path)

    # Then
    assert runtime_path.read_bytes() == runtime_bytes
    with sqlite3.connect(catalog_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'",
            )
        }
    assert "jobs" not in tables
    assert {"sessions", "artifact_recipes", "experiments"} <= tables
