"""Canonical analysis-manifest.json construction and verification."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final

from lnt.analysis_store.errors import ArtifactCorruptError
from lnt.analysis_store.provenance import AnalysisProvenance
from lnt.context.json_codec import JsonValue, decode_object, encode_canonical
from lnt.errors import InputError
from lnt.safe_paths import ensure_safe_filename, ensure_within_root, is_linked_path

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.analysis_store.identity import ArtifactInputs, NamedDigest

MANIFEST_NAME: Final = "analysis-manifest.json"


def sha256_bytes(value: bytes) -> str:
    """Возвращает lowercase SHA-256 переданных байт."""
    return hashlib.sha256(value).hexdigest()


def build_manifest(inputs: ArtifactInputs, outputs: tuple[NamedDigest, ...]) -> bytes:
    """Строит byte-stable manifest для одной locked среды."""
    payload: dict[str, JsonValue] = {
        "schema_version": 1,
        "artifact_key": inputs.artifact_key,
        "recipe_sha256": inputs.recipe_sha256,
        "inputs": {
            "raw": _entries(inputs.raw_inputs),
            "context": _entries(inputs.context_dependencies),
            "profile": _entries(inputs.profile_dependencies),
            "calibration": _entries(inputs.calibration_dependencies),
            "code_identity": inputs.code_identity.identity_string,
        },
        "outputs": _entries(outputs),
        "provenance": AnalysisProvenance.current(inputs.code_identity).to_mapping(),
    }
    return encode_canonical(payload, "analysis-manifest") + b"\n"


def verify_artifact(
    path: Path, expected_key: str, *, expected_recipe_id: str | None = None
) -> frozenset[str]:
    """Проверяет identity и каждый перечисленный output digest."""
    manifest_path = path / MANIFEST_NAME
    if is_linked_path(path) or is_linked_path(manifest_path):
        raise ArtifactCorruptError(path, "linked_path")
    try:
        payload = decode_object(manifest_path.read_text(encoding="utf-8"), "analysis-manifest")
    except (InputError, OSError, UnicodeDecodeError) as error:
        raise ArtifactCorruptError(path, "manifest_unreadable") from error
    if payload.get("artifact_key") != expected_key:
        raise ArtifactCorruptError(path, "artifact_key_mismatch")
    if expected_recipe_id is not None and payload.get("recipe_sha256") != expected_recipe_id:
        raise ArtifactCorruptError(path, "recipe_id_mismatch")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        raise ArtifactCorruptError(path, "outputs_invalid")
    names: set[str] = set()
    for item in outputs:
        name, digest = _output_entry(path, item)
        if name in names:
            raise ArtifactCorruptError(path, "output_path_invalid")
        actual = _verified_output_digest(path, name)
        if actual != digest:
            raise ArtifactCorruptError(path, "output_digest_mismatch")
        names.add(name)
    return frozenset(names)


def _output_entry(path: Path, item: object) -> tuple[str, str]:
    if not isinstance(item, dict):
        raise ArtifactCorruptError(path, "output_entry_invalid")
    name = item.get("name")
    digest = item.get("digest")
    if not isinstance(name, str) or not isinstance(digest, str):
        raise ArtifactCorruptError(path, "output_entry_invalid")
    return name, digest


def _verified_output_digest(path: Path, name: str) -> str:
    try:
        ensure_safe_filename(name, label="имя output")
    except InputError as error:
        raise ArtifactCorruptError(path, "output_path_invalid") from error
    output_path = path / name
    if is_linked_path(output_path):
        raise ArtifactCorruptError(path, "output_path_invalid")
    try:
        checked_output = ensure_within_root(path, output_path)
        content = checked_output.read_bytes()
    except (InputError, OSError) as error:
        raise ArtifactCorruptError(path, "output_unreadable") from error
    if checked_output.parent != path.resolve(strict=True) or not checked_output.is_file():
        raise ArtifactCorruptError(path, "output_unreadable")
    return sha256_bytes(content)


def _entries(values: tuple[NamedDigest, ...]) -> list[JsonValue]:
    return [{"name": value.name, "digest": value.digest} for value in sorted(values)]
