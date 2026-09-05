"""Чистые валидационные примитивы manifest.json (без доменных импортов)."""

import math
from collections.abc import Mapping
from enum import StrEnum

from lnt.errors import InputError

__all__ = [
    "_opt_object",
    "_opt_str",
    "_reject_unknown_fields",
    "_req",
    "_req_bool",
    "_req_enum",
    "_req_float",
    "_req_float_tuple",
    "_req_int",
    "_req_int_tuple",
    "_req_object",
    "_req_str",
]


def _reject_unknown_fields(
    obj: Mapping[str, object],
    allowed: frozenset[str],
    context: str,
) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise InputError(f"{context}: неизвестные поля {names}")


def _req(obj: Mapping[str, object], key: str) -> object:
    if key not in obj:
        raise InputError(f"manifest: отсутствует поле {key!r}")
    return obj[key]


def _req_str(obj: Mapping[str, object], key: str) -> str:
    value = _req(obj, key)
    if not isinstance(value, str):
        raise InputError(f"manifest: поле {key!r} должно быть строкой")
    return value


def _opt_str(obj: Mapping[str, object], key: str) -> str | None:
    value = _req(obj, key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InputError(f"manifest: поле {key!r} должно быть строкой или null")
    return value


def _req_int(obj: Mapping[str, object], key: str) -> int:
    value = _req(obj, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"manifest: поле {key!r} должно быть целым числом")
    return value


def _req_float(obj: Mapping[str, object], key: str) -> float:
    value = _req(obj, key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InputError(f"manifest: поле {key!r} должно быть числом")
    number = float(value)
    if not math.isfinite(number):
        raise InputError(f"manifest: поле {key!r} должно быть конечным числом")
    return number


def _req_bool(obj: Mapping[str, object], key: str) -> bool:
    value = _req(obj, key)
    if not isinstance(value, bool):
        raise InputError(f"manifest: поле {key!r} должно быть булевым")
    return value


def _req_object(obj: Mapping[str, object], key: str) -> dict[str, object]:
    value = _req(obj, key)
    if not isinstance(value, dict):
        raise InputError(f"manifest: поле {key!r} должно быть JSON-object")
    result: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise InputError(f"manifest: поле {key!r} должно быть JSON-object")
        result[raw_key] = raw_value
    return result


def _opt_object(obj: Mapping[str, object], key: str) -> dict[str, object] | None:
    value = _req(obj, key)
    if value is None:
        return None
    return _req_object(obj, key)


def _req_enum[E: StrEnum](obj: Mapping[str, object], key: str, enum_type: type[E]) -> E:
    raw = _req_str(obj, key)
    try:
        return enum_type(raw)
    except ValueError as error:
        raise InputError(f"manifest: недопустимое значение поля {key!r}: {raw!r}") from error


def _req_int_tuple(obj: Mapping[str, object], key: str) -> tuple[int, ...]:
    value = _req(obj, key)
    if not isinstance(value, list):
        raise InputError(f"manifest: поле {key!r} должно быть списком")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise InputError(f"manifest: элементы {key!r} должны быть целыми числами")
        result.append(item)
    return tuple(result)


def _req_float_tuple(obj: Mapping[str, object], key: str) -> tuple[float, ...]:
    value = _req(obj, key)
    if not isinstance(value, list):
        raise InputError(f"manifest: поле {key!r} должно быть списком")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float) or not math.isfinite(item):
            raise InputError(f"manifest: элементы {key!r} должны быть конечными числами")
        result.append(float(item))
    return tuple(result)
