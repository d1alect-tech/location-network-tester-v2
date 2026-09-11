"""Strict JSON parsing primitives for characterization codecs."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from lnt.characterization.errors import CharacterizationError
from lnt.context.json_codec import JsonValue, decode_object
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Mapping


def decode(data: bytes, label: str) -> dict[str, JsonValue]:
    """Decode one strict UTF-8 JSON object."""
    try:
        return decode_object(data.decode("utf-8"), label)
    except (InputError, UnicodeDecodeError, ValueError) as error:
        raise CharacterizationError("json_decode", f"invalid {label}") from error


def exact(raw: Mapping[str, JsonValue], fields: frozenset[str], label: str) -> None:
    """Require all and only the declared fields."""
    if frozenset(raw) != fields:
        raise CharacterizationError("json_fields", f"{label} fields do not match schema")


def mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    """Require a JSON object."""
    if not isinstance(value, dict):
        raise CharacterizationError("json_type", f"{label} must be object")
    return value


def array(raw: Mapping[str, JsonValue], key: str, label: str) -> list[JsonValue]:
    """Require an array field."""
    value = raw.get(key)
    if not isinstance(value, list):
        raise CharacterizationError("json_type", f"{label}.{key} must be array")
    return value


def string(raw: Mapping[str, JsonValue], key: str, label: str) -> str:
    """Require a nonempty string field."""
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise CharacterizationError("json_type", f"{label}.{key} must be nonempty string")
    return value


def optional_string(raw: Mapping[str, JsonValue], key: str, label: str) -> str | None:
    """Require a nonempty string or null field."""
    value = raw.get(key)
    return None if value is None else string(raw, key, label)


def integer(raw: Mapping[str, JsonValue], key: str, label: str) -> int:
    """Require an integer field."""
    return integer_value(raw.get(key), f"{label}.{key}")


def integer_value(value: JsonValue, label: str) -> int:
    """Require an integer value, excluding bool."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CharacterizationError("json_type", f"{label} must be integer")
    return value


def optional_integer(raw: Mapping[str, JsonValue], key: str, label: str) -> int | None:
    """Require an integer or null field."""
    value = raw.get(key)
    return None if value is None else integer_value(value, f"{label}.{key}")


def number(raw: Mapping[str, JsonValue], key: str, label: str) -> float:
    """Require a numeric field, excluding bool."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CharacterizationError("json_type", f"{label}.{key} must be number")
    return float(value)


def optional_number(raw: Mapping[str, JsonValue], key: str, label: str) -> float | None:
    """Require a numeric or null field."""
    value = raw.get(key)
    return None if value is None else number(raw, key, label)


def boolean(raw: Mapping[str, JsonValue], key: str, label: str) -> bool:
    """Require a boolean field."""
    value = raw.get(key)
    if not isinstance(value, bool):
        raise CharacterizationError("json_type", f"{label}.{key} must be boolean")
    return value


def strings(raw: Mapping[str, JsonValue], key: str, label: str) -> tuple[str, ...]:
    """Require an array of nonempty strings."""
    values = array(raw, key, label)
    if any(not isinstance(value, str) or not value for value in values):
        raise CharacterizationError("json_type", f"{label}.{key} must contain strings")
    return tuple(value for value in values if isinstance(value, str))


def enum[EnumT: StrEnum](
    raw: Mapping[str, JsonValue], key: str, enum_type: type[EnumT], label: str
) -> EnumT:
    """Require a member of a closed string enum."""
    return enum_value(raw.get(key), enum_type, f"{label}.{key}")


def enum_value[EnumT: StrEnum](value: JsonValue, enum_type: type[EnumT], label: str) -> EnumT:
    """Require a value from a closed string enum."""
    if not isinstance(value, str):
        raise CharacterizationError("json_type", f"{label} must be string")
    try:
        return enum_type(value)
    except ValueError as error:
        raise CharacterizationError("json_enum", f"unknown {label}") from error
