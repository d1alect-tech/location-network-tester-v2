"""Strict parsing primitives for characterization recipe schema 2."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from lnt.analysis_store.errors import RecipeError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.context.json_codec import JsonValue

type ParameterValue = str | int | float | tuple[ParameterValue, ...]


def group(value: JsonValue, name: str, fields: tuple[str, ...]) -> dict[str, JsonValue]:
    """Require a JSON object with exactly the declared fields."""
    if not isinstance(value, dict):
        raise RecipeError(f"рецепт characterization: {name} должен быть JSON-object")
    expected = frozenset(fields)
    unknown = value.keys() - expected
    missing = expected - value.keys()
    if unknown or missing:
        message = f"неизвестные={sorted(unknown)}, отсутствуют={sorted(missing)}"
        raise RecipeError(f"рецепт characterization: {name}: {message}")
    return value


def root_group(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Require the exact schema-2 root shape."""
    expected = (
        "schema_version",
        "mode",
        "channels",
        "resource_limits",
        "phase",
        "stft",
        "events",
        "families",
    )
    unknown = value.keys() - frozenset(expected)
    missing = frozenset(expected) - value.keys()
    if unknown or missing:
        raise RecipeError(
            f"рецепт characterization: неизвестные={sorted(unknown)}, отсутствуют={sorted(missing)}"
        )
    return dict(value)


def string(value: JsonValue, name: str) -> str:
    """Read a nonempty string."""
    if not isinstance(value, str) or not value:
        raise RecipeError(f"рецепт characterization: {name} должен быть непустой строкой")
    return value


def integer(value: JsonValue, name: str) -> int:
    """Read an integer excluding booleans."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise RecipeError(f"рецепт characterization: {name} должен быть целым числом")
    return value


def number(value: JsonValue, name: str) -> float:
    """Read a finite JSON number excluding booleans."""
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise RecipeError(f"рецепт characterization: {name} должен быть конечным числом")
    return float(value)


def string_list(value: JsonValue, name: str) -> tuple[str, ...]:
    """Read an array of nonempty strings."""
    if not isinstance(value, list):
        raise RecipeError(f"рецепт characterization: {name} должен быть массивом")
    return tuple(string(item, f"{name}[]") for item in value)


def freeze_parameter(value: JsonValue, name: str) -> ParameterValue:
    """Recursively freeze a scalar/list family parameter."""
    if isinstance(value, str):
        return string(value, name)
    if isinstance(value, bool) or value is None or isinstance(value, dict):
        raise RecipeError(f"рецепт characterization: {name} имеет недопустимый тип")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RecipeError(f"рецепт characterization: {name} должен быть конечным числом")
        return value
    return tuple(freeze_parameter(item, f"{name}[]") for item in value)


def thaw_parameter(value: ParameterValue) -> JsonValue:
    """Restore frozen family parameters to JSON values."""
    if isinstance(value, tuple):
        return [thaw_parameter(item) for item in value]
    return value
