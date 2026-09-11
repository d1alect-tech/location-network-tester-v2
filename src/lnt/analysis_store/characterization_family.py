"""Frozen, strictly shaped characterization family blocks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lnt.analysis_store.characterization_contract import FAMILY_FIELDS
from lnt.analysis_store.characterization_locked import LOCKED_VALUES
from lnt.analysis_store.characterization_parse import (
    ParameterValue,
    freeze_parameter,
    group,
    integer,
    thaw_parameter,
)
from lnt.analysis_store.errors import RecipeError

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterizationFamily:
    """One locked method block with immutable validated parameters."""

    id: str
    method: str
    method_version: int
    parameters: tuple[tuple[str, ParameterValue], ...]

    @classmethod
    def from_mapping(cls, value: JsonValue, expected_id: str) -> CharacterizationFamily:
        """Parse the exact fields and method assigned to one family ID."""
        method, fields = FAMILY_FIELDS[expected_id]
        raw = group(value, expected_id, ("id", "method", "method_version", *fields))
        if raw["id"] != expected_id:
            raise RecipeError("рецепт characterization: families должны иметь точные ID и порядок")
        method_version = integer(raw["method_version"], f"{expected_id}.method_version")
        if raw["method"] != method or method_version != 1:
            raise RecipeError(
                f"рецепт characterization: {expected_id}: method/version не поддерживается"
            )
        parameters = tuple(
            (name, freeze_parameter(raw[name], f"{expected_id}.{name}")) for name in fields
        )
        family = cls(
            id=expected_id, method=method, method_version=method_version, parameters=parameters
        )
        family._validate_locked_values()
        return family

    def value(self, name: str) -> ParameterValue:
        """Return one validated family parameter by name."""
        for key, value in self.parameters:
            if key == name:
                return value
        raise RecipeError(f"рецепт characterization: {self.id}: отсутствует {name}")

    def to_mapping(self) -> dict[str, JsonValue]:
        """Return the semantic JSON family block."""
        return {
            "id": self.id,
            "method": self.method,
            "method_version": self.method_version,
            **{name: thaw_parameter(value) for name, value in self.parameters},
        }

    def _validate_locked_values(self) -> None:
        for name, expected in LOCKED_VALUES.get(self.id, {}).items():
            if self.value(name) != expected:
                raise RecipeError(f"рецепт characterization: {self.id}.{name} не поддерживается")
