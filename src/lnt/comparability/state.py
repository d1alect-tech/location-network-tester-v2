"""Append-only inclusion state для experiment-member и standalone pair."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from lnt.context.lock import session_writer_lock

from .qc import InclusionState

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class StateRevision:
    """Одна аудит-запись явного решения участника."""

    revision: int
    state: InclusionState
    actor: str
    reason: str
    undo_of_revision: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberInclusion:
    """Полная append-only история одного участника."""

    member_id: str
    history: tuple[StateRevision, ...]

    @classmethod
    def proposed(cls, *, member_id: str, actor: str, reason: str) -> MemberInclusion:
        """Создаёт первую proposed revision."""
        return cls(
            member_id=member_id,
            history=(
                StateRevision(
                    revision=1, state=InclusionState.PROPOSED, actor=actor, reason=reason
                ),
            ),
        )

    @property
    def current(self) -> StateRevision:
        """Возвращает последнее аудит-решение."""
        return self.history[-1]

    def transition(self, *, state: InclusionState, actor: str, reason: str) -> MemberInclusion:
        """Добавляет только явный переход с actor/reason."""
        return MemberInclusion(
            member_id=self.member_id,
            history=(
                *self.history,
                StateRevision(
                    revision=self.current.revision + 1,
                    state=state,
                    actor=actor,
                    reason=reason,
                ),
            ),
        )

    def undo(self, *, actor: str, reason: str) -> MemberInclusion:
        """Добавляет компенсационную revision, не удаляя исходное решение."""
        previous = self.history[-2]
        return MemberInclusion(
            member_id=self.member_id,
            history=(
                *self.history,
                StateRevision(
                    revision=self.current.revision + 1,
                    state=previous.state,
                    actor=actor,
                    reason=reason,
                    undo_of_revision=self.current.revision,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class StateConflictError(Exception):
    """Optimistic revision устарела."""

    expected_revision: int
    actual_revision: int

    @override
    def __str__(self) -> str:
        """Возвращает русское описание конфликта."""
        return (
            f"конфликт inclusion revision: ожидалась {self.expected_revision}, "
            f"текущая {self.actual_revision}"
        )


class MemberStateStore:
    """Один storage pattern для experiment member и standalone pair scope."""

    def __init__(self, root: Path, *, scope_id: str) -> None:
        """Связывает scope с отдельным append-only каталогом."""
        self._directory: Path = root / scope_id / "member-qc"
        self._lock_path: Path = self._directory / ".writer.lock"

    def save(self, member: MemberInclusion, *, expected_revision: int) -> MemberInclusion:
        """Дописывает только новые revisions под optimistic lock."""
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{member.member_id}.events.jsonl"
        with session_writer_lock(self._lock_path):
            current = self._read(path, member.member_id)
            actual = 0 if current is None else current.current.revision
            if actual != expected_revision:
                raise StateConflictError(expected_revision, actual)
            additions = member.history[actual:]
            if not additions or additions[0].revision != actual + 1:
                raise StateConflictError(expected_revision, actual)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                for revision in additions:
                    stream.write(
                        json.dumps(
                            _to_mapping(member.member_id, revision),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
                stream.flush()
                os.fsync(stream.fileno())
        return member

    def load(self, member_id: str) -> MemberInclusion:
        """Материализует участника из канонического журнала."""
        member = self._read(self._directory / f"{member_id}.events.jsonl", member_id)
        if member is None:
            raise FileNotFoundError(member_id)
        return member

    def history(self, member_id: str) -> tuple[StateRevision, ...]:
        """Возвращает все revisions для аудита."""
        return self.load(member_id).history

    def transition(
        self,
        *,
        member_id: str,
        state: InclusionState,
        actor: str,
        reason: str,
        expected_revision: int,
    ) -> MemberInclusion:
        """Явно меняет состояние через append-only save."""
        updated = self.load(member_id).transition(state=state, actor=actor, reason=reason)
        return self.save(updated, expected_revision=expected_revision)

    def undo(
        self,
        *,
        member_id: str,
        actor: str,
        reason: str,
        expected_revision: int,
    ) -> MemberInclusion:
        """Явно компенсирует последний переход."""
        updated = self.load(member_id).undo(actor=actor, reason=reason)
        return self.save(updated, expected_revision=expected_revision)

    @staticmethod
    def _read(path: Path, member_id: str) -> MemberInclusion | None:
        if not path.is_file():
            return None
        revisions: list[StateRevision] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = json.loads(line)
            revisions.append(
                StateRevision(
                    revision=int(raw["revision"]),
                    state=InclusionState(str(raw["state"])),
                    actor=str(raw["actor"]),
                    reason=str(raw["reason"]),
                    undo_of_revision=(
                        int(raw["undo_of_revision"])
                        if raw["undo_of_revision"] is not None
                        else None
                    ),
                )
            )
        return MemberInclusion(member_id=member_id, history=tuple(revisions))


def _to_mapping(member_id: str, revision: StateRevision) -> dict[str, str | int | None]:
    return {
        "member_id": member_id,
        "revision": revision.revision,
        "state": revision.state.value,
        "actor": revision.actor,
        "reason": revision.reason,
        "undo_of_revision": revision.undo_of_revision,
    }
