from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, TypedDict, Unpack

import pytest

from lnt.analysis_store import (
    ArtifactCorruptError,
    ArtifactInputs,
    ArtifactStore,
    CodeIdentity,
    NamedDigest,
)

if TYPE_CHECKING:
    from pathlib import Path


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class _InputChanges(TypedDict, total=False):
    raw_inputs: tuple[NamedDigest, ...]
    context_dependencies: tuple[NamedDigest, ...]
    profile_dependencies: tuple[NamedDigest, ...]
    calibration_dependencies: tuple[NamedDigest, ...]
    code_identity: CodeIdentity


def _inputs(**changes: Unpack[_InputChanges]) -> ArtifactInputs:
    return ArtifactInputs(
        recipe_sha256=_digest(b"recipe"),
        raw_inputs=changes.get(
            "raw_inputs", (NamedDigest(name="ch1.npy", digest=_digest(b"raw")),)
        ),
        context_dependencies=changes.get("context_dependencies", ()),
        profile_dependencies=changes.get("profile_dependencies", ()),
        calibration_dependencies=changes.get("calibration_dependencies", ()),
        code_identity=changes.get(
            "code_identity",
            CodeIdentity(lnt="0.1.0", numpy="2.1.0", scipy="1.14.0"),
        ),
    )


def test_artifact_key_separates_recipe_from_declared_execution_identity() -> None:
    base = _inputs()
    raw_changed = _inputs(raw_inputs=(NamedDigest(name="ch1.npy", digest=_digest(b"other")),))
    context_changed = _inputs(
        context_dependencies=(NamedDigest(name="context.json", digest=_digest(b"context")),),
    )
    code_changed = _inputs(code_identity=CodeIdentity(lnt="0.1.1", numpy="2.1.0", scipy="1.14.0"))

    assert {base.recipe_sha256, raw_changed.recipe_sha256, context_changed.recipe_sha256} == {
        base.recipe_sha256,
    }
    assert (
        len(
            {
                base.artifact_key,
                raw_changed.artifact_key,
                context_changed.artifact_key,
                code_changed.artifact_key,
            }
        )
        == 4
    )


def test_undeclared_context_cannot_change_artifact_key() -> None:
    before = _inputs()
    after = _inputs()

    assert before.artifact_key == after.artifact_key


def test_publish_is_byte_stable_and_reuses_valid_artifact(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    inputs = _inputs()
    outputs = {"metrics.json": b'{"value":1}\n', "spectrum.csv": b"frequency_hz,psd\n"}

    first = store.publish(inputs, outputs)
    first_manifest = (first / "analysis-manifest.json").read_bytes()
    second = store.publish(inputs, dict(reversed(list(outputs.items()))))

    assert second == first
    assert (second / "analysis-manifest.json").read_bytes() == first_manifest
    manifest = json.loads(first_manifest)
    assert manifest["recipe_sha256"] == inputs.recipe_sha256
    assert manifest["artifact_key"] == inputs.artifact_key
    assert {item["name"] for item in manifest["outputs"]} == set(outputs)


def test_crash_during_publish_never_becomes_readable(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    inputs = _inputs()

    def crash(_partial: Path) -> None:
        raise RuntimeError("injected crash")

    with pytest.raises(RuntimeError, match="injected crash"):
        store.publish(inputs, {"metrics.json": b"{}\n"}, before_publish=crash)

    assert store.find(inputs.artifact_key) is None


def test_tampered_output_is_never_served_or_overwritten(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    inputs = _inputs()
    artifact = store.publish(inputs, {"metrics.json": b"{}\n"})
    (artifact / "metrics.json").write_bytes(b"tampered")

    with pytest.raises(ArtifactCorruptError):
        store.find(inputs.artifact_key)
    with pytest.raises(ArtifactCorruptError):
        store.publish(inputs, {"metrics.json": b"replacement\n"})
    assert (artifact / "metrics.json").read_bytes() == b"tampered"
