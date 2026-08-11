"""Plain-SQL репозитории проекций каталога без ORM."""

import sqlite3
from dataclasses import dataclass

from lnt.catalog.models import (
    ArtifactRecipe,
    ContextField,
    Experiment,
    ExperimentMember,
    SessionProjection,
)

_SESSION_COLUMNS = (
    "id, storage_path, path_fingerprint, health, manifest_schema, created_utc, "
    "source, session_type, profile, sample_rate_hz, duration_s, sample_count, label, channels"
)
_UPSERT_SESSION = (
    "INSERT INTO sessions (id, storage_path, path_fingerprint, health, manifest_schema, "
    "created_utc, source, session_type, profile, sample_rate_hz, duration_s, sample_count, "
    "label, channels) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET storage_path=excluded.storage_path, "
    "path_fingerprint=excluded.path_fingerprint, health=excluded.health, "
    "manifest_schema=excluded.manifest_schema, created_utc=excluded.created_utc, "
    "source=excluded.source, session_type=excluded.session_type, profile=excluded.profile, "
    "sample_rate_hz=excluded.sample_rate_hz, duration_s=excluded.duration_s, "
    "sample_count=excluded.sample_count, label=excluded.label, channels=excluded.channels"
)
_SELECT_SESSION = f"SELECT {_SESSION_COLUMNS} FROM sessions WHERE id = ?"  # noqa: S608
_SELECT_CONTEXT_FIELDS = """SELECT session_id, field_key, field_value
FROM context_fields WHERE session_id = ? ORDER BY field_key"""
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


def _session(row: sqlite3.Row) -> SessionProjection:
    return SessionProjection(
        id=row["id"],
        storage_path=row["storage_path"],
        path_fingerprint=row["path_fingerprint"],
        health=row["health"],
        manifest_schema=row["manifest_schema"],
        created_utc=row["created_utc"],
        source=row["source"],
        session_type=row["session_type"],
        profile=row["profile"],
        sample_rate_hz=row["sample_rate_hz"],
        duration_s=row["duration_s"],
        sample_count=row["sample_count"],
        label=row["label"],
        channels=row["channels"],
    )


@dataclass(frozen=True, slots=True)
class SessionRepository:
    """CRUD проекций обнаруженных сессий."""

    connection: sqlite3.Connection

    def upsert(self, item: SessionProjection) -> None:
        """Вставляет либо полностью обновляет проекцию evidence."""
        self.connection.execute(
            _UPSERT_SESSION,
            (
                item.id,
                item.storage_path,
                item.path_fingerprint,
                item.health,
                item.manifest_schema,
                item.created_utc,
                item.source,
                item.session_type,
                item.profile,
                item.sample_rate_hz,
                item.duration_s,
                item.sample_count,
                item.label,
                item.channels,
            ),
        )

    def get(self, session_id: str) -> SessionProjection | None:
        """Возвращает проекцию по stable session ID."""
        row = self.connection.execute(
            _SELECT_SESSION,
            (session_id,),
        ).fetchone()
        return None if row is None else _session(row)

    def delete(self, session_id: str) -> None:
        """Удаляет только disposable-проекцию и её дочерние проекции."""
        self.connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


@dataclass(frozen=True, slots=True)
class ContextRepository:
    """Проекции полей и тегов context sidecar."""

    connection: sqlite3.Connection

    def replace(
        self,
        session_id: str,
        *,
        fields: tuple[ContextField, ...],
        tags: tuple[str, ...],
    ) -> None:
        """Атомарно заменяет производный context индекс сессии."""
        self.connection.execute("DELETE FROM context_fields WHERE session_id = ?", (session_id,))
        self.connection.execute("DELETE FROM context_tags WHERE session_id = ?", (session_id,))
        self.connection.executemany(
            "INSERT INTO context_fields(session_id, field_key, field_value) VALUES (?, ?, ?)",
            ((field.session_id, field.key, field.value) for field in fields),
        )
        self.connection.executemany(
            "INSERT INTO context_tags(session_id, tag) VALUES (?, ?)",
            ((session_id, tag) for tag in tags),
        )

    def fields(self, session_id: str) -> tuple[ContextField, ...]:
        """Читает поля контекста в стабильном порядке ключей."""
        rows = self.connection.execute(
            _SELECT_CONTEXT_FIELDS,
            (session_id,),
        )
        return tuple(ContextField(row[0], row[1], row[2]) for row in rows)

    def tags(self, session_id: str) -> tuple[str, ...]:
        """Читает теги контекста в стабильном порядке."""
        rows = self.connection.execute(
            "SELECT tag FROM context_tags WHERE session_id = ? ORDER BY tag",
            (session_id,),
        )
        return tuple(row[0] for row in rows)


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
        rows = self.connection.execute(
            _SELECT_ARTIFACTS,
            (session_id,),
        )
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
        self.connection.execute(
            _UPSERT_EXPERIMENT,
            (item.id, item.storage_ref, item.health),
        )

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
        rows = self.connection.execute(
            _SELECT_MEMBERS,
            (experiment_id,),
        )
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


@dataclass(frozen=True, slots=True, init=False)
class CatalogRepositories:
    """Согласованный набор repositories поверх одной транзакции."""

    sessions: SessionRepository
    context: ContextRepository
    artifacts: ArtifactRepository
    experiments: ExperimentRepository

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Привязывает все repositories к одному соединению."""
        object.__setattr__(self, "sessions", SessionRepository(connection))
        object.__setattr__(self, "context", ContextRepository(connection))
        object.__setattr__(self, "artifacts", ArtifactRepository(connection))
        object.__setattr__(self, "experiments", ExperimentRepository(connection))
