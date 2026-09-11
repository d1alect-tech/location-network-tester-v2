"""Bounded three-file characterization bundle codec."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from lnt.characterization.array_codec import (
    NumericArray,
    decode_arrays,
    encode_arrays,
    validate_array_relations,
)
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.metadata_codec import decode_metadata, encode_metadata
from lnt.characterization.table_codec import decode_tables, encode_tables

if TYPE_CHECKING:
    from collections.abc import Mapping

    import numpy as np

    from lnt.characterization.models import CharacterizationBundle, FamilyResult
    from lnt.characterization.tables import TableBlock

METADATA_FILENAME: Final = "characterization.json"
ARRAYS_FILENAME: Final = "characterization-arrays.npz"
TABLES_FILENAME: Final = "characterization-tables.json"
OUTPUT_FILENAMES: Final = (METADATA_FILENAME, ARRAYS_FILENAME, TABLES_FILENAME)
HARD_MAX_ARTIFACT_BYTES: Final = 64 * 1024 * 1024
MAX_METADATA_BYTES: Final = 2 * 1024 * 1024
MAX_TABLES_BYTES: Final = 14 * 1024 * 1024
MAX_ARRAYS_BYTES: Final = 48 * 1024 * 1024


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadedCharacterization:
    """Validated loaded bundle and its typed external outputs."""

    bundle: CharacterizationBundle
    arrays: Mapping[str, NumericArray]
    tables: Mapping[str, TableBlock]


def encode_bundle(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
    *,
    max_artifact_bytes: int,
) -> dict[str, bytes]:
    """Validate and encode the exact bounded artifact files."""
    _validate_references(bundle, arrays, tables)
    files = {
        METADATA_FILENAME: encode_metadata(bundle),
        ARRAYS_FILENAME: encode_arrays(arrays),
        TABLES_FILENAME: encode_tables(tables),
    }
    _validate_limits(files, max_artifact_bytes)
    return files


def load_bundle(files: Mapping[str, bytes]) -> LoadedCharacterization:
    """Load exact files and fail closed on every malformed relation."""
    if set(files) != set(OUTPUT_FILENAMES):
        raise CharacterizationError("bundle_files", "exactly three artifact files are required")
    _validate_limits(files, HARD_MAX_ARTIFACT_BYTES)
    bundle = decode_metadata(files[METADATA_FILENAME])
    arrays = decode_arrays(files[ARRAYS_FILENAME], maximum_uncompressed_bytes=MAX_ARRAYS_BYTES)
    tables = decode_tables(files[TABLES_FILENAME])
    _validate_references(bundle, arrays, tables)
    return LoadedCharacterization(
        bundle=bundle,
        arrays=MappingProxyType(arrays),
        tables=MappingProxyType(tables),
    )


def _validate_references(
    bundle: CharacterizationBundle,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> None:
    values: dict[str, tuple[str, tuple[int, ...], str | None, str | None]] = {}
    table_ids: list[str] = []
    for family in bundle.families:
        for reference in family.array_refs:
            if reference.array_id in values:
                raise CharacterizationError("array_references", "duplicate array reference")
            values[reference.array_id] = (
                reference.dtype,
                reference.shape,
                reference.validity_mask_id,
                reference.offsets_id,
            )
        table_ids.extend(reference.table_id for reference in family.table_refs)
    validate_array_relations(arrays, values=values)
    if len(table_ids) != len(set(table_ids)) or set(table_ids) != set(tables):
        raise CharacterizationError("table_references", "table references do not resolve exactly")
    if any(table_id != table.table_id for table_id, table in tables.items()):
        raise CharacterizationError("table_references", "table mapping key does not match table id")
    for family in bundle.families:
        if family.status.value != "unavailable" and not _has_valid_output(family, arrays, tables):
            raise CharacterizationError(
                "status_invariant", f"{family.family_id} has no valid output"
            )


def _has_valid_output(
    family: FamilyResult,
    arrays: Mapping[str, np.ndarray],
    tables: Mapping[str, TableBlock],
) -> bool:
    if family.comparison_summary:
        return True
    for reference in family.array_refs:
        array = arrays[reference.array_id]
        if reference.validity_mask_id is None and array.size > 0:
            return True
        if reference.validity_mask_id is not None and arrays[reference.validity_mask_id].any():
            return True
    return any(
        any(value is not None for row in tables[reference.table_id].rows for value in row)
        for reference in family.table_refs
    )


def _validate_limits(files: Mapping[str, bytes], max_artifact_bytes: int) -> None:
    if max_artifact_bytes <= 0 or max_artifact_bytes > HARD_MAX_ARTIFACT_BYTES:
        raise CharacterizationError("artifact_limit", "invalid recipe artifact limit")
    limits = {
        METADATA_FILENAME: MAX_METADATA_BYTES,
        ARRAYS_FILENAME: MAX_ARRAYS_BYTES,
        TABLES_FILENAME: MAX_TABLES_BYTES,
    }
    if any(len(files[name]) > limit for name, limit in limits.items() if name in files) or sum(
        len(value) for value in files.values()
    ) > min(max_artifact_bytes, HARD_MAX_ARTIFACT_BYTES):
        raise CharacterizationError("artifact_limit", "artifact bundle exceeds its byte limit")
