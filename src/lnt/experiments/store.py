"""Каноническое sibling-хранилище экспериментов."""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from lnt.context.json_codec import decode_object
from lnt.context.lock import session_writer_lock
from lnt.experiments.errors import ExperimentConflictError
from lnt.experiments.events import (
    ExperimentEvent,
    append_event,
    build_event,
    genesis_hash,
    read_events,
)
from lnt.experiments.model import Experiment, experiment_from_mapping, experiment_to_canonical_json
from lnt.experiments.values import Member


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedMember:
    """Членство с видимым состоянием ссылки."""

    member: Member
    health: str
    resolved_path: Path | None


class ExperimentStore:
    """Сохраняет эксперименты рядом, но не внутри session root."""

    def __init__(self, session_root: Path) -> None:
        """Разрешает experiment root как sibling переданного session root."""
        self._session_root: Path = session_root
        self._root: Path = session_root.parent / "experiments"

    @property
    def root(self) -> Path:
        """Возвращает принадлежащую subsystem sibling-область."""
        return self._root

    def save(self, experiment: Experiment, *, expected_revision: int) -> Experiment:
        """Атомарно принимает следующую optimistic revision."""
        directory = self._root / experiment.experiment_id
        events_path = directory / "experiment.events.jsonl"
        directory.mkdir(parents=True, exist_ok=True)
        with session_writer_lock(directory / ".experiment.writer.lock"):
            history = read_events(events_path, experiment.experiment_id)
            actual_revision = len(history)
            if expected_revision != actual_revision:
                raise ExperimentConflictError(expected_revision, actual_revision)
            if experiment.revision != actual_revision + 1:
                raise ExperimentConflictError(experiment.revision - 1, actual_revision)
            previous = (
                genesis_hash(experiment.experiment_id) if not history else history[-1].content_hash
            )
            append_event(
                events_path,
                build_event(
                    ExperimentEvent(
                        experiment_id=experiment.experiment_id,
                        revision=experiment.revision,
                        snapshot=experiment,
                        prev_hash=previous,
                        content_hash="",
                    )
                ),
            )
            self._replace_snapshot(directory / "experiment.json", experiment)
        return experiment

    def load(self, experiment_id: str) -> Experiment:
        """Возвращает verified последний snapshot."""
        events = read_events(
            self._root / experiment_id / "experiment.events.jsonl",
            experiment_id,
        )
        if events:
            return events[-1].snapshot
        path = self._root / experiment_id / "experiment.json"
        return experiment_from_mapping(
            decode_object(path.read_text(encoding="utf-8"), "experiment.json")
        )

    def history(self, experiment_id: str) -> tuple[Experiment, ...]:
        """Возвращает immutable snapshots в порядке revision."""
        return tuple(
            event.snapshot
            for event in read_events(
                self._root / experiment_id / "experiment.events.jsonl",
                experiment_id,
            )
        )

    def resolve_members(self, experiment_id: str) -> tuple[ResolvedMember, ...]:
        """Сохраняет отсутствующие ссылки как broken_reference."""
        experiment = self.load(experiment_id)
        result: list[ResolvedMember] = []
        for member in experiment.members:
            candidate = self._session_root / member.storage_ref
            exists = candidate.is_dir()
            result.append(
                ResolvedMember(
                    member=member,
                    health="ok" if exists else "broken_reference",
                    resolved_path=candidate if exists else None,
                )
            )
        return tuple(result)

    @staticmethod
    def _replace_snapshot(path: Path, experiment: Experiment) -> None:
        temporary = path.with_name(f"experiment.json.partial-{uuid.uuid4().hex[:8]}")
        try:
            with temporary.open("wb") as stream:
                stream.write(experiment_to_canonical_json(experiment))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
