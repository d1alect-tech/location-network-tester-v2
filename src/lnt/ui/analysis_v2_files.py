"""Validated filesystem boundary for analysis-v2 HTTP routes."""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Final

from fastapi import HTTPException, status

from lnt.analysis_store import ArtifactCorruptError, ArtifactStore
from lnt.analysis_store.identity import SHA256_LENGTH
from lnt.analysis_store.manifest import verify_artifact
from lnt.errors import InputError
from lnt.safe_paths import ensure_safe_filename, is_linked_path
from lnt.ui.dependencies import AppServices, http_unprocessable, resolve_session_or_404

if TYPE_CHECKING:
    from pathlib import Path

_POINTER_NAME = ".lnt-default-analysis.json"
_JOB_ID_LENGTH: Final = 32


def validate_sha256(value: str, *, label: str) -> str:
    """Require one canonical lowercase SHA-256 identity."""
    if len(value) != SHA256_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise http_unprocessable(f"{label} должен быть lowercase SHA-256")
    return value


def validate_job_id(value: str) -> str:
    """Require one canonical lowercase UUID hex identity."""
    if len(value) != _JOB_ID_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise http_unprocessable("job_id должен быть lowercase UUID hex")
    return value


def validate_session_inputs(
    session_dir: Path, channels: tuple[str, ...], *, make_default: bool
) -> None:
    """Reject linked manifest and channel inputs before an analysis job exists."""
    inputs = (
        session_dir / "manifest.json",
        session_dir / "analyses",
        *(session_dir / f"{name}.npy" for name in channels),
    )
    if make_default:
        inputs = (*inputs, session_dir / _POINTER_NAME)
    for path in inputs:
        if is_linked_path(path):
            raise http_unprocessable(f"вход анализа не должен быть ссылкой: {path.name}")


def verified_artifact(services: AppServices, session_name: str, artifact_key: str) -> Path:
    """Resolve a session and return one integrity-checked artifact directory."""
    validate_sha256(artifact_key, label="artifact_key")
    session_dir = resolve_session_or_404(services.root, session_name)
    store = ArtifactStore(session_dir)
    try:
        artifact = store.find(artifact_key)
    except (ArtifactCorruptError, InputError) as error:
        store.invalidate(artifact_key)
        raise HTTPException(status.HTTP_409_CONFLICT, "artifact повреждён") from error
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact не найден")
    return artifact


def verified_output(
    services: AppServices, session_name: str, artifact_key: str, filename: str
) -> Path:
    """Return a manifest-listed output after complete artifact verification."""
    artifact = verified_artifact(services, session_name, artifact_key)
    try:
        ensure_safe_filename(filename, label="имя файла артефакта")
    except InputError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "файл artifact не найден") from error
    outputs = verify_artifact(artifact, artifact_key)
    if filename not in outputs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "файл artifact не найден")
    return artifact / filename


def read_default_pointer(services: AppServices, session_name: str) -> dict[str, str]:
    """Read a pointer only when it names a verified artifact in the resolved session."""
    session_dir = resolve_session_or_404(services.root, session_name)
    pointer_path = session_dir / _POINTER_NAME
    if is_linked_path(pointer_path):
        raise HTTPException(status.HTTP_409_CONFLICT, "указатель анализа повреждён")
    try:
        payload = _pointer_object(pointer_path)
        recipe_id = validate_sha256(str(payload["recipe_id"]), label="recipe_id")
        artifact_key = validate_sha256(str(payload["artifact_key"]), label="artifact_key")
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "указатель анализа не найден") from error
    except (HTTPException, KeyError, OSError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "указатель анализа повреждён") from error
    artifact = verified_artifact(services, session_name, artifact_key)
    try:
        verify_artifact(artifact, artifact_key, expected_recipe_id=recipe_id)
    except ArtifactCorruptError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "указатель анализа повреждён") from error
    return {"recipe_id": recipe_id, "artifact_key": artifact_key}


def _pointer_object(path: Path) -> dict[object, object]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError
    return payload


def write_default_pointer(session_dir: Path, recipe_id: str, artifact_key: str) -> None:
    """Atomically publish a validated default-analysis pointer."""
    verify_artifact(
        session_dir / "analyses" / artifact_key,
        artifact_key,
        expected_recipe_id=recipe_id,
    )
    path = session_dir / _POINTER_NAME
    if is_linked_path(path):
        raise OSError("указатель анализа не должен быть ссылкой")
    temporary = path.with_name(f".{path.name}.partial-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {"recipe_id": recipe_id, "artifact_key": artifact_key}, stream, sort_keys=True
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)  # noqa: PTH105 - explicit atomic seam
    finally:
        temporary.unlink(missing_ok=True)
