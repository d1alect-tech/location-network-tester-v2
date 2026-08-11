"""Immutable on-disk recipe catalog with clone-only evolution."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 - runtime catalog paths

from lnt.analysis_store import AnalysisRecipe


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
        stored = StoredRecipe(recipe_id=recipe.recipe_sha256, name=name, recipe=recipe)
        path = self._root / f"{stored.recipe_id}.json"
        if not path.exists():
            self._atomic_write(path, stored)
        return stored

    def list(self) -> tuple[StoredRecipe, ...]:
        """List stored recipes in identity order."""
        if not self._root.is_dir():
            return ()
        return tuple(self._read(path) for path in sorted(self._root.glob("*.json")))

    def get(self, recipe_id: str) -> StoredRecipe:
        """Load one immutable recipe by identity."""
        return self._read(self._root / f"{recipe_id}.json")

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

    @staticmethod
    def _read(path: Path) -> StoredRecipe:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StoredRecipe(
            recipe_id=str(payload["recipe_id"]),
            name=str(payload["name"]),
            recipe=AnalysisRecipe.from_mapping(payload["recipe"]),
        )
