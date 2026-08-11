"""Строгий JSON-кодек контекста без дубликатов и неконечных чисел."""

import json
import math
from collections.abc import Mapping
from typing import Never

from lnt.errors import InputError

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


def decode_object(text: str, label: str) -> dict[str, JsonValue]:
    """Разбирает строгий JSON-object."""
    try:
        value: JsonValue = json.loads(
            text,
            object_pairs_hook=lambda pairs: _unique_object(pairs, label),
            parse_constant=lambda literal: _reject_constant(literal, label),
            parse_float=lambda literal: _finite_float(literal, label),
        )
    except json.JSONDecodeError as error:
        raise InputError(f"{label}: некорректный JSON: {error}") from error
    if not isinstance(value, dict):
        raise InputError(f"{label}: ожидается JSON-object")
    return value


def encode_pretty(value: Mapping[str, JsonValue], label: str) -> str:
    """Сериализует читаемый JSON с завершающей новой строкой."""
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    except ValueError as error:
        raise InputError(f"{label}: JSON содержит неконечное число") from error


def encode_canonical(value: Mapping[str, JsonValue], label: str) -> bytes:
    """Сериализует канонические UTF-8 байты для хеширования."""
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except ValueError as error:
        raise InputError(f"{label}: JSON содержит неконечное число") from error
    return text.encode("utf-8")


def _unique_object(
    pairs: list[tuple[str, JsonValue]],
    label: str,
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"{label}: повторяющееся поле {key!r}")
        result[key] = value
    return result


def _reject_constant(_literal: str, label: str) -> Never:
    raise InputError(f"{label}: JSON содержит неконечное число")


def _finite_float(literal: str, label: str) -> float:
    value = float(literal)
    if not math.isfinite(value):
        raise InputError(f"{label}: JSON содержит неконечное число")
    return value
