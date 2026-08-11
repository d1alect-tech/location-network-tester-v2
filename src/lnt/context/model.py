"""Неизменяемые доменные типы session context schema 1."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class FieldKind(StrEnum):
    """Машинный тип значения поля контекста."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    TIMESTAMP = "timestamp"


class FieldSource(StrEnum):
    """Источник происхождения значения."""

    AUTOMATIC = "automatic"
    PROFILE = "profile"
    USER = "user"
    DERIVED = "derived"


class CollectionStatus(StrEnum):
    """Результат попытки собрать значение."""

    COLLECTED = "collected"
    UNAVAILABLE = "unavailable"
    NOT_COLLECTED = "not_collected"


type FieldValue = str | float | bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextField:
    """Типизированное значение с единицей, provenance и временем."""

    kind: FieldKind
    value: FieldValue
    unit: str | None
    uncertainty: float | None
    source: FieldSource
    collection_status: CollectionStatus
    collection_reason: str | None
    captured_at: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileSnapshot:
    """Зафиксированная версия применённого профиля."""

    profile_id: str
    revision: int
    captured_at: str
    fields: Mapping[str, ContextField]


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextSnapshot:
    """Полная материализованная версия контекста сессии."""

    schema_version: int
    session_id: str
    revision: int
    fields: Mapping[str, ContextField]
    tags: tuple[str, ...]
    notes: str | None
    profile_snapshots: tuple[ProfileSnapshot, ...]

    @classmethod
    def empty(cls, session_id: str) -> ContextSnapshot:
        """Создаёт явный пустой snapshot revision 0."""
        return cls(
            schema_version=1,
            session_id=session_id,
            revision=0,
            fields={},
            tags=(),
            notes=None,
            profile_snapshots=(),
        )

    def with_field(self, key: str, field: ContextField) -> ContextSnapshot:
        """Возвращает копию snapshot с полем без повышения revision."""
        return replace(self, fields={**self.fields, key: field})

    def next_revision(self, *, fields: Mapping[str, ContextField]) -> ContextSnapshot:
        """Создаёт следующую полную revision с заданными полями."""
        return replace(self, revision=self.revision + 1, fields=dict(fields))
