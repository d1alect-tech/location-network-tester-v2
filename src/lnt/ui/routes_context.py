"""HTTP API оптимистично версионированного session context."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from lnt.context.events import read_event_history
from lnt.context.model import ContextField, ContextSnapshot
from lnt.context.store import ContextConflictError, ContextStore, ContextUpdate
from lnt.errors import InputError
from lnt.ui.api_support import session_directory
from lnt.ui.models_context import (
    ContextFieldModel,
    ContextHistoryItem,
    ContextHistoryResponse,
    ContextResponse,
    ContextUpdateRequest,
)

router = APIRouter(prefix="/api/context")


def _response(session_id: str, store: ContextStore) -> ContextResponse:
    view = store.load()
    snapshot = view.snapshot or ContextSnapshot.empty(session_id)
    return ContextResponse(
        session_id=session_id,
        revision=snapshot.revision,
        health=view.health,
        reason_codes=view.reason_codes,
        fields={
            key: ContextFieldModel.model_validate(value, from_attributes=True)
            for key, value in snapshot.fields.items()
        },
        tags=snapshot.tags,
        notes=snapshot.notes,
    )


@router.get("/{session_id}")
def show_context(session_id: str) -> ContextResponse:
    """Читает материализованный context view сессии."""
    directory = session_directory(session_id)
    return _response(session_id, ContextStore(directory, session_id))


@router.put("/{session_id}")
def update_context(session_id: str, request: ContextUpdateRequest) -> ContextResponse:
    """Записывает следующую revision при совпавшей ожидаемой revision."""
    directory = session_directory(session_id)
    store = ContextStore(directory, session_id)
    current = store.load().snapshot or ContextSnapshot.empty(session_id)
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    fields = (
        current.fields
        if request.fields is None
        else {key: ContextField(**value.model_dump()) for key, value in request.fields.items()}
    )
    snapshot = replace(
        current,
        revision=current.revision + 1,
        fields=fields,
        tags=current.tags if request.tags is None else request.tags,
        notes=current.notes if request.notes is None else request.notes,
    )
    changed = tuple(
        key
        for key, changed_value in (
            ("fields", request.fields),
            ("tags", request.tags),
            ("notes", request.notes),
        )
        if changed_value is not None
    )
    try:
        store.update(
            ContextUpdate(
                expected_revision=request.expected_revision,
                snapshot=snapshot,
                actor="lnt.api",
                changed_keys=changed,
                occurred_at=now,
                event_id=uuid.uuid4().hex,
            )
        )
    except ContextConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": str(error), "current_revision": error.actual_revision},
        ) from error
    except InputError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return _response(session_id, store)


@router.get("/{session_id}/history")
def context_history(session_id: str) -> ContextHistoryResponse:
    """Возвращает аудит revisions из проверенной event chain."""
    directory = session_directory(session_id)
    events = read_event_history(directory / "context.events.jsonl", session_id)
    return ContextHistoryResponse(
        items=tuple(
            ContextHistoryItem(
                revision=event.new_revision,
                occurred_at=event.occurred_at,
                actor=event.actor,
                changed_keys=event.changed_keys,
            )
            for event in events
        )
    )
