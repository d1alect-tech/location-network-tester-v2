"""Durable append-only storage for protocol runner boundaries."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from lnt.experiments.runner_models import ProtocolRunEvent, ProtocolRunRecord

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProtocolRunPersistenceError(Exception):
    """A persisted event sequence or revision is inconsistent."""

    detail: str

    @override
    def __str__(self) -> str:
        return f"хранилище запуска протокола: {self.detail}"


class ProtocolRunStore:
    """Stores one atomic snapshot and an fsynced event for every transition."""

    def __init__(self, root: Path) -> None:
        """Bind storage to its explicit application-owned root."""
        self.root: Path = root

    def create(self, record: ProtocolRunRecord) -> ProtocolRunRecord:
        """Persist the initial run boundary."""
        directory = self.root / record.run_id
        if (directory / "run.json").exists():
            raise FileExistsError(record.run_id)
        directory.mkdir(parents=True, exist_ok=False)
        self._append(
            directory,
            ProtocolRunEvent(
                revision=record.revision, transition="run_created", actor="system", snapshot=record
            ),
        )
        self._replace(directory / "run.json", record)
        return record

    def load(self, run_id: str) -> ProtocolRunRecord:
        """Load the exact latest step boundary."""
        return ProtocolRunRecord.model_validate_json(
            (self.root / run_id / "run.json").read_text(encoding="utf-8")
        )

    def record(
        self, record: ProtocolRunRecord, *, transition: str, actor: str = "system"
    ) -> ProtocolRunRecord:
        """Append the next monotonic transition then replace the cache."""
        current = self.load(record.run_id)
        if record.revision != current.revision + 1:
            raise ProtocolRunPersistenceError("revision не является следующей")
        directory = self.root / record.run_id
        self._append(
            directory,
            ProtocolRunEvent(
                revision=record.revision, transition=transition, actor=actor, snapshot=record
            ),
        )
        self._replace(directory / "run.json", record)
        return record

    def events(self, run_id: str) -> tuple[ProtocolRunEvent, ...]:
        """Read the verified monotonic event sequence."""
        path = self.root / run_id / "run.events.jsonl"
        events = tuple(
            ProtocolRunEvent.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        if [event.revision for event in events] != list(range(1, len(events) + 1)):
            raise ProtocolRunPersistenceError("журнал событий повреждён")
        return events

    @staticmethod
    def _append(directory: Path, event: ProtocolRunEvent) -> None:
        payload = event.model_dump_json() + "\n"
        with (directory / "run.events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _replace(path: Path, record: ProtocolRunRecord) -> None:
        temporary = path.with_name(f".{path.name}.partial-{uuid.uuid4().hex[:8]}")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(record.model_dump_json())
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)  # noqa: PTH105 - atomic persistence seam
        finally:
            temporary.unlink(missing_ok=True)
