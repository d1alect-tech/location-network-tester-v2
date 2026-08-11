"""Хеш-цепочка канонического append-only журнала контекста."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from lnt.context.json_codec import JsonValue, decode_object, encode_canonical
from lnt.context.schema import context_from_mapping, context_to_mapping
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from lnt.context.model import ContextSnapshot

_EVENT_FIELDS: Final = frozenset(
    {
        "event_schema_version",
        "event_id",
        "session_id",
        "occurred_at",
        "event_kind",
        "actor",
        "old_revision",
        "new_revision",
        "changed_keys",
        "snapshot",
        "prev_hash",
        "content_hash",
    }
)


class ContextChainError(InputError):
    """Журнал контекста повреждён или нарушает хеш-цепочку."""

    def __init__(self, reason_code: str, detail: str) -> None:
        """Сохраняет стабильный reason code и локализованную деталь."""
        super().__init__(f"context.events.jsonl: {detail}")
        self.reason_code: str = reason_code


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextEvent:
    """Полный replayable snapshot и его аудит-метаданные."""

    event_id: str
    session_id: str
    occurred_at: str
    actor: str
    old_revision: int
    new_revision: int
    changed_keys: tuple[str, ...]
    snapshot: ContextSnapshot
    prev_hash: str
    content_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EventVerification:
    """Результат строгой проверки журнала от genesis."""

    snapshot: ContextSnapshot | None
    event_count: int
    last_hash: str
    torn_tail: bool


def genesis_hash(session_id: str) -> str:
    """Возвращает session-bound genesis SHA-256."""
    return hashlib.sha256(f"lnt-context-genesis:{session_id}".encode()).hexdigest()


def build_event(event: ContextEvent) -> ContextEvent:
    """Создаёт событие полного результирующего snapshot."""
    unsigned = _unsigned_mapping(
        event,
    )
    digest = hashlib.sha256(encode_canonical(unsigned, "context event")).hexdigest()
    return replace(event, content_hash=digest)


def append_event(path: Path, event: ContextEvent) -> None:
    """Дописывает, flush и fsync одного полного JSONL-события."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = encode_canonical(event_to_mapping(event), "context event") + b"\n"
    with path.open("ab") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def verify_event_log(path: Path, session_id: str) -> EventVerification:
    """Проверяет журнал от genesis, игнорируя лишь рваную последнюю строку."""
    if not path.is_file():
        return EventVerification(
            snapshot=None,
            event_count=0,
            last_hash=genesis_hash(session_id),
            torn_tail=False,
        )
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ContextChainError("context_events_unreadable", str(error)) from error
    complete, tail = _split_complete_lines(data)
    previous = genesis_hash(session_id)
    snapshot: ContextSnapshot | None = None
    for index, line in enumerate(complete, start=1):
        event = _parse_line(line, index)
        _verify_event(event, session_id, previous, snapshot)
        previous = event.content_hash
        snapshot = event.snapshot
    return EventVerification(
        snapshot=snapshot,
        event_count=len(complete),
        last_hash=previous,
        torn_tail=bool(tail),
    )


def event_to_mapping(event: ContextEvent) -> dict[str, JsonValue]:
    """Переводит событие в persistable JSON-mapping."""
    mapping = _unsigned_mapping(event)
    mapping["content_hash"] = event.content_hash
    return mapping


def _unsigned_mapping(event: ContextEvent) -> dict[str, JsonValue]:
    return {
        "event_schema_version": 1,
        "event_id": event.event_id,
        "session_id": event.snapshot.session_id,
        "occurred_at": event.occurred_at,
        "event_kind": "context_snapshot",
        "actor": event.actor,
        "old_revision": event.snapshot.revision - 1,
        "new_revision": event.snapshot.revision,
        "changed_keys": list(event.changed_keys),
        "snapshot": context_to_mapping(event.snapshot),
        "prev_hash": event.prev_hash,
    }


def _parse_line(line: bytes, index: int) -> ContextEvent:
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContextChainError("context_events_corrupt", f"строка {index}: не UTF-8") from error
    try:
        raw = decode_object(text, f"context.events.jsonl строка {index}")
        return _event_from_mapping(raw)
    except InputError as error:
        raise ContextChainError("context_events_corrupt", f"строка {index}: {error}") from error


def _event_from_mapping(raw: Mapping[str, JsonValue]) -> ContextEvent:
    unknown = set(raw) - _EVENT_FIELDS
    missing = _EVENT_FIELDS - set(raw)
    if unknown or missing:
        raise InputError("context event: неверный набор полей")
    if (
        _integer(raw, "event_schema_version") != 1
        or _string(raw, "event_kind") != "context_snapshot"
    ):
        raise InputError("context event: неподдерживаемая версия или kind")
    changed = raw["changed_keys"]
    snapshot_raw = raw["snapshot"]
    if not isinstance(changed, list) or not isinstance(snapshot_raw, dict):
        raise InputError("context event: неверный payload")
    return ContextEvent(
        event_id=_string(raw, "event_id"),
        session_id=_string(raw, "session_id"),
        occurred_at=_string(raw, "occurred_at"),
        actor=_string(raw, "actor"),
        old_revision=_integer(raw, "old_revision"),
        new_revision=_integer(raw, "new_revision"),
        changed_keys=tuple(_json_string(item, "changed_keys") for item in changed),
        snapshot=context_from_mapping(snapshot_raw),
        prev_hash=_string(raw, "prev_hash"),
        content_hash=_string(raw, "content_hash"),
    )


def _verify_event(
    event: ContextEvent,
    session_id: str,
    previous_hash: str,
    previous_snapshot: ContextSnapshot | None,
) -> None:
    expected_old = 0 if previous_snapshot is None else previous_snapshot.revision
    unsigned = event_to_mapping(event)
    del unsigned["content_hash"]
    expected_hash = hashlib.sha256(encode_canonical(unsigned, "context event")).hexdigest()
    valid = (
        event.session_id == session_id
        and event.snapshot.session_id == session_id
        and event.prev_hash == previous_hash
        and event.old_revision == expected_old
        and event.new_revision == expected_old + 1
        and event.snapshot.revision == event.new_revision
        and event.content_hash == expected_hash
    )
    if not valid:
        raise ContextChainError("context_events_chain_invalid", "нарушена хеш-цепочка")


def _split_complete_lines(data: bytes) -> tuple[list[bytes], bytes]:
    if not data:
        return [], b""
    parts = data.split(b"\n")
    if data.endswith(b"\n"):
        return parts[:-1], b""
    return parts[:-1], parts[-1]


def _string(raw: Mapping[str, JsonValue], key: str) -> str:
    return _json_string(raw[key], key)


def _json_string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str):
        raise InputError(f"context event: {label} должен быть строкой")
    return value


def _integer(raw: Mapping[str, JsonValue], key: str) -> int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"context event: {key} должен быть целым")
    return value
