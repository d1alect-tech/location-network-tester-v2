"""Явные упорядоченные SQL-миграции перестраиваемого каталога."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lnt.catalog.lock import catalog_writer_lock
from lnt.errors import InputError


@dataclass(frozen=True, slots=True)
class Migration:
    """Одна необратимая версия схемы каталога."""

    version: int
    name: str
    statements: tuple[str, ...]


class CatalogDowngradeError(InputError):
    """Запрошена неподдерживаемая обратная миграция каталога."""

    reason_code: Final = "catalog_downgrade_unsupported"

    def __init__(self, *, current: int, target: int) -> None:
        """Фиксирует текущую и запрошенную версии."""
        super().__init__(
            f"понижение схемы каталога не поддерживается: текущая {current}, запрошена {target}",
        )
        self.current: int = current
        self.target: int = target


MIGRATIONS: Final = (
    Migration(
        1,
        "projection_tables",
        (
            """CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            storage_path TEXT NOT NULL,
            path_fingerprint TEXT NOT NULL UNIQUE,
            health TEXT NOT NULL,
            manifest_schema INTEGER,
            created_utc TEXT,
            source TEXT,
            session_type TEXT,
            profile TEXT,
            sample_rate_hz REAL,
            duration_s REAL,
            sample_count INTEGER,
            label TEXT,
            channels TEXT
        )""",
            """CREATE TABLE context_fields (
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            field_key TEXT NOT NULL,
            field_value TEXT NOT NULL,
            PRIMARY KEY (session_id, field_key)
        )""",
            """CREATE TABLE context_tags (
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            PRIMARY KEY (session_id, tag)
        )""",
            """CREATE TABLE artifact_recipes (
            recipe_sha256 TEXT PRIMARY KEY CHECK(length(recipe_sha256) = 64),
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            artifact_key TEXT NOT NULL,
            storage_ref TEXT NOT NULL,
            UNIQUE (session_id, artifact_key)
        )""",
            """CREATE TABLE experiments (
            id TEXT PRIMARY KEY,
            storage_ref TEXT NOT NULL UNIQUE,
            health TEXT NOT NULL
        )""",
            """CREATE TABLE experiment_members (
            experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
            session_id TEXT NOT NULL,
            session_storage_ref TEXT NOT NULL,
            artifact_key TEXT,
            recipe_sha256 TEXT,
            PRIMARY KEY (experiment_id, ordinal),
            CHECK ((artifact_key IS NULL) = (recipe_sha256 IS NULL))
        )""",
            "CREATE INDEX idx_artifact_recipes_session ON artifact_recipes(session_id)",
            "CREATE INDEX idx_experiment_members_session ON experiment_members(session_id)",
        ),
    ),
    Migration(
        2,
        "reconcile_projections",
        (
            """CREATE TABLE catalog_sessions (
            storage_path TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            path_fingerprint TEXT NOT NULL,
            health TEXT NOT NULL,
            base_health TEXT NOT NULL,
            manifest_schema INTEGER,
            created_utc TEXT,
            source TEXT,
            session_type TEXT,
            profile TEXT,
            sample_rate_hz REAL,
            duration_s REAL,
            sample_count INTEGER,
            label TEXT,
            channels TEXT
        )""",
            "CREATE INDEX idx_catalog_sessions_id ON catalog_sessions(session_id)",
            "CREATE INDEX idx_catalog_sessions_health ON catalog_sessions(health)",
            """CREATE TABLE catalog_context_fields (
            storage_path TEXT NOT NULL REFERENCES catalog_sessions(storage_path) ON DELETE CASCADE,
            field_key TEXT NOT NULL,
            field_value TEXT NOT NULL,
            PRIMARY KEY (storage_path, field_key)
        )""",
            """CREATE TABLE catalog_context_tags (
            storage_path TEXT NOT NULL REFERENCES catalog_sessions(storage_path) ON DELETE CASCADE,
            tag TEXT NOT NULL,
            PRIMARY KEY (storage_path, tag)
        )""",
            """CREATE TABLE reconcile_runs (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            root_path TEXT NOT NULL,
            completed_utc TEXT NOT NULL,
            scanned INTEGER NOT NULL,
            changed INTEGER NOT NULL,
            deleted INTEGER NOT NULL
        )""",
        ),
    ),
    Migration(
        3,
        "catalog_query_indexes",
        (
            (
                "CREATE INDEX idx_catalog_sessions_page ON catalog_sessions("
                "created_utc DESC, session_id, storage_path)"
            ),
            "CREATE INDEX idx_catalog_sessions_type ON catalog_sessions(session_type)",
            "CREATE INDEX idx_catalog_sessions_source ON catalog_sessions(source)",
            "CREATE INDEX idx_catalog_sessions_profile ON catalog_sessions(profile)",
            "CREATE INDEX idx_catalog_context_tags_tag ON catalog_context_tags(tag, storage_path)",
        ),
    ),
)


def apply_migrations(path: Path, *, target_version: int | None = None) -> tuple[int, ...]:
    """Применяет недостающие версии атомарно и возвращает их номера."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    with catalog_writer_lock(lock_path, timeout_s=5.0):
        connection = sqlite3.connect(path, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_utc TEXT NOT NULL
                )""",
            )
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations",
            ).fetchone()
            current = int(row[0])
            target = MIGRATIONS[-1].version if target_version is None else target_version
            if target < current:
                raise CatalogDowngradeError(current=current, target=target)
            applied: list[int] = []
            for migration in MIGRATIONS:
                if current < migration.version <= target:
                    for statement in migration.statements:
                        connection.execute(statement)
                    connection.execute(
                        """INSERT INTO schema_migrations(version, name, applied_utc)
                        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))""",
                        (migration.version, migration.name),
                    )
                    applied.append(migration.version)
            connection.commit()
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()
    return tuple(applied)
