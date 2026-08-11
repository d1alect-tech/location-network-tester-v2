"""Хранилище контекста: сначала fsync события, затем atomic replace cache.

Это намеренно не двухфайловый атомарный commit: журнал каноничен, а
``context.json`` является восстанавливаемой проекцией.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lnt.context.events import ContextEvent, append_event, build_event, verify_event_log
from lnt.context.lock import session_writer_lock
from lnt.context.schema import context_from_json, context_to_json
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from lnt.context.model import ContextSnapshot


class ContextConflictError(InputError):
    """Ожидаемая revision устарела."""

    def __init__(self, expected_revision: int, actual_revision: int) -> None:
        """Сохраняет ожидаемую и фактическую revision."""
        message = (
            f"конфликт revision контекста: ожидалась {expected_revision}, текущая {actual_revision}"
        )
        super().__init__(
            message,
        )
        self.expected_revision: int = expected_revision
        self.actual_revision: int = actual_revision


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextUpdate:
    """Команда записи уже вычисленного следующего snapshot."""

    expected_revision: int
    snapshot: ContextSnapshot
    actor: str
    changed_keys: tuple[str, ...]
    occurred_at: str
    event_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextView:
    """Читаемый snapshot и машиночитаемое здоровье sidecar."""

    snapshot: ContextSnapshot | None
    health: str
    reason_codes: tuple[str, ...]


class ContextStore:
    """Читает и изменяет только context-sidecars заданной сессии."""

    def __init__(self, session_dir: Path, session_id: str) -> None:
        """Связывает store с каталогом и идентичностью сессии."""
        self._session_dir: Path = session_dir
        self._session_id: str = session_id
        self._cache_path: Path = session_dir / "context.json"
        self._events_path: Path = session_dir / "context.events.jsonl"
        self._lock_path: Path = session_dir / ".context.writer.lock"

    def load(self) -> ContextView:
        """Возвращает replay события либо строгий cache/empty health-view."""
        if self._events_path.is_file():
            verification = verify_event_log(self._events_path, self._session_id)
            snapshot = verification.snapshot
            if snapshot is None:
                return ContextView(snapshot=None, health="context_absent", reason_codes=())
            cache = self._read_cache()
            if cache != snapshot:
                self._replace_cache(snapshot)
            reasons = ("context_events_torn_tail",) if verification.torn_tail else ()
            return ContextView(snapshot=snapshot, health="context_valid", reason_codes=reasons)
        if not self._cache_path.is_file():
            return ContextView(snapshot=None, health="context_absent", reason_codes=())
        try:
            snapshot = context_from_json(self._cache_path.read_text(encoding="utf-8"))
        except (InputError, UnicodeDecodeError, OSError):
            return ContextView(
                snapshot=None,
                health="context_invalid",
                reason_codes=("context_cache_malformed",),
            )
        if snapshot.session_id != self._session_id:
            return ContextView(
                snapshot=None,
                health="context_invalid",
                reason_codes=("context_identity_mismatch",),
            )
        return ContextView(snapshot=snapshot, health="context_valid", reason_codes=())

    def update(
        self,
        update: ContextUpdate,
        *,
        after_event_flush: Callable[[], None] | None = None,
    ) -> ContextSnapshot:
        """Под lock дописывает событие и лишь затем заменяет derived cache."""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        with session_writer_lock(self._lock_path):
            verification = verify_event_log(self._events_path, self._session_id)
            current_revision = (
                0 if verification.snapshot is None else verification.snapshot.revision
            )
            if update.expected_revision != current_revision:
                raise ContextConflictError(update.expected_revision, current_revision)
            snapshot = update.snapshot
            if snapshot.session_id != self._session_id or snapshot.revision != current_revision + 1:
                raise InputError("context update: session_id или новая revision не согласованы")
            event = build_event(
                ContextEvent(
                    event_id=update.event_id,
                    session_id=snapshot.session_id,
                    occurred_at=update.occurred_at,
                    actor=update.actor,
                    old_revision=snapshot.revision - 1,
                    new_revision=snapshot.revision,
                    changed_keys=update.changed_keys,
                    snapshot=snapshot,
                    prev_hash=verification.last_hash,
                    content_hash="",
                )
            )
            append_event(self._events_path, event)
            if after_event_flush is not None:
                after_event_flush()
            self._replace_cache(snapshot)
            return snapshot

    def _read_cache(self) -> ContextSnapshot | None:
        if not self._cache_path.is_file():
            return None
        try:
            return context_from_json(self._cache_path.read_text(encoding="utf-8"))
        except (InputError, UnicodeDecodeError, OSError):
            return None

    def _replace_cache(self, snapshot: ContextSnapshot) -> None:
        partial = self._cache_path.with_name(
            f"context.json.partial-{uuid.uuid4().hex[:8]}",
        )
        try:
            with partial.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(context_to_json(snapshot))
                stream.flush()
                os.fsync(stream.fileno())
            partial.replace(self._cache_path)
        finally:
            partial.unlink(missing_ok=True)
