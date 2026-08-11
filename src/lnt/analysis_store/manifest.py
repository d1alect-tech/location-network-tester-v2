"""Canonical analysis-manifest.json construction and verification."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final

from lnt.analysis_store.errors import ArtifactCorruptError
from lnt.analysis_store.provenance import AnalysisProvenance
from lnt.context.json_codec import JsonValue, decode_object, encode_canonical
from lnt.errors import InputError

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


def verify_artifact(path: Path, expected_key: str) -> None:
    """Проверяет identity и каждый перечисленный output digest."""
    manifest_path = path / MANIFEST_NAME
    try:
        payload = decode_object(manifest_path.read_text(encoding="utf-8"), "analysis-manifest")
    except (InputError, OSError, UnicodeDecodeError) as error:
        raise ArtifactCorruptError(path, "manifest_unreadable") from error
    if payload.get("artifact_key") != expected_key:
        raise ArtifactCorruptError(path, "artifact_key_mismatch")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        raise ArtifactCorruptError(path, "outputs_invalid")
    for item in outputs:
        if not isinstance(item, dict):
            raise ArtifactCorruptError(path, "output_entry_invalid")
        name = item.get("name")
        digest = item.get("digest")
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ArtifactCorruptError(path, "output_entry_invalid")
        output_path = path / name
        try:
            actual = sha256_bytes(output_path.read_bytes())
        except OSError as error:
            raise ArtifactCorruptError(path, "output_unreadable") from error
        if actual != digest:
            raise ArtifactCorruptError(path, "output_digest_mismatch")


def _entries(values: tuple[NamedDigest, ...]) -> list[JsonValue]:
    return [{"name": value.name, "digest": value.digest} for value in sorted(values)]
