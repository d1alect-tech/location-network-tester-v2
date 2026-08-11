"""Атомарная инкрементальная сверка disposable-каталога с диском."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from lnt.catalog.connection import open_catalog_reader, writer_transaction
from lnt.catalog.migrations import apply_migrations
from lnt.catalog.reconcile_models import CatalogStatus, ReconcileResult, VerifyResult
from lnt.catalog.reconcile_parse import parse_directory
from lnt.catalog.reconcile_repository import ReconcileRepository
from lnt.catalog.reconcile_scan import scan_immediate_directories

if TYPE_CHECKING:
    from pathlib import Path

_LAST_RUN_QUERY = """SELECT root_path, completed_utc, scanned, changed, deleted
FROM reconcile_runs WHERE id=1"""


def reconcile_catalog(root: Path, database: Path, *, rebuild: bool = False) -> ReconcileResult:
    """Сверяет immediate child directories в одной writer-транзакции."""
    apply_migrations(database)
    scanned = scan_immediate_directories(root)
    scanned_by_path = {str(item.path): item for item in scanned}
    with writer_transaction(database) as connection:
        repository = ReconcileRepository(connection)
        previous = repository.fingerprints()
        if rebuild:
            connection.execute("DELETE FROM catalog_sessions")
            previous = {}
        deleted_paths = tuple(sorted(set(previous) - set(scanned_by_path)))
        repository.delete_paths(deleted_paths)
        inserted = 0
        updated = 0
        skipped = 0
        projections = []
        changed_existing_paths = []
        for storage_path, item in scanned_by_path.items():
            if previous.get(storage_path) == item.fingerprint:
                skipped += 1
                continue
            projections.append(parse_directory(item))
            if storage_path in previous:
                updated += 1
                changed_existing_paths.append(storage_path)
            else:
                inserted += 1
        repository.upsert_many(tuple(projections), tuple(changed_existing_paths))
        repository.mark_duplicates()
        changed = inserted + updated
        connection.execute(
            """INSERT INTO reconcile_runs(id, root_path, completed_utc, scanned, changed, deleted)
            VALUES (1, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
            root_path=excluded.root_path, completed_utc=excluded.completed_utc,
            scanned=excluded.scanned, changed=excluded.changed, deleted=excluded.deleted""",
            (
                str(root.resolve(strict=False)),
                datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                len(scanned),
                changed,
                len(deleted_paths),
            ),
        )
    return ReconcileResult(
        scanned=len(scanned),
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        deleted=len(deleted_paths),
    )


def verify_catalog(root: Path, database: Path) -> VerifyResult:
    """Сравнивает текущие fingerprints и строки без записи."""
    scanned = scan_immediate_directories(root)
    actual = {str(item.path): item.fingerprint for item in scanned}
    with open_catalog_reader(database) as connection:
        expected = ReconcileRepository(connection).fingerprints()
    paths = set(actual) | set(expected)
    drift = tuple(sorted(path for path in paths if actual.get(path) != expected.get(path)))
    return VerifyResult(drift_paths=drift)


def catalog_status(database: Path) -> CatalogStatus:
    """Возвращает counts по health и метаданные последней сверки."""
    with open_catalog_reader(database) as connection:
        health = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT health, COUNT(*) FROM catalog_sessions GROUP BY health ORDER BY health",
            )
        }
        row = connection.execute(_LAST_RUN_QUERY).fetchone()
    last = None
    if row is not None:
        last = {
            "root_path": str(row[0]),
            "completed_utc": str(row[1]),
            "scanned": int(row[2]),
            "changed": int(row[3]),
            "deleted": int(row[4]),
        }
    return CatalogStatus(health=health, last_reconcile=last)
