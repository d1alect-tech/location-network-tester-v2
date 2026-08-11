"""SQL операции path-keyed reconcile-проекций."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

    from lnt.catalog.reconcile_models import CatalogSession

_COLUMNS = (
    "storage_path, session_id, path_fingerprint, health, base_health, manifest_schema, "
    "created_utc, "
    "source, session_type, profile, sample_rate_hz, duration_s, sample_count, label, channels"
)
_UPSERT = (
    f"INSERT INTO catalog_sessions ({_COLUMNS}) "  # noqa: S608 - compile-time columns
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(storage_path) DO UPDATE SET session_id=excluded.session_id, "
    "path_fingerprint=excluded.path_fingerprint, health=excluded.health, "
    "base_health=excluded.base_health, manifest_schema=excluded.manifest_schema, "
    "created_utc=excluded.created_utc, source=excluded.source, "
    "session_type=excluded.session_type, profile=excluded.profile, "
    "sample_rate_hz=excluded.sample_rate_hz, duration_s=excluded.duration_s, "
    "sample_count=excluded.sample_count, label=excluded.label, channels=excluded.channels"
)


def _values(item: CatalogSession) -> tuple[str | int | float | None, ...]:
    return (
        item.storage_path,
        item.session_id,
        item.path_fingerprint,
        item.health,
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
    )


@dataclass(frozen=True, slots=True)
class ReconcileRepository:
    """Сохраняет disposable-проекции в текущей writer-транзакции."""

    connection: sqlite3.Connection

    def fingerprints(self) -> dict[str, str]:
        """Возвращает сохранённые fingerprints по абсолютному пути."""
        rows = self.connection.execute(
            "SELECT storage_path, path_fingerprint FROM catalog_sessions",
        )
        return {str(row[0]): str(row[1]) for row in rows}

    def upsert_many(
        self,
        items: tuple[CatalogSession, ...],
        changed_existing_paths: tuple[str, ...],
    ) -> None:
        """Пакетно заменяет изменившиеся проекции и их context-индексы."""
        self.connection.executemany(_UPSERT, (_values(item) for item in items))
        self.connection.executemany(
            "DELETE FROM catalog_context_fields WHERE storage_path = ?",
            ((path,) for path in changed_existing_paths),
        )
        self.connection.executemany(
            "DELETE FROM catalog_context_tags WHERE storage_path = ?",
            ((path,) for path in changed_existing_paths),
        )
        self.connection.executemany(
            "INSERT INTO catalog_context_fields VALUES (?, ?, ?)",
            (
                (item.storage_path, key, value)
                for item in items
                for key, value in item.context_fields
            ),
        )
        self.connection.executemany(
            "INSERT INTO catalog_context_tags VALUES (?, ?)",
            ((item.storage_path, tag) for item in items for tag in item.context_tags),
        )

    def delete_paths(self, paths: tuple[str, ...]) -> None:
        """Удаляет исчезнувшие path-keyed проекции каскадно."""
        self.connection.executemany(
            "DELETE FROM catalog_sessions WHERE storage_path = ?",
            ((path,) for path in paths),
        )

    def mark_duplicates(self) -> None:
        """Восстанавливает base health и помечает все повторяющиеся IDs."""
        self.connection.execute("UPDATE catalog_sessions SET health = base_health")
        self.connection.execute(
            """UPDATE catalog_sessions SET health = 'duplicate_id'
            WHERE session_id IN (
                SELECT session_id FROM catalog_sessions
                GROUP BY session_id HAVING COUNT(*) > 1
            )""",
        )
