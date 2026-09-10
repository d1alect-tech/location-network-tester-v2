"""Immutable on-disk recipe catalog with clone-only evolution."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 - runtime catalog paths

from lnt.analysis_store import AnalysisRecipe
from lnt.analysis_store.errors import RecipeError
from lnt.analysis_store.identity import SHA256_LENGTH
from lnt.safe_paths import is_linked_path


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredRecipe:
    """Named immutable recipe identified by its canonical hash."""

    recipe_id: str
    name: str
    recipe: AnalysisRecipe

    def payload(self) -> dict[str, object]:
        """Return a JSON-compatible API payload."""
        return {"recipe_id": self.recipe_id, "name": self.name, "recipe": self.recipe.to_mapping()}


class RecipeCatalog:
    """Persist immutable recipes and clone them into new identities."""

    def __init__(self, root: Path) -> None:
        """Bind the catalog to one directory."""
        self._root: Path = root

    def create(self, name: str, recipe: AnalysisRecipe) -> StoredRecipe:
        """Create a recipe unless its identity already exists."""
        self._validate_root()
        stored = StoredRecipe(recipe_id=recipe.recipe_sha256, name=name, recipe=recipe)
        path = self._root / f"{stored.recipe_id}.json"
        if not path.exists():
            self._atomic_write(path, stored)
        return stored

    def list(self) -> tuple[StoredRecipe, ...]:
        """List stored recipes in identity order."""
        self._validate_root()
        if not self._root.is_dir():
            return ()
        return tuple(
            self._read(path)
            for path in sorted(self._root.glob("*.json"))
            if not is_linked_path(path)
        )

    def get(self, recipe_id: str) -> StoredRecipe:
        """Load one immutable recipe by identity."""
        self._validate_id(recipe_id)
        self._validate_root()
        path = self._root / f"{recipe_id}.json"
        if is_linked_path(path):
            raise RecipeError("файл рецепта не должен быть ссылкой")
        return self._read(path)

    def clone(self, recipe_id: str, name: str) -> StoredRecipe:
        """Create a new identity without mutating the source."""
        source = self.get(recipe_id)
        clone = source.recipe.clone(mode=f"{source.recipe.mode}:clone:{uuid.uuid4().hex[:8]}")
        return self.create(name, clone)

    def _atomic_write(self, path: Path, stored: StoredRecipe) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.partial-{uuid.uuid4().hex}")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(stored.payload(), stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)  # noqa: PTH105 - explicit atomic seam
        finally:
            temporary.unlink(missing_ok=True)

    def _validate_root(self) -> None:
        if is_linked_path(self._root) or is_linked_path(self._root.parent):
            raise RecipeError("каталог рецептов не должен быть ссылкой")

    @staticmethod
    def _validate_id(recipe_id: str) -> None:
        if len(recipe_id) != SHA256_LENGTH or any(
            char not in "0123456789abcdef" for char in recipe_id
        ):
            raise RecipeError("recipe_id должен быть lowercase SHA-256")

    @staticmethod
    def _read(path: Path) -> StoredRecipe:
        """Читает рецепт и проверяет identity: имя файла = payload ID = canonical hash."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        stored = StoredRecipe(
            recipe_id=str(payload["recipe_id"]),
            name=str(payload["name"]),
            recipe=AnalysisRecipe.from_mapping(payload["recipe"]),
        )
        if stored.recipe_id != path.stem or stored.recipe.recipe_sha256 != stored.recipe_id:
            raise RecipeError("identity сохранённого рецепта не совпадает с canonical hash")
        return stored
