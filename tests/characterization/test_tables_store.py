from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import (
    ArtifactCorruptError,
    ArtifactInputs,
    ArtifactStore,
    CodeIdentity,
    NamedDigest,
)
from lnt.characterization import (
    CharacterizationBundle,
    CharacterizationError,
    TableBlock,
    encode_bundle,
    load_bundle,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def test_table_null_requires_parallel_reason_code(tables: Mapping[str, TableBlock]) -> None:
    table = tables["events"]
    with pytest.raises(CharacterizationError, match="table_null_reason"):
        dataclasses.replace(table, rows=((None, None),), row_count=1, stored_count=1)


def test_artifact_store_round_trip_and_tamper_detection(
    tmp_path: Path,
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    files = encode_bundle(bundle, arrays, tables, max_artifact_bytes=67_108_864)
    inputs = ArtifactInputs(
        recipe_sha256="a" * 64,
        raw_inputs=(NamedDigest(name="ch1.npy", digest="b" * 64),),
        context_dependencies=(),
        profile_dependencies=(),
        calibration_dependencies=(),
        code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
    )
    store = ArtifactStore(tmp_path)
    artifact = store.publish(inputs, files)
    loaded = load_bundle({name: (artifact / name).read_bytes() for name in files})
    assert loaded.bundle == bundle
    (artifact / "characterization.json").write_bytes(b"tampered")
    with pytest.raises(ArtifactCorruptError, match="повреждён"):
        store.find(inputs.artifact_key)
