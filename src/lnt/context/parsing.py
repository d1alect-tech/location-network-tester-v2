"""Переиспользуемые строгие примитивы разбора context JSON."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.context.json_codec import JsonValue


def required(raw: Mapping[str, JsonValue], key: str, label: str) -> JsonValue:
    """Возвращает обязательное поле или поднимает InputError."""
    if key not in raw:
        raise InputError(f"{label}: отсутствует поле {key!r}")
    return raw[key]


def string(raw: Mapping[str, JsonValue], key: str, label: str) -> str:
    """Разбирает обязательную строку."""
    return string_item(required(raw, key, label), f"{label}.{key}")


def string_item(value: JsonValue, label: str) -> str:
    """Разбирает JSON-значение как строку."""
    if not isinstance(value, str):
        raise InputError(f"{label}: ожидается строка")
    return value


def integer(raw: Mapping[str, JsonValue], key: str, label: str) -> int:
    """Разбирает целое, отдельно отвергая bool."""
    value = required(raw, key, label)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"{label}.{key}: ожидается целое число")
    return value


def optional_number(raw: Mapping[str, JsonValue], key: str, label: str) -> float | None:
    """Разбирает конечное число либо null; конечность проверяет домен."""
    value = required(raw, key, label)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InputError(f"{label}.{key}: ожидается число или null")
    return float(value)


def optional_string(raw: Mapping[str, JsonValue], key: str, label: str) -> str | None:
    """Разбирает строку либо null."""
    value = required(raw, key, label)
    if value is None:
        return None
    return string_item(value, f"{label}.{key}")


def mapping(raw: Mapping[str, JsonValue], key: str, label: str) -> dict[str, JsonValue]:
    """Разбирает обязательный вложенный object."""
    return as_mapping(required(raw, key, label), f"{label}.{key}")


def as_mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    """Разбирает JSON-значение как object."""
    if not isinstance(value, dict):
        raise InputError(f"{label}: ожидается object")
    return value


def json_list(raw: Mapping[str, JsonValue], key: str, label: str) -> list[JsonValue]:
    """Разбирает обязательный array."""
    value = required(raw, key, label)
    if not isinstance(value, list):
        raise InputError(f"{label}.{key}: ожидается array")
    return value


def enum_value[EnumT: StrEnum](
    raw: Mapping[str, JsonValue],
    key: str,
    enum_type: type[EnumT],
    label: str,
) -> EnumT:
    """Разбирает строковое значение конкретного StrEnum."""
    value = string(raw, key, label)
    try:
        return enum_type(value)
    except ValueError as error:
        raise InputError(f"{label}.{key}: неизвестное значение {value!r}") from error


def reject_unknown(
    raw: Mapping[str, JsonValue],
    allowed: frozenset[str],
    label: str,
) -> None:
    """Отвергает все неизвестные поля object."""
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise InputError(f"{label}: неизвестные поля {', '.join(unknown)}")
