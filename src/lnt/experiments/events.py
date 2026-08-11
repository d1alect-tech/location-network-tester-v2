"""Append-only SHA-256 цепочка revisions эксперимента."""

import hashlib
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from lnt.context.json_codec import JsonValue, decode_object, encode_canonical
from lnt.context.parsing import as_mapping, integer, string
from lnt.experiments.errors import ExperimentChainError, ExperimentValidationError
from lnt.experiments.model import Experiment, experiment_from_mapping

_EVENT_FIELDS: Final = frozenset(
    {"event_schema_version", "experiment_id", "revision", "snapshot", "prev_hash", "content_hash"}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentEvent:
    """Полный snapshot одной revision и звено цепочки."""

    experiment_id: str
    revision: int
    snapshot: Experiment
    prev_hash: str
    content_hash: str


def genesis_hash(experiment_id: str) -> str:
    """Возвращает experiment-bound genesis digest."""
    return hashlib.sha256(f"lnt-experiment-genesis:{experiment_id}".encode()).hexdigest()


def event_to_mapping(event: ExperimentEvent, *, signed: bool = True) -> dict[str, JsonValue]:
    """Переводит событие в persistable mapping."""
    result: dict[str, JsonValue] = {
        "event_schema_version": 1,
        "experiment_id": event.experiment_id,
        "revision": event.revision,
        "snapshot": event.snapshot.to_mapping(),
        "prev_hash": event.prev_hash,
    }
    if signed:
        result["content_hash"] = event.content_hash
    return result


def build_event(event: ExperimentEvent) -> ExperimentEvent:
    """Вычисляет content hash канонического unsigned события."""
    digest = hashlib.sha256(
        encode_canonical(event_to_mapping(event, signed=False), "experiment event")
    ).hexdigest()
    return replace(event, content_hash=digest)


def append_event(path: Path, event: ExperimentEvent) -> None:
    """Надёжно дописывает одну завершённую JSONL-строку."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = encode_canonical(event_to_mapping(event), "experiment event") + b"\n"
    with path.open("ab") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def read_events(path: Path, experiment_id: str) -> tuple[ExperimentEvent, ...]:
    """Проверяет журнал от genesis и возвращает revisions."""
    if not path.is_file():
        return ()
    try:
        lines = path.read_bytes().splitlines()
    except OSError as error:
        raise ExperimentChainError("experiment_events_unreadable", str(error)) from error
    previous = genesis_hash(experiment_id)
    events: list[ExperimentEvent] = []
    for ordinal, line in enumerate(lines, start=1):
        event = _parse_event(line, ordinal)
        expected_hash = hashlib.sha256(
            encode_canonical(event_to_mapping(event, signed=False), "experiment event")
        ).hexdigest()
        valid = (
            event.experiment_id == experiment_id
            and event.snapshot.experiment_id == experiment_id
            and event.revision == ordinal
            and event.snapshot.revision == ordinal
            and event.prev_hash == previous
            and event.content_hash == expected_hash
        )
        if not valid:
            raise ExperimentChainError("experiment_events_chain_invalid", "нарушена хеш-цепочка")
        events.append(event)
        previous = event.content_hash
    return tuple(events)


def _parse_event(line: bytes, ordinal: int) -> ExperimentEvent:
    try:
        raw = decode_object(line.decode("utf-8"), f"experiment.events строка {ordinal}")
        if frozenset(raw) != _EVENT_FIELDS or integer(raw, "event_schema_version", "event") != 1:
            _raise_invalid_event("неверный набор полей события")
        snapshot = as_mapping(raw["snapshot"], "event.snapshot")
        experiment_id = string(raw, "experiment_id", "event")
        revision = integer(raw, "revision", "event")
        prev_hash = string(raw, "prev_hash", "event")
        content_hash = string(raw, "content_hash", "event")
        return ExperimentEvent(
            experiment_id=experiment_id,
            revision=revision,
            snapshot=experiment_from_mapping(snapshot),
            prev_hash=prev_hash,
            content_hash=content_hash,
        )
    except (UnicodeDecodeError, ExperimentValidationError) as error:
        raise ExperimentChainError(
            "experiment_events_corrupt", f"строка {ordinal}: {error}"
        ) from error


def _raise_invalid_event(detail: str) -> None:
    raise ExperimentValidationError("experiment_event_invalid", detail)
