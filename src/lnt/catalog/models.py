"""Типизированные строки проекционного каталога LNT."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionProjection:
    """Нормализованная проекция ключевых полей manifest.json."""

    id: str
    storage_path: str
    path_fingerprint: str
    health: str
    manifest_schema: int | None
    created_utc: str | None
    source: str | None
    session_type: str | None
    profile: str | None
    sample_rate_hz: float | None
    duration_s: float | None
    sample_count: int | None
    label: str | None
    channels: str | None

    @classmethod
    def minimal(
        cls,
        *,
        id: str,  # noqa: A002 - имя совпадает с колонкой и публичным полем модели
        storage_path: str,
        path_fingerprint: str,
        health: str,
    ) -> "SessionProjection":
        """Создаёт проекцию без доступного валидного манифеста."""
        return cls(
            id=id,
            storage_path=storage_path,
            path_fingerprint=path_fingerprint,
            health=health,
            manifest_schema=None,
            created_utc=None,
            source=None,
            session_type=None,
            profile=None,
            sample_rate_hz=None,
            duration_s=None,
            sample_count=None,
            label=None,
            channels=None,
        )


@dataclass(frozen=True, slots=True)
class ContextField:
    """Одно индексируемое поле контекста сессии."""

    session_id: str
    key: str
    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactRecipe:
    """Ссылка на неизменяемый артефакт по identity рецепта."""

    recipe_sha256: str
    session_id: str
    artifact_key: str
    storage_ref: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Experiment:
    """Проекция опубликованного внешнего эксперимента."""

    id: str
    storage_ref: str
    health: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentMember:
    """Упорядоченная ссылка эксперимента на evidence сессии/анализа."""

    experiment_id: str
    ordinal: int
    session_id: str
    session_storage_ref: str
    artifact_key: str | None
    recipe_sha256: str | None
