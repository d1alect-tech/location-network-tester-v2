"""Best-effort projection of canonical sessions into disposable indexes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import warnings
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from lnt.catalog.connection import catalog_path, writer_transaction
from lnt.catalog.migrations import apply_migrations
from lnt.catalog.models import ArtifactRecipe, SessionProjection
from lnt.catalog.reconcile import reconcile_catalog
from lnt.catalog.repositories import CatalogRepositories
from lnt.context.model import (
    CollectionStatus,
    ContextField,
    ContextSnapshot,
    FieldKind,
    FieldSource,
)
from lnt.context.store import ContextStore, ContextUpdate
from lnt.errors import InputError
from lnt.manifest import manifest_from_json

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.metadata_collector import MetadataField, MetadataSnapshot

RECONCILE_MARKER: Final = ".reconcile-needed"
LEGACY_ARTIFACT_KEY: Final = "legacy-default"
LEGACY_RECIPE_SHA256: Final = hashlib.sha256(b"lnt:legacy-default-analysis:v2").hexdigest()

__all__ = [
    "CatalogProjectionWarning",
    "index_session",
    "project_analysis_artifact",
    "project_analysis_safely",
    "reconcile_catalog",
    "session_id_from_manifest",
    "write_initial_context",
]


class CatalogProjectionWarning(UserWarning):
    """A canonical write succeeded but its disposable catalog projection failed."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectionFailure:
    """Machine-readable projection failure persisted in a recovery marker."""

    operation: str
    reason: str


def write_initial_context(
    session_dir: Path,
    session_id: str,
    metadata: MetadataSnapshot,
    *,
    label: str | None,
    tags: tuple[str, ...] = (),
) -> None:
    """Write the initial context event inside an unpublished session directory."""
    fields = {
        key: _context_field(field, metadata.captured_at) for key, field in metadata.fields.items()
    }
    if label is not None:
        fields["session.label"] = ContextField(
            kind=FieldKind.STRING,
            value=label,
            unit=None,
            uncertainty=None,
            source=FieldSource.USER,
            collection_status=CollectionStatus.COLLECTED,
            collection_reason=None,
            captured_at=metadata.captured_at,
        )
    snapshot = ContextSnapshot(
        schema_version=1,
        session_id=session_id,
        revision=1,
        fields=fields,
        tags=tags,
        notes=None,
        profile_snapshots=(),
    )
    ContextStore(session_dir, session_id).update(
        ContextUpdate(
            expected_revision=0,
            snapshot=snapshot,
            actor="lnt.capture",
            changed_keys=tuple(sorted(fields)),
            occurred_at=metadata.captured_at,
            event_id=f"initial-{session_id}",
        ),
    )


def index_session(session_dir: Path) -> None:
    """Reconcile only after publication; isolate all expected catalog failures."""
    try:
        reconcile_catalog(session_dir.parent, catalog_path())
        (session_dir / RECONCILE_MARKER).unlink(missing_ok=True)
    except (InputError, OSError, sqlite3.Error) as error:
        _mark_failure(session_dir, ProjectionFailure(operation="session", reason=str(error)))


def project_analysis_artifact(session_dir: Path, session_id: str) -> None:
    """Project the selected root legacy outputs as the default artifact recipe."""
    database = catalog_path()
    reconcile_catalog(session_dir.parent, database)
    apply_migrations(database)
    with writer_transaction(database) as connection:
        row = connection.execute(
            """SELECT session_id, storage_path, path_fingerprint, health, manifest_schema,
            created_utc, source, session_type, profile, sample_rate_hz, duration_s,
            sample_count, label, channels FROM catalog_sessions WHERE storage_path = ?""",
            (str(session_dir.resolve()),),
        ).fetchone()
        if row is None:
            raise InputError(f"каталог не содержит опубликованную сессию {session_id}")
        repositories = CatalogRepositories(connection)
        repositories.sessions.upsert(
            SessionProjection(
                id=str(row[0]),
                storage_path=str(row[1]),
                path_fingerprint=str(row[2]),
                health=str(row[3]),
                manifest_schema=row[4],
                created_utc=row[5],
                source=row[6],
                session_type=row[7],
                profile=row[8],
                sample_rate_hz=row[9],
                duration_s=row[10],
                sample_count=row[11],
                label=row[12],
                channels=row[13],
            ),
        )
        repositories.artifacts.upsert(
            ArtifactRecipe(
                recipe_sha256=LEGACY_RECIPE_SHA256,
                session_id=session_id,
                artifact_key=LEGACY_ARTIFACT_KEY,
                storage_ref=str(session_dir.resolve()),
            ),
        )


def project_analysis_safely(session_dir: Path, session_id: str) -> None:
    """Keep completed legacy analysis usable when its catalog is unavailable."""
    try:
        project_analysis_artifact(session_dir, session_id)
        (session_dir / RECONCILE_MARKER).unlink(missing_ok=True)
    except (InputError, OSError, sqlite3.Error) as error:
        _mark_failure(session_dir, ProjectionFailure(operation="analysis", reason=str(error)))


def session_id_from_manifest(session_dir: Path) -> str:
    """Read a published session identity for projection tests and adapters."""
    return manifest_from_json(
        (session_dir / "manifest.json").read_text(encoding="utf-8")
    ).session_id


def _context_field(field: MetadataField, captured_at: str) -> ContextField:
    value = field.value
    status = CollectionStatus.COLLECTED
    reason = field.reason_code
    if value is None:
        value = ""
        status = CollectionStatus.UNAVAILABLE
    if isinstance(value, bool):
        kind = FieldKind.BOOLEAN
        normalized: str | float | bool = value
    elif isinstance(value, (int, float)):
        kind = FieldKind.NUMBER
        normalized = float(value)
    elif isinstance(value, tuple):
        kind = FieldKind.STRING
        normalized = json.dumps(value, separators=(",", ":"))
    else:
        kind = FieldKind.STRING
        normalized = value
    return ContextField(
        kind=kind,
        value=normalized,
        unit=None,
        uncertainty=None,
        source=FieldSource.AUTOMATIC,
        collection_status=status,
        collection_reason=reason,
        captured_at=captured_at,
    )


def _mark_failure(session_dir: Path, failure: ProjectionFailure) -> None:
    payload = json.dumps(
        {"schema_version": 1, "operation": failure.operation, "reason": failure.reason},
        ensure_ascii=False,
        sort_keys=True,
    )
    with suppress(OSError):
        (session_dir / RECONCILE_MARKER).write_text(payload + "\n", encoding="utf-8")
    warnings.warn(
        f"catalog projection deferred for {session_dir.name}: {failure.reason}",
        CatalogProjectionWarning,
        stacklevel=2,
    )
