from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.characterization import (
    ARRAYS_FILENAME,
    METADATA_FILENAME,
    TABLES_FILENAME,
    CharacterizationBundle,
    CharacterizationError,
    TableBlock,
    encode_bundle,
    load_bundle,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def test_bundle_round_trip_is_deterministic(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    first = encode_bundle(bundle, arrays, tables, max_artifact_bytes=67_108_864)
    second = encode_bundle(
        bundle, dict(reversed(tuple(arrays.items()))), tables, max_artifact_bytes=67_108_864
    )

    assert first == second
    assert tuple(first) == (METADATA_FILENAME, ARRAYS_FILENAME, TABLES_FILENAME)
    loaded = load_bundle(first)
    assert loaded.bundle == bundle
    assert tuple(loaded.arrays) == tuple(sorted(arrays))
    assert loaded.tables == tables


def test_npz_has_sorted_pinned_members(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    files = encode_bundle(bundle, arrays, tables, max_artifact_bytes=67_108_864)
    with zipfile.ZipFile(io.BytesIO(files[ARRAYS_FILENAME])) as archive:
        infos = archive.infolist()
    assert [info.filename for info in infos] == [f"{name}.npy" for name in sorted(arrays)]
    assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
    assert all(info.create_system == 0 for info in infos)


@pytest.mark.parametrize(
    "bad",
    [
        np.array([object()], dtype=object),
        np.array(["value"]),
        np.array([np.inf]),
    ],
)
def test_non_numeric_or_nonfinite_array_is_rejected(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
    bad: np.ndarray,
) -> None:
    changed = dict(arrays)
    changed["event_waveform_v"] = bad
    with pytest.raises(CharacterizationError, match=r"array_(dtype|finite|shape)"):
        encode_bundle(bundle, changed, tables, max_artifact_bytes=67_108_864)


def test_malformed_mask_and_offsets_are_rejected(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    bad_mask = dict(arrays)
    bad_mask["event_waveform_valid"] = np.array([1, 2, 1, 1], dtype=np.uint8)
    with pytest.raises(CharacterizationError, match="array_mask"):
        encode_bundle(bundle, bad_mask, tables, max_artifact_bytes=67_108_864)
    bad_offsets = dict(arrays)
    bad_offsets["event_waveform_offsets"] = np.array([0, 4, 3], dtype=np.int64)
    with pytest.raises(CharacterizationError, match="array_offsets"):
        encode_bundle(bundle, bad_offsets, tables, max_artifact_bytes=67_108_864)


def test_missing_extra_and_unreferenced_outputs_are_rejected(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    with pytest.raises(CharacterizationError, match="array_references"):
        encode_bundle(bundle, {}, tables, max_artifact_bytes=67_108_864)
    with pytest.raises(CharacterizationError, match="array_references"):
        encode_bundle(
            bundle,
            {**arrays, "unreferenced": np.array([1], dtype=np.int64)},
            tables,
            max_artifact_bytes=67_108_864,
        )
    with pytest.raises(CharacterizationError, match="table_references"):
        encode_bundle(bundle, arrays, {}, max_artifact_bytes=67_108_864)


def test_loader_rejects_unknown_duplicate_and_noncanonical_json(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    files = encode_bundle(bundle, arrays, tables, max_artifact_bytes=67_108_864)
    metadata = json.loads(files[METADATA_FILENAME])
    metadata["unknown"] = True
    changed = dict(files)
    changed[METADATA_FILENAME] = json.dumps(metadata, separators=(",", ":")).encode()
    with pytest.raises(CharacterizationError):
        load_bundle(changed)
    changed[METADATA_FILENAME] = b'{"schema_version":1,"schema_version":1,"families":[]}'
    with pytest.raises(CharacterizationError):
        load_bundle(changed)
    changed[METADATA_FILENAME] = files[METADATA_FILENAME] + b"\n"
    with pytest.raises(CharacterizationError, match="canonical_json"):
        load_bundle(changed)


def test_loader_rejects_missing_metadata_field_and_unpinned_npz(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    files = encode_bundle(bundle, arrays, tables, max_artifact_bytes=67_108_864)
    metadata = json.loads(files[METADATA_FILENAME])
    del metadata["families"][0]["method"]
    changed = dict(files)
    changed[METADATA_FILENAME] = json.dumps(
        metadata, sort_keys=True, separators=(",", ":")
    ).encode()
    with pytest.raises(CharacterizationError, match="json_fields"):
        load_bundle(changed)

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        for name, value in sorted(arrays.items()):
            payload = io.BytesIO()
            np.lib.format.write_array(payload, value, allow_pickle=False)
            archive.writestr(f"{name}.npy", payload.getvalue())
    changed = dict(files)
    changed[ARRAYS_FILENAME] = archive_bytes.getvalue()
    with pytest.raises(CharacterizationError, match="array_members"):
        load_bundle(changed)


def test_individual_and_total_limits_fail_with_typed_reason(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    with pytest.raises(CharacterizationError) as caught:
        encode_bundle(bundle, arrays, tables, max_artifact_bytes=100)
    assert caught.value.reason_code == "artifact_limit"
    with pytest.raises(CharacterizationError, match="artifact_limit"):
        encode_bundle(bundle, arrays, tables, max_artifact_bytes=67_108_865)

    files = encode_bundle(bundle, arrays, tables, max_artifact_bytes=67_108_864)
    oversized = dict(files)
    oversized[METADATA_FILENAME] = b"x" * (2 * 1024 * 1024 + 1)
    with pytest.raises(CharacterizationError, match="artifact_limit"):
        load_bundle(oversized)
