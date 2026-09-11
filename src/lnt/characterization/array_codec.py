"""Deterministic finite numeric NPZ codec."""

from __future__ import annotations

import io
import re
import zipfile
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.errors import CharacterizationError

if TYPE_CHECKING:
    from collections.abc import Mapping

type NumericArray = NDArray[np.bool_ | np.integer | np.floating | np.complexfloating]

_NAME: Final = re.compile(r"[a-z][a-z0-9_]*\Z")
_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)


def encode_arrays(arrays: Mapping[str, np.ndarray]) -> bytes:
    """Encode sorted NPY members into a pinned ZIP container."""
    validated = {name: _validate_array(name, value) for name, value in arrays.items()}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for name in sorted(validated):
            payload = io.BytesIO()
            np.lib.format.write_array(payload, validated[name], allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", _TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, payload.getvalue())
    return output.getvalue()


def decode_arrays(data: bytes, *, maximum_uncompressed_bytes: int) -> dict[str, NumericArray]:
    """Strictly decode bounded numeric NPY members without pickle."""
    result: dict[str, NumericArray] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            _validate_members(
                infos, names, sum(info.file_size for info in infos), maximum_uncompressed_bytes
            )
            for info in infos:
                if not info.filename.endswith(".npy"):
                    _invalid_member()
                name = info.filename.removesuffix(".npy")
                _validate_name(name)
                with archive.open(info) as stream:
                    value = np.lib.format.read_array(stream, allow_pickle=False)
                result[name] = _validate_array(name, value)
    except CharacterizationError:
        raise
    except (OSError, ValueError, EOFError, zipfile.BadZipFile) as error:
        raise CharacterizationError("array_archive", "invalid NPZ archive") from error
    return result


def validate_array_relations(
    arrays: Mapping[str, np.ndarray],
    *,
    values: Mapping[str, tuple[str, tuple[int, ...], str | None, str | None]],
) -> None:
    """Validate reference dtype/shape and mask/offset semantics."""
    expected: set[str] = set()
    for name, (_, _, mask_name, offsets_name) in values.items():
        expected.add(name)
        if mask_name is not None:
            expected.add(mask_name)
        if offsets_name is not None:
            expected.add(offsets_name)
    if set(arrays) != expected:
        raise CharacterizationError("array_references", "array members do not resolve exactly")
    for name, (dtype, shape, mask_name, offsets_name) in values.items():
        array = arrays.get(name)
        if array is None or array.dtype.name != dtype or array.shape != shape:
            raise CharacterizationError("array_shape", f"{name} does not match its reference")
        if mask_name is not None:
            _validate_mask(arrays.get(mask_name), array, name)
        if offsets_name is not None:
            _validate_offsets(arrays.get(offsets_name), array.shape[0], name)


def _validate_members(
    infos: list[zipfile.ZipInfo], names: list[str], size: int, limit: int
) -> None:
    if (
        names != sorted(names)
        or len({name.casefold() for name in names}) != len(names)
        or any(
            info.date_time != _TIMESTAMP
            or info.create_system != 0
            or info.compress_type != zipfile.ZIP_DEFLATED
            for info in infos
        )
    ):
        raise CharacterizationError("array_members", "members must be unique and sorted")
    if size > limit:
        raise CharacterizationError("artifact_limit", "NPZ expands beyond its limit")


def _invalid_member() -> None:
    raise CharacterizationError("array_members", "NPZ contains an unknown member")


def _validate_mask(mask: np.ndarray | None, array: np.ndarray, name: str) -> None:
    if (
        mask is None
        or mask.dtype != np.dtype(np.uint8)
        or mask.shape != array.shape
        or not np.all((mask == 0) | (mask == 1))
    ):
        raise CharacterizationError("array_mask", f"invalid validity mask for {name}")


def _validate_offsets(offsets: np.ndarray | None, size: int, name: str) -> None:
    if (
        offsets is None
        or offsets.ndim != 1
        or offsets.dtype.kind not in "iu"
        or offsets.size == 0
        or offsets[0] != 0
        or offsets[-1] != size
        or np.any(np.diff(offsets) < 0)
    ):
        raise CharacterizationError("array_offsets", f"invalid ragged offsets for {name}")


def _validate_name(name: str) -> None:
    if _NAME.fullmatch(name) is None:
        raise CharacterizationError("array_name", f"unsafe array name {name!r}")


def _validate_array(name: str, value: np.ndarray) -> NumericArray:
    _validate_name(name)
    if value.dtype.kind not in "biufc":
        raise CharacterizationError("array_dtype", f"{name} must be a numeric array")
    if value.dtype.hasobject or not np.all(np.isfinite(value)):
        raise CharacterizationError("array_finite", f"{name} must contain finite values")
    return value
