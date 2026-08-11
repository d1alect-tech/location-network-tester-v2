"""Безопасные параметризованные запросы к disposable-каталогу."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lnt.catalog.query_models import CatalogCursor, CatalogFilters, CatalogPage, CatalogRow

if TYPE_CHECKING:
    import sqlite3

_COLUMNS = "storage_path, session_id, health, created_utc, source, session_type, profile, label"


@dataclass(frozen=True, slots=True)
class CatalogQueryRepository:
    """Параметризованные read-only запросы каталога."""

    connection: sqlite3.Connection

    def page(
        self,
        filters: CatalogFilters,
        cursor: CatalogCursor | None,
        page_size: int,
    ) -> CatalogPage:
        """Возвращает страницу в стабильном keyset-порядке."""
        clauses: list[str] = []
        values: list[str | int] = []
        equality = (
            ("health", filters.health.value if filters.health is not None else None),
            ("session_type", filters.session_type),
            ("source", filters.source),
            ("profile", filters.profile),
        )
        for column, value in equality:
            if value is not None:
                clauses.append(f"s.{column} = ?")
                values.append(value)
        if filters.label is not None:
            clauses.append("instr(casefold(COALESCE(s.label, '')), casefold(?)) > 0")
            values.append(filters.label)
        if filters.tag is not None:
            clauses.append(
                """EXISTS (SELECT 1 FROM catalog_context_tags t
                WHERE t.storage_path=s.storage_path AND t.tag=?)"""
            )
            values.append(filters.tag)
        if filters.created_from is not None:
            clauses.append("s.created_utc >= ?")
            values.append(filters.created_from)
        if filters.created_to is not None:
            clauses.append("s.created_utc <= ?")
            values.append(filters.created_to)
        if cursor is not None:
            clauses.append(
                """(COALESCE(s.created_utc, '') < COALESCE(?, '') OR
                (COALESCE(s.created_utc, '') = COALESCE(?, '') AND
                (s.session_id > ? OR (s.session_id = ? AND s.storage_path > ?))))"""
            )
            values.extend(
                [
                    cursor.created_utc or "",
                    cursor.created_utc or "",
                    cursor.session_id,
                    cursor.session_id,
                    cursor.storage_path,
                ]
            )
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute(
            "".join(
                (
                    f"SELECT {_COLUMNS} FROM catalog_sessions s{where} ",  # noqa: S608
                    "ORDER BY COALESCE(created_utc, '') DESC, ",
                    "session_id ASC, storage_path ASC LIMIT ?",
                )
            ),
            (*values, page_size + 1),
        ).fetchall()
        items = tuple(self._row(row) for row in rows[:page_size])
        next_cursor = None
        if len(rows) > page_size and items:
            last = items[-1]
            next_cursor = CatalogCursor(
                created_utc=last.created_utc,
                session_id=last.session_id,
                storage_path=last.storage_path,
            )
        return CatalogPage(items=items, next_cursor=next_cursor)

    def health_facets(self) -> dict[str, int]:
        """Считает строки каждого health."""
        rows = self.connection.execute(
            "SELECT health, COUNT(*) FROM catalog_sessions GROUP BY health ORDER BY health"
        )
        return {str(row[0]): int(row[1]) for row in rows}

    def find(self, session_id: str) -> CatalogRow | None:
        """Находит первую path-keyed строку stable session ID."""
        row = self.connection.execute(
            "".join(
                (
                    f"SELECT {_COLUMNS} FROM catalog_sessions WHERE session_id=? ",  # noqa: S608
                    "ORDER BY storage_path LIMIT 1",
                )
            ),
            (session_id,),
        ).fetchone()
        return None if row is None else self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> CatalogRow:
        return CatalogRow(
            storage_path=str(row[0]),
            session_id=str(row[1]),
            health=str(row[2]),
            created_utc=None if row[3] is None else str(row[3]),
            source=None if row[4] is None else str(row[4]),
            session_type=None if row[5] is None else str(row[5]),
            profile=None if row[6] is None else str(row[6]),
            label=None if row[7] is None else str(row[7]),
        )
