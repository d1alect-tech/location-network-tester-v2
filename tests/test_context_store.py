from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from lnt.context.events import ContextChainError, verify_event_log
from lnt.context.model import (
    CollectionStatus,
    ContextField,
    ContextSnapshot,
    FieldKind,
    FieldSource,
)
from lnt.context.store import ContextConflictError, ContextStore, ContextUpdate


def _field(value: str) -> ContextField:
    return ContextField(
        kind=FieldKind.STRING,
        value=value,
        unit=None,
        uncertainty=None,
        source=FieldSource.USER,
        collection_status=CollectionStatus.COLLECTED,
        collection_reason=None,
        captured_at="2026-08-11T10:00:00.000Z",
    )


def _update(snapshot: ContextSnapshot, expected: int, *, actor: str = "tester") -> ContextUpdate:
    return ContextUpdate(
        expected_revision=expected,
        snapshot=snapshot,
        actor=actor,
        changed_keys=("site.name",),
        occurred_at="2026-08-11T10:01:00.000Z",
        event_id=f"event-{expected + 1}",
    )


def test_absent_sidecars_return_explicit_empty_view(tmp_path: Path) -> None:
    view = ContextStore(tmp_path, "session-A").load()

    assert view.snapshot is None
    assert view.health == "context_absent"
    assert view.reason_codes == ()


def test_update_verifies_chain_from_session_genesis(tmp_path: Path) -> None:
    store = ContextStore(tmp_path, "session-A")
    snapshot = ContextSnapshot.empty("session-A").next_revision(
        fields={"site.name": _field("lab")},
    )

    actual = store.update(_update(snapshot, 0))
    verification = verify_event_log(tmp_path / "context.events.jsonl", "session-A")

    assert actual.revision == 1
    assert verification.snapshot == snapshot
    assert verification.event_count == 1


def test_update_rejects_stale_expected_revision(tmp_path: Path) -> None:
    store = ContextStore(tmp_path, "session-A")
    first = ContextSnapshot.empty("session-A").next_revision(fields={"site.name": _field("a")})
    store.update(_update(first, 0))
    stale = first.next_revision(fields={"site.name": _field("b")})

    with pytest.raises(ContextConflictError) as caught:
        store.update(_update(stale, 0))

    assert caught.value.actual_revision == 1


def test_load_replays_flushed_event_after_cache_replace_crash(tmp_path: Path) -> None:
    store = ContextStore(tmp_path, "session-A")
    snapshot = ContextSnapshot.empty("session-A").next_revision(
        fields={"site.name": _field("committed")},
    )

    with pytest.raises(RuntimeError, match="injected crash"):
        store.update(
            _update(snapshot, 0),
            after_event_flush=lambda: (_ for _ in ()).throw(RuntimeError("injected crash")),
        )
    actual = store.load()

    assert actual.snapshot == snapshot
    assert actual.health == "context_valid"
    assert (tmp_path / "context.json").is_file()


def test_torn_final_line_is_ignored_and_reason_coded(tmp_path: Path) -> None:
    store = ContextStore(tmp_path, "session-A")
    snapshot = ContextSnapshot.empty("session-A").next_revision(fields={"site.name": _field("lab")})
    store.update(_update(snapshot, 0))
    events = tmp_path / "context.events.jsonl"
    with events.open("ab") as stream:
        stream.write(b'{"event_schema_version":1')
        stream.flush()
        os.fsync(stream.fileno())

    actual = store.load()

    assert actual.snapshot == snapshot
    assert actual.health == "context_valid"
    assert actual.reason_codes == ("context_events_torn_tail",)


def test_interior_tamper_fails_without_rewriting_event_log(tmp_path: Path) -> None:
    store = ContextStore(tmp_path, "session-A")
    first = ContextSnapshot.empty("session-A").next_revision(fields={"site.name": _field("alpha")})
    store.update(_update(first, 0))
    second = first.next_revision(fields={"site.name": _field("beta")})
    store.update(_update(second, 1))
    events = tmp_path / "context.events.jsonl"
    tampered = events.read_bytes().replace(b"alpha", b"omega", 1)
    events.write_bytes(tampered)
    before_bytes = events.read_bytes()
    before_mtime = events.stat().st_mtime_ns

    with pytest.raises(ContextChainError):
        store.load()

    assert events.read_bytes() == before_bytes
    assert events.stat().st_mtime_ns == before_mtime


def test_malformed_cache_keeps_session_readable_with_invalid_health(tmp_path: Path) -> None:
    (tmp_path / "context.json").write_text("{broken", encoding="utf-8")

    actual = ContextStore(tmp_path, "session-A").load()

    assert actual.snapshot is None
    assert actual.health == "context_invalid"
    assert actual.reason_codes == ("context_cache_malformed",)
