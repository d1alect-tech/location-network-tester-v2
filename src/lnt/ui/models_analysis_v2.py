"""Pydantic boundaries for analysis v2 HTTP requests."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, StringConstraints

from lnt.context.json_codec import JsonValue  # noqa: TC001 - Pydantic field type

SessionKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
Sha256Key = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


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
    session: SessionKey
    recipe_id: Sha256Key
    make_default: bool = False
