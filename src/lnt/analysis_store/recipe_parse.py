"""Version dispatcher for strict analysis recipes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lnt.analysis_store.errors import RecipeError
from lnt.analysis_store.recipe import AnalysisRecipe
from lnt.analysis_store.recipe_v2 import CharacterizationRecipe

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.context.json_codec import JsonValue

SCHEMA_VERSION_V2 = 2

type AnalysisRecipeDocument = AnalysisRecipe | CharacterizationRecipe


def parse_analysis_recipe(value: Mapping[str, JsonValue]) -> AnalysisRecipeDocument:
    """Dispatch a recipe by its required integer schema version."""
    version = value.get("schema_version")
    if version == 1:
        return AnalysisRecipe.from_mapping(value)
    if version == SCHEMA_VERSION_V2:
        return CharacterizationRecipe.from_mapping(value)
    raise RecipeError("рецепт анализа: schema_version не поддерживается")
