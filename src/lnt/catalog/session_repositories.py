"""SQL-репозитории сессий и их context-проекций."""

import sqlite3
from dataclasses import dataclass

from lnt.catalog.models import ContextField, SessionProjection

_SESSION_COLUMNS = (
    "id, storage_path, path_fingerprint, health, manifest_schema, created_utc, "
    "source, session_type, profile, sample_rate_hz, duration_s, sample_count, label, channels"
)
_UPSERT_SESSION = (
    "INSERT INTO sessions (id, storage_path, path_fingerprint, health, manifest_schema, "
    "created_utc, source, session_type, profile, sample_rate_hz, duration_s, sample_count, "
    "label, channels) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET storage_path=excluded.storage_path, "
    "path_fingerprint=excluded.path_fingerprint, health=excluded.health, "
    "manifest_schema=excluded.manifest_schema, created_utc=excluded.created_utc, "
    "source=excluded.source, session_type=excluded.session_type, profile=excluded.profile, "
    "sample_rate_hz=excluded.sample_rate_hz, duration_s=excluded.duration_s, "
    "sample_count=excluded.sample_count, label=excluded.label, channels=excluded.channels"
)
_SELECT_SESSION = f"SELECT {_SESSION_COLUMNS} FROM sessions WHERE id = ?"  # noqa: S608
_SELECT_CONTEXT_FIELDS = """SELECT session_id, field_key, field_value
FROM context_fields WHERE session_id = ? ORDER BY field_key"""


def _session(row: sqlite3.Row) -> SessionProjection:
    return SessionProjection(
        id=row["id"],
        storage_path=row["storage_path"],
        path_fingerprint=row["path_fingerprint"],
        health=row["health"],
        manifest_schema=row["manifest_schema"],
        created_utc=row["created_utc"],
        source=row["source"],
        session_type=row["session_type"],
        profile=row["profile"],
        sample_rate_hz=row["sample_rate_hz"],
        duration_s=row["duration_s"],
        sample_count=row["sample_count"],
        label=row["label"],
        channels=row["channels"],
    )


@dataclass(frozen=True, slots=True)
class SessionRepository:
    """CRUD проекций обнаруженных сессий."""

    connection: sqlite3.Connection

    def upsert(self, item: SessionProjection) -> None:
        """Вставляет либо полностью обновляет проекцию evidence."""
        self.connection.execute(
            _UPSERT_SESSION,
            (
                item.id,
                item.storage_path,
                item.path_fingerprint,
                item.health,
                item.manifest_schema,
                item.created_utc,
                item.source,
                item.session_type,
                item.profile,
                item.sample_rate_hz,
                item.duration_s,
                item.sample_count,
                item.label,
                item.channels,
            ),
        )

    def get(self, session_id: str) -> SessionProjection | None:
        """Возвращает проекцию по stable session ID."""
        row = self.connection.execute(_SELECT_SESSION, (session_id,)).fetchone()
        return None if row is None else _session(row)

    def delete(self, session_id: str) -> None:
        """Удаляет только disposable-проекцию и её дочерние проекции."""
        self.connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


@dataclass(frozen=True, slots=True)
class ContextRepository:
    """Проекции полей и тегов context sidecar."""

    connection: sqlite3.Connection

    def replace(
        self,
        session_id: str,
        *,
        fields: tuple[ContextField, ...],
        tags: tuple[str, ...],
    ) -> None:
        """Атомарно заменяет производный context индекс сессии."""
        self.connection.execute("DELETE FROM context_fields WHERE session_id = ?", (session_id,))
        self.connection.execute("DELETE FROM context_tags WHERE session_id = ?", (session_id,))
        self.connection.executemany(
            "INSERT INTO context_fields(session_id, field_key, field_value) VALUES (?, ?, ?)",
            ((field.session_id, field.key, field.value) for field in fields),
        )
        self.connection.executemany(
            "INSERT INTO context_tags(session_id, tag) VALUES (?, ?)",
            ((session_id, tag) for tag in tags),
        )

    def fields(self, session_id: str) -> tuple[ContextField, ...]:
        """Читает поля контекста в стабильном порядке ключей."""
        rows = self.connection.execute(_SELECT_CONTEXT_FIELDS, (session_id,))
        return tuple(ContextField(row[0], row[1], row[2]) for row in rows)

    def tags(self, session_id: str) -> tuple[str, ...]:
        """Читает теги контекста в стабильном порядке."""
        rows = self.connection.execute(
            "SELECT tag FROM context_tags WHERE session_id = ? ORDER BY tag",
            (session_id,),
        )
        return tuple(row[0] for row in rows)
