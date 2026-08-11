"""SQL-репозитории артефактов и внешних экспериментов."""

import sqlite3
from dataclasses import dataclass

from lnt.catalog.models import ArtifactRecipe, Experiment, ExperimentMember

_UPSERT_ARTIFACT = """INSERT INTO artifact_recipes(
recipe_sha256, session_id, artifact_key, storage_ref
) VALUES (?, ?, ?, ?) ON CONFLICT(recipe_sha256) DO UPDATE SET
session_id=excluded.session_id, artifact_key=excluded.artifact_key,
storage_ref=excluded.storage_ref"""
_SELECT_ARTIFACTS = """SELECT recipe_sha256, session_id, artifact_key, storage_ref
FROM artifact_recipes WHERE session_id = ? ORDER BY artifact_key"""
_UPSERT_EXPERIMENT = """INSERT INTO experiments(id, storage_ref, health) VALUES (?, ?, ?)
ON CONFLICT(id) DO UPDATE SET storage_ref=excluded.storage_ref, health=excluded.health"""
_INSERT_MEMBER = """INSERT INTO experiment_members(
experiment_id, ordinal, session_id, session_storage_ref, artifact_key, recipe_sha256
) VALUES (?, ?, ?, ?, ?, ?)"""
_SELECT_MEMBERS = """SELECT experiment_id, ordinal, session_id, session_storage_ref,
artifact_key, recipe_sha256 FROM experiment_members
WHERE experiment_id = ? ORDER BY ordinal"""


@dataclass(frozen=True, slots=True)
class ArtifactRepository:
    """Проекции analysis artifact recipes."""

    connection: sqlite3.Connection

    def upsert(self, item: ArtifactRecipe) -> None:
        """Индексирует artifact-key с immutable recipe identity."""
        self.connection.execute(
            _UPSERT_ARTIFACT,
            (item.recipe_sha256, item.session_id, item.artifact_key, item.storage_ref),
        )

    def for_session(self, session_id: str) -> tuple[ArtifactRecipe, ...]:
        """Читает рецепты сессии по artifact-key."""
        rows = self.connection.execute(_SELECT_ARTIFACTS, (session_id,))
        return tuple(
            ArtifactRecipe(
                recipe_sha256=row[0],
                session_id=row[1],
                artifact_key=row[2],
                storage_ref=row[3],
            )
            for row in rows
        )


@dataclass(frozen=True, slots=True)
class ExperimentRepository:
    """Проекции внешних экспериментов и их evidence-ссылок."""

    connection: sqlite3.Connection

    def upsert(self, item: Experiment) -> None:
        """Вставляет либо обновляет проекцию эксперимента."""
        self.connection.execute(_UPSERT_EXPERIMENT, (item.id, item.storage_ref, item.health))

    def get(self, experiment_id: str) -> Experiment | None:
        """Возвращает эксперимент по ID."""
        row = self.connection.execute(
            "SELECT id, storage_ref, health FROM experiments WHERE id = ?",
            (experiment_id,),
        ).fetchone()
        return None if row is None else Experiment(id=row[0], storage_ref=row[1], health=row[2])

    def replace_members(
        self,
        experiment_id: str,
        members: tuple[ExperimentMember, ...],
    ) -> None:
        """Заменяет упорядоченный индекс members одной ревизии."""
        self.connection.execute(
            "DELETE FROM experiment_members WHERE experiment_id = ?",
            (experiment_id,),
        )
        self.connection.executemany(
            _INSERT_MEMBER,
            (
                (
                    item.experiment_id,
                    item.ordinal,
                    item.session_id,
                    item.session_storage_ref,
                    item.artifact_key,
                    item.recipe_sha256,
                )
                for item in members
            ),
        )

    def members(self, experiment_id: str) -> tuple[ExperimentMember, ...]:
        """Читает members в опубликованном порядке."""
        rows = self.connection.execute(_SELECT_MEMBERS, (experiment_id,))
        return tuple(
            ExperimentMember(
                experiment_id=row[0],
                ordinal=row[1],
                session_id=row[2],
                session_storage_ref=row[3],
                artifact_key=row[4],
                recipe_sha256=row[5],
            )
            for row in rows
        )
