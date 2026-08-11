"""Pydantic-контракты session context."""

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from lnt.context.model import CollectionStatus, FieldKind, FieldSource


class ContextFieldModel(BaseModel):
    """Типизированное редактируемое поле контекста."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: FieldKind
    value: str | float | bool
    unit: str | None = None
    uncertainty: float | None = Field(default=None, ge=0)
    source: FieldSource = FieldSource.USER
    collection_status: CollectionStatus = CollectionStatus.COLLECTED
    collection_reason: str | None = None
    captured_at: str


class ContextResponse(BaseModel):
    """Материализованный context view."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    session_id: str
    revision: int
    health: str
    reason_codes: tuple[str, ...]
    fields: dict[str, ContextFieldModel]
    tags: tuple[str, ...]
    notes: str | None


class ContextUpdateRequest(BaseModel):
    """Оптимистичная команда частичной замены контекста."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    expected_revision: Annotated[int, Field(ge=0)]
    fields: dict[str, ContextFieldModel] | None = None
    tags: tuple[str, ...] | None = None
    notes: str | None = None


class ContextHistoryItem(BaseModel):
    """Аудит одной revision."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    revision: int
    occurred_at: str
    actor: str
    changed_keys: tuple[str, ...]


class ContextHistoryResponse(BaseModel):
    """Неизменяемая история revisions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    items: tuple[ContextHistoryItem, ...]
