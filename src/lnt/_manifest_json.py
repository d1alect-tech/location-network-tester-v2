"""Строгий JSON-кодек manifest.json без неконечных чисел и дубликатов ключей."""

import json
import math
from collections.abc import Mapping
from typing import Final, Never

from lnt.errors import InputError

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

NON_FINITE_MESSAGE: Final = "manifest: JSON содержит неконечное число"


def encode_json(value: Mapping[str, JsonValue]) -> str:
    """Сериализует JSON-object, запрещая NaN и бесконечности на любой глубине."""
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    except ValueError as error:
        raise InputError(NON_FINITE_MESSAGE) from error


def decode_json_object(text: str) -> dict[str, JsonValue]:
    """Разбирает строгий JSON-object с уникальными ключами на любой глубине."""
    try:
        value: JsonValue = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite_constant,
            parse_float=_parse_finite_float,
        )
    except json.JSONDecodeError as error:
        raise InputError(f"manifest: некорректный JSON: {error}") from error
    if not isinstance(value, dict):
        raise InputError("manifest: ожидается JSON-object на верхнем уровне")
    return value


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"manifest: повторяющееся поле {key!r}")
        result[key] = value
    return result


def _reject_non_finite_constant(_literal: str) -> Never:
    raise InputError(NON_FINITE_MESSAGE)


def _parse_finite_float(literal: str) -> float:
    value = float(literal)
    if not math.isfinite(value):
        raise InputError(NON_FINITE_MESSAGE)
    return value
