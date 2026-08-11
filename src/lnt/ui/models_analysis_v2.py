"""Pydantic boundaries for analysis v2 HTTP requests."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from lnt.context.json_codec import JsonValue  # noqa: TC001 - Pydantic field type


class RecipeCreateRequest(BaseModel):
    """Create an immutable named analysis recipe."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    name: str
    recipe: dict[str, JsonValue]


class RecipeCloneRequest(BaseModel):
    """Clone a recipe into a new immutable identity."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    name: str


class AnalysisRunRequest(BaseModel):
    """Start analysis for one session and recipe identity."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    session: str
    recipe_id: str
    make_default: bool = False
