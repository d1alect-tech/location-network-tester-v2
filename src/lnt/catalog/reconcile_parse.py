"""Разбор manifest/context/analysis без чтения raw-массивов."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from lnt.catalog.reconcile_models import CatalogSession, ScannedDirectory, SessionHealth
from lnt.context.store import ContextStore
from lnt.errors import InputError
from lnt.manifest import manifest_from_json

if TYPE_CHECKING:
    from lnt.types import SessionManifest


def _safe_filename(filename: str) -> bool:
    path = Path(filename)
    return path.name == filename and not path.is_absolute() and os.sep not in filename


def _manifest_health(directory: Path, manifest: SessionManifest) -> SessionHealth:
    filenames = [manifest.ch1.filename]
    if manifest.ch2 is not None:
        filenames.append(manifest.ch2.filename)
    if not all(_safe_filename(filename) for filename in filenames):
        return "corrupt_manifest"
    if not all((directory / filename).is_file() for filename in filenames):
        return "missing_files"
    return "ok"


def _context_projection(
    directory: Path,
    session_id: str,
) -> tuple[SessionHealth, tuple[tuple[str, str], ...], tuple[str, ...]]:
    try:
        view = ContextStore(directory, session_id).load()
    except (InputError, OSError, UnicodeError):
        return "context_invalid", (), ()
    if view.health == "context_invalid":
        return "context_invalid", (), ()
    if view.snapshot is None:
        return "ok", (), ()
    fields = tuple(
        (key, json.dumps(field.value, ensure_ascii=False, sort_keys=True))
        for key, field in sorted(view.snapshot.fields.items())
    )
    return "ok", fields, view.snapshot.tags


def _analysis_health(directory: Path, session_id: str) -> SessionHealth:
    path = directory / "metrics.json"
    if not path.exists():
        return "ok"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError, OSError):
        return "analysis_invalid"
    if not isinstance(payload, dict):
        return "analysis_invalid"
    if payload.get("session_id") != session_id or not isinstance(
        payload.get("schema_version"), int
    ):
        return "analysis_invalid"
    return "ok"


def _label(manifest: SessionManifest) -> str | None:
    value = manifest.parameters.get("label")
    return value if isinstance(value, str) else None


def parse_directory(scanned: ScannedDirectory) -> CatalogSession:
    """Строит видимую проекцию, классифицируя ожидаемые повреждения."""
    storage_path = str(scanned.path)
    if scanned.reparse_point or ".partial-" in scanned.path.name:
        health: SessionHealth = (
            "partial" if ".partial-" in scanned.path.name else "corrupt_manifest"
        )
        return CatalogSession(
            storage_path=storage_path,
            session_id=scanned.path.name,
            path_fingerprint=scanned.fingerprint,
            health=health,
        )
    if any(".partial-" in entry.name for entry in scanned.path.iterdir()):
        return CatalogSession(
            storage_path=storage_path,
            session_id=scanned.path.name,
            path_fingerprint=scanned.fingerprint,
            health="partial",
        )
    if scanned.manifest_text is None:
        return CatalogSession(
            storage_path=storage_path,
            session_id=scanned.path.name,
            path_fingerprint=scanned.fingerprint,
            health="corrupt_manifest",
        )
    try:
        manifest = manifest_from_json(scanned.manifest_text)
    except (InputError, OSError, UnicodeError):
        return CatalogSession(
            storage_path=storage_path,
            session_id=scanned.path.name,
            path_fingerprint=scanned.fingerprint,
            health="corrupt_manifest",
        )
    health = _manifest_health(scanned.path, manifest)
    if health != "ok":
        return CatalogSession(
            storage_path=storage_path,
            session_id=manifest.session_id,
            path_fingerprint=scanned.fingerprint,
            health=health,
            manifest_schema=manifest.schema_version,
            created_utc=manifest.created_utc,
            source=manifest.source.value,
            session_type=manifest.session_type.value,
            profile=manifest.profile,
            sample_rate_hz=manifest.sample_rate_hz,
            duration_s=manifest.duration_s,
            sample_count=manifest.sample_count,
            label=_label(manifest),
            channels="dual" if manifest.ch2 is not None else "single",
        )
    context_health, fields, tags = _context_projection(scanned.path, manifest.session_id)
    analysis_health = _analysis_health(scanned.path, manifest.session_id)
    if health == "ok" and context_health != "ok":
        health = context_health
    if health == "ok" and analysis_health != "ok":
        health = analysis_health
    return CatalogSession(
        storage_path=storage_path,
        session_id=manifest.session_id,
        path_fingerprint=scanned.fingerprint,
        health=health,
        manifest_schema=manifest.schema_version,
        created_utc=manifest.created_utc,
        source=manifest.source.value,
        session_type=manifest.session_type.value,
        profile=manifest.profile,
        sample_rate_hz=manifest.sample_rate_hz,
        duration_s=manifest.duration_s,
        sample_count=manifest.sample_count,
        label=_label(manifest),
        channels="dual" if manifest.ch2 is not None else "single",
        context_fields=fields,
        context_tags=tags,
    )
