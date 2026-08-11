"""Канонический snapshot и append-only журнал пользовательских гипотез."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError

from lnt.context.lock import session_writer_lock

from .hypothesis_models import Hypothesis

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.context.json_codec import JsonValue


class HypothesisConflictError(RuntimeError):
    """Отклоняет optimistic conflict или неявную revision."""


@dataclass(frozen=True, slots=True, kw_only=True)
class HypothesisEvent:
    """Одно проверяемое звено append-only журнала."""

    revision: int
    snapshot: Hypothesis
    prev_hash: str
    content_hash: str


class HypothesisStore:
    """Хранит ledger как reconcile-visible sibling sessions root."""

    def __init__(self, session_root: Path) -> None:
        """Разрешает hypothesis root как sibling переданного session root."""
        self._root: Path = session_root.parent / "hypotheses"

    @property
    def root(self) -> Path:
        """Возвращает отдельную от sessions область ledger."""
        return self._root

    def save(self, hypothesis: Hypothesis, *, expected_revision: int) -> Hypothesis:
        """Принимает только следующую явно подписанную user revision."""
        directory = self._root / hypothesis.hypothesis_id
        events_path = directory / "hypothesis.events.jsonl"
        directory.mkdir(parents=True, exist_ok=True)
        with session_writer_lock(directory / ".hypothesis.writer.lock"):
            history = self.history(hypothesis.hypothesis_id)
            actual = len(history)
            explicit = len(hypothesis.revision_history) == hypothesis.revision
            if expected_revision != actual or hypothesis.revision != actual + 1 or not explicit:
                raise HypothesisConflictError("revision_history conflict")
            previous = _genesis(hypothesis.hypothesis_id)
            if events_path.is_file():
                previous = _read_events(events_path, hypothesis.hypothesis_id)[-1].content_hash
            event = _build_event(hypothesis, previous)
            with events_path.open("ab") as stream:
                stream.write(_canonical(_event_mapping(event)) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._replace(directory / "hypothesis.json", hypothesis)
        return hypothesis

    def load(self, hypothesis_id: str) -> Hypothesis:
        """Возвращает последний проверенный snapshot."""
        events = _read_events(self._root / hypothesis_id / "hypothesis.events.jsonl", hypothesis_id)
        if not events:
            raise KeyError(hypothesis_id)
        return events[-1].snapshot

    def history(self, hypothesis_id: str) -> tuple[Hypothesis, ...]:
        """Возвращает все неизменяемые revisions."""
        return tuple(
            event.snapshot
            for event in _read_events(
                self._root / hypothesis_id / "hypothesis.events.jsonl", hypothesis_id
            )
        )

    @staticmethod
    def _replace(path: Path, hypothesis: Hypothesis) -> None:
        temporary = path.with_name(f"hypothesis.json.partial-{uuid.uuid4().hex[:8]}")
        try:
            with temporary.open("wb") as stream:
                stream.write(_canonical(hypothesis.model_dump(mode="json")))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _canonical(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _genesis(hypothesis_id: str) -> str:
    return hashlib.sha256(f"lnt:hypothesis:{hypothesis_id}:genesis".encode()).hexdigest()


def _unsigned(hypothesis: Hypothesis, previous: str) -> dict[str, JsonValue]:
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "revision": hypothesis.revision,
        "snapshot": hypothesis.model_dump(mode="json"),
        "prev_hash": previous,
    }


def _build_event(hypothesis: Hypothesis, previous: str) -> HypothesisEvent:
    digest = hashlib.sha256(_canonical(_unsigned(hypothesis, previous))).hexdigest()
    return HypothesisEvent(
        revision=hypothesis.revision,
        snapshot=hypothesis,
        prev_hash=previous,
        content_hash=digest,
    )


def _event_mapping(event: HypothesisEvent) -> dict[str, JsonValue]:
    return {**_unsigned(event.snapshot, event.prev_hash), "content_hash": event.content_hash}


def _read_events(path: Path, hypothesis_id: str) -> tuple[HypothesisEvent, ...]:
    if not path.is_file():
        return ()
    previous = _genesis(hypothesis_id)
    events: list[HypothesisEvent] = []
    for ordinal, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            raw = json.loads(line)
            snapshot = Hypothesis.model_validate(raw["snapshot"])
            event = HypothesisEvent(
                revision=int(raw["revision"]),
                snapshot=snapshot,
                prev_hash=str(raw["prev_hash"]),
                content_hash=str(raw["content_hash"]),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise HypothesisConflictError("invalid hypothesis event") from error
        expected = _build_event(snapshot, previous)
        valid = (
            event.revision == ordinal
            and snapshot.hypothesis_id == hypothesis_id
            and event.prev_hash == previous
            and event.content_hash == expected.content_hash
        )
        if not valid:
            raise HypothesisConflictError("invalid hypothesis event chain")
        events.append(event)
        previous = event.content_hash
    return tuple(events)
