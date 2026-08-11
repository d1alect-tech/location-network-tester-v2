"""Согласованный набор SQL-репозиториев одной транзакции каталога."""

import sqlite3
from dataclasses import dataclass

from lnt.catalog.evidence_repositories import ArtifactRepository, ExperimentRepository
from lnt.catalog.session_repositories import ContextRepository, SessionRepository


@dataclass(frozen=True, slots=True, init=False)
class CatalogRepositories:
    """Группирует repositories поверх одного SQLite-соединения."""

    sessions: SessionRepository
    context: ContextRepository
    artifacts: ArtifactRepository
    experiments: ExperimentRepository

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Привязывает все repositories к одной транзакции."""
        object.__setattr__(self, "sessions", SessionRepository(connection))
        object.__setattr__(self, "context", ContextRepository(connection))
        object.__setattr__(self, "artifacts", ArtifactRepository(connection))
        object.__setattr__(self, "experiments", ExperimentRepository(connection))
