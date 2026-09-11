from __future__ import annotations

import dataclasses
import io
import zipfile
from typing import TYPE_CHECKING, NoReturn

import numpy as np
import pytest

from lnt.characterization import (
    ARRAYS_FILENAME,
    CharacterizationError,
    TableBlock,
    TableColumn,
    TableValueType,
    encode_bundle,
    load_bundle,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.characterization import CharacterizationBundle


MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def _with_table_only_partial(bundle: CharacterizationBundle) -> CharacterizationBundle:
    family = dataclasses.replace(bundle.families[1], array_refs=())
    return dataclasses.replace(
        bundle,
        families=(bundle.families[0], family, *bundle.families[2:]),
    )


def _with_array_size(bundle: CharacterizationBundle, size: int) -> CharacterizationBundle:
    family = bundle.families[1]
    reference = dataclasses.replace(family.array_refs[0], shape=(size,), offsets_id=None)
    return dataclasses.replace(
        bundle,
        families=(
            bundle.families[0],
            dataclasses.replace(family, array_refs=(reference,)),
            *bundle.families[2:],
        ),
    )


def _replace_array_member(data: bytes, name: str, payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, "w") as target:
        for info in source.infolist():
            target.writestr(info, payload if info.filename == name else source.read(info))
    return output.getvalue()


def test_descending_unsigned_offsets_are_rejected(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    changed = dict(arrays)
    changed["event_waveform_offsets"] = np.array([0, 3, 2, 4], dtype=np.uint64)

    with pytest.raises(CharacterizationError) as caught:
        encode_bundle(bundle, changed, tables, max_artifact_bytes=MAX_ARTIFACT_BYTES)

    assert caught.value.reason_code == "array_offsets"


def test_repeated_unsigned_offsets_round_trip(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    changed = dict(arrays)
    offsets = np.array([0, 2, 2, 4], dtype=np.uint64)
    changed["event_waveform_offsets"] = offsets

    loaded = load_bundle(
        encode_bundle(bundle, changed, tables, max_artifact_bytes=MAX_ARTIFACT_BYTES)
    )

    assert np.array_equal(loaded.arrays["event_waveform_offsets"], offsets)


def test_reason_code_cells_do_not_count_as_partial_output(
    bundle: CharacterizationBundle,
    tables: Mapping[str, TableBlock],
) -> None:
    changed_tables = {
        "events": dataclasses.replace(
            tables["events"], rows=((None, "clipped"),), row_count=1, stored_count=1
        )
    }

    with pytest.raises(CharacterizationError) as caught:
        encode_bundle(
            _with_table_only_partial(bundle),
            {},
            changed_tables,
            max_artifact_bytes=MAX_ARTIFACT_BYTES,
        )

    assert caught.value.reason_code == "status_invariant"


def test_text_cells_count_as_partial_output(bundle: CharacterizationBundle) -> None:
    table = TableBlock(
        table_id="events",
        columns=(TableColumn(name="category", unit=None, type=TableValueType.TEXT),),
        rows=(("clipped",),),
        row_count=1,
        stored_count=1,
        selection_rule="all",
    )

    files = encode_bundle(
        _with_table_only_partial(bundle),
        {},
        {"events": table},
        max_artifact_bytes=MAX_ARTIFACT_BYTES,
    )

    assert load_bundle(files).tables["events"] == table


def test_encode_enforces_expanded_npy_budget_including_headers(
    bundle: CharacterizationBundle,
    tables: Mapping[str, TableBlock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    size = 400
    changed_bundle = _with_array_size(bundle, size)
    changed_arrays = {
        "event_waveform_v": np.zeros(size, dtype=np.float64),
        "event_waveform_valid": np.ones(size, dtype=np.uint8),
    }
    monkeypatch.setattr("lnt.characterization.bundle_codec.MAX_ARRAYS_BYTES", 4096)
    files = encode_bundle(
        changed_bundle, changed_arrays, tables, max_artifact_bytes=MAX_ARTIFACT_BYTES
    )
    with zipfile.ZipFile(io.BytesIO(files[ARRAYS_FILENAME])) as archive:
        expanded_size = sum(info.file_size for info in archive.infolist())
    assert expanded_size > sum(array.nbytes for array in changed_arrays.values())
    assert load_bundle(files).bundle == changed_bundle

    monkeypatch.setattr("lnt.characterization.bundle_codec.MAX_ARRAYS_BYTES", expanded_size - 1)
    with pytest.raises(CharacterizationError) as caught:
        encode_bundle(changed_bundle, changed_arrays, tables, max_artifact_bytes=MAX_ARTIFACT_BYTES)

    assert caught.value.reason_code == "artifact_limit"


def test_loader_rejects_npy_shape_larger_than_member_before_allocation(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = encode_bundle(bundle, arrays, tables, max_artifact_bytes=MAX_ARTIFACT_BYTES)
    forged = io.BytesIO()
    np.lib.format.write_array_header_1_0(
        forged,
        {"descr": "<i8", "fortran_order": False, "shape": (10_000_000_000,)},
    )
    changed = dict(files)
    changed[ARRAYS_FILENAME] = _replace_array_member(
        files[ARRAYS_FILENAME], "event_waveform_offsets.npy", forged.getvalue()
    )

    def fail_allocation(shape: object, dtype: object = None) -> NoReturn:
        raise AssertionError(f"forged shape reached ndarray allocation: {shape!r}, {dtype!r}")

    monkeypatch.setattr("lnt.characterization.array_codec.np.ndarray", fail_allocation)
    with pytest.raises(CharacterizationError) as caught:
        load_bundle(changed)

    assert caught.value.reason_code == "artifact_limit"
