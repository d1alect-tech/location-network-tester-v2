"""Атомарное хранилище неизменяемой истории профилей."""

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import override

from lnt.app_paths import resolve_app_paths
from lnt.errors import InputError
from lnt.profiles.model import ProfileData, ProfileId, ProfileSnapshot
from lnt.profiles.schema import parse_profile_id, profile_from_json, profile_kind, profile_to_json


@dataclass(frozen=True, slots=True)
class ProfileWriteError(InputError):
    """Ожидаемая ошибка атомарной записи профиля."""

    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        return f"не удалось записать профиль {self.path}: {self.reason}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ProfileStore:
    """CRUD поверх отдельных неизменяемых файлов ревизий."""

    def __init__(self, root: Path | None = None, clock: Callable[[], str] = _utc_now) -> None:
        """Связывает store с явным либо app-support корнем."""
        self._root: Path = root or resolve_app_paths().support_dir / "profiles"
        self._clock: Callable[[], str] = clock

    def create(self, profile_id: str, data: ProfileData) -> ProfileSnapshot:
        """Создаёт первую ревизию ранее неизвестного профиля."""
        parsed_id = parse_profile_id(profile_id)
        if self._revision_paths(parsed_id):
            raise InputError(f"профиль {profile_id!r} уже существует")
        return self._write(parsed_id, data, revision=1)

    def update(self, profile_id: str, data: ProfileData) -> ProfileSnapshot:
        """Добавляет новую ревизию, не изменяя старые файлы."""
        parsed_id = parse_profile_id(profile_id)
        history = self.history(profile_id)
        if not history:
            raise InputError(f"профиль {profile_id!r} не найден")
        if history[-1].kind is not profile_kind(data):
            raise InputError("профиль: kind нельзя менять между ревизиями")
        return self._write(parsed_id, data, revision=history[-1].revision + 1)

    def get(self, profile_id: str) -> ProfileSnapshot:
        """Возвращает последнюю активную ревизию."""
        parsed_id = parse_profile_id(profile_id)
        if self._deleted_path(parsed_id).exists():
            raise InputError(f"профиль {profile_id!r} удалён")
        history = self.history(profile_id)
        if not history:
            raise InputError(f"профиль {profile_id!r} не найден")
        return history[-1]

    def history(self, profile_id: str) -> tuple[ProfileSnapshot, ...]:
        """Читает полную историю в порядке ревизий."""
        parsed_id = parse_profile_id(profile_id)
        return tuple(
            profile_from_json(path.read_text(encoding="utf-8"))
            for path in self._revision_paths(parsed_id)
        )

    def list(self) -> tuple[ProfileSnapshot, ...]:
        """Перечисляет последние ревизии активных профилей."""
        if not self._root.is_dir():
            return ()
        result: list[ProfileSnapshot] = []
        for directory in sorted(path for path in self._root.iterdir() if path.is_dir()):
            parsed_id = parse_profile_id(directory.name)
            if not self._deleted_path(parsed_id).exists():
                revisions = self._revision_paths(parsed_id)
                if revisions:
                    result.append(profile_from_json(revisions[-1].read_text(encoding="utf-8")))
        return tuple(result)

    def delete(self, profile_id: str) -> None:
        """Скрывает профиль маркером, сохраняя исторические snapshots."""
        snapshot = self.get(profile_id)
        marker = self._deleted_path(snapshot.profile_id)
        self._atomic_write(marker, self._clock() + "\n")

    def _write(self, profile_id: ProfileId, data: ProfileData, *, revision: int) -> ProfileSnapshot:
        snapshot = ProfileSnapshot(
            schema_version=1,
            profile_id=profile_id,
            kind=profile_kind(data),
            revision=revision,
            captured_at=self._clock(),
            data=data,
        )
        self._atomic_write(
            self._directory(profile_id) / f"revision-{revision:06d}.json", profile_to_json(snapshot)
        )
        return snapshot

    def _atomic_write(self, path: Path, payload: str) -> None:
        temporary = path.with_name(f".{path.name}.partial-{uuid.uuid4().hex[:8]}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)  # noqa: PTH105 - патчируемый атомарный seam
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ProfileWriteError(path=path, reason=str(error)) from error

    def _directory(self, profile_id: ProfileId) -> Path:
        return self._root / profile_id

    def _deleted_path(self, profile_id: ProfileId) -> Path:
        return self._directory(profile_id) / ".deleted"

    def _revision_paths(self, profile_id: ProfileId) -> tuple[Path, ...]:
        return tuple(sorted(self._directory(profile_id).glob("revision-*.json")))
