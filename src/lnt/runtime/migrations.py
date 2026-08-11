"""Независимые миграции базы исполнения задач."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True, slots=True)
class Migration:
    """Одна необратимая версия схемы runtime-базы."""

    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: Final = (
    Migration(
        1,
        "durable_jobs",
        (
            """CREATE TABLE jobs (
                queue_order INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                operation_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1),
                input_reference TEXT,
                result_reference TEXT,
                progress TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT,
                created_utc TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            )""",
            """CREATE TABLE job_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                snapshot TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                UNIQUE(job_id, version)
            )""",
            "CREATE INDEX idx_jobs_status_order ON jobs(status, queue_order)",
            "CREATE INDEX idx_job_events_job ON job_events(job_id, event_id)",
        ),
    ),
)


def apply_migrations(path: Path) -> tuple[int, ...]:
    """Атомарно применяет только миграции runtime-хранилища."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS runtime_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_utc TEXT NOT NULL
            )""",
        )
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM runtime_schema_migrations",
        ).fetchone()
        current = int(row[0])
        applied: list[int] = []
        for migration in MIGRATIONS:
            if migration.version <= current:
                continue
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                """INSERT INTO runtime_schema_migrations(version, name, applied_utc)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))""",
                (migration.version, migration.name),
            )
            applied.append(migration.version)
        connection.commit()
    return tuple(applied)
