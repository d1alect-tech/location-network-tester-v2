"""Безопасное обнаружение сессий и выбор каталогов для веб-интерфейса."""

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from lnt.errors import InputError
from lnt.manifest import manifest_from_json
from lnt.series import series_dirs
from lnt.types import SessionType

_SESSION_NAME_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_MANIFEST_FILENAME: Final = "manifest.json"
_METRICS_FILENAME: Final = "metrics.json"
_SPECTRUM_FILENAME: Final = "spectrum.csv"
_MAX_AUTO_NAME_ATTEMPTS: Final = 100


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionSummary:
    """Краткие метаданные сессии из manifest.json."""

    session_id: str
    created_utc: str
    source: str
    session_type: str
    profile: str | None
    sample_rate_hz: float
    duration_s: float
    sample_count: int
    label: str | None
    channels: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEntry:
    """Результат безопасного просмотра одного каталога сессии."""

    name: str
    status: Literal["valid", "invalid"]
    error: str | None
    analyzed: bool
    summary: SessionSummary | None


def list_sessions(root: Path) -> tuple[SessionEntry, ...]:
    """Возвращает отсортированные непосредственные сессии без перехода по ссылкам."""
    if not root.is_dir():
        return ()

    entries: list[SessionEntry] = []
    for session_dir in sorted(root.iterdir(), key=lambda path: path.name):
        if session_dir.is_symlink() or not session_dir.is_dir():
            continue
        manifest_path = session_dir / _MANIFEST_FILENAME
        if not manifest_path.is_file():
            continue
        try:
            manifest = manifest_from_json(manifest_path.read_text(encoding="utf-8"))
        except (InputError, UnicodeDecodeError, OSError) as error:
            detail = " ".join(str(error).splitlines())
            entries.append(
                SessionEntry(
                    name=session_dir.name,
                    status="invalid",
                    error=f"ошибка manifest.json: {detail}",
                    analyzed=False,
                    summary=None,
                ),
            )
            continue

        label_value = manifest.parameters.get("label")
        match label_value:
            case str() as label:
                pass
            case int() | float() | None:
                label = None
        has_metrics = (session_dir / _METRICS_FILENAME).is_file()
        needs_spectrum = manifest.session_type is not SessionType.LINE_QUALITY
        entries.append(
            SessionEntry(
                name=session_dir.name,
                status="valid",
                error=None,
                analyzed=has_metrics
                and ((session_dir / _SPECTRUM_FILENAME).is_file() or not needs_spectrum),
                summary=SessionSummary(
                    session_id=manifest.session_id,
                    created_utc=manifest.created_utc,
                    source=manifest.source.value,
                    session_type=manifest.session_type.value,
                    profile=manifest.profile,
                    sample_rate_hz=manifest.sample_rate_hz,
                    duration_s=manifest.duration_s,
                    sample_count=manifest.sample_count,
                    label=label,
                    channels=("dual" if manifest.ch2 is not None else "ch1_only"),
                ),
            ),
        )
    return tuple(entries)


def resolve_session_dir(root: Path, name: str) -> Path:
    """Разрешает существующий реальный каталог сессии внутри ``root``."""
    _validate_session_name(name)
    candidate = root / name
    if candidate.is_symlink() or not candidate.is_dir():
        raise InputError(f"каталог сессии не найден или небезопасен: {name!r}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except OSError as error:
        detail = " ".join(str(error).splitlines())
        raise InputError(f"не удалось проверить каталог сессии {name!r}: {detail}") from error
    if resolved_candidate.parent != resolved_root:
        raise InputError(f"каталог сессии выходит за пределы корня: {name!r}")
    return candidate


def allocate_output_base(
    root: Path,
    *,
    requested: str | None,
    kind: str,
    profile: str | None,
    repeat: int,
) -> Path:
    """Выбирает свободную базу результата, не создавая её на диске."""
    if requested is not None:
        _validate_session_name(requested)
        requested_base = root / requested
        collision = _first_collision(requested_base, repeat)
        if collision is not None:
            raise InputError(f"каталог результата уже существует: {collision}")
        return requested_base

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    if kind == "simulate":
        if profile is None:
            raise InputError("для симуляции требуется профиль")
        auto_name = f"sim-{profile}-{timestamp}"
    elif kind == "capture":
        auto_name = f"cap-{timestamp}"
    else:
        raise InputError(f"неизвестный тип сессии: {kind!r}")
    _validate_session_name(auto_name)

    auto_base = root / auto_name
    if _first_collision(auto_base, repeat) is None:
        return auto_base
    for _attempt in range(_MAX_AUTO_NAME_ATTEMPTS):
        candidate = root / f"{auto_name}-{secrets.token_hex(3)}"
        if _first_collision(candidate, repeat) is None:
            return candidate
    raise InputError("не удалось подобрать свободное имя каталога результата")


def _validate_session_name(name: str) -> None:
    if (
        name in {".", ".."}
        or "/" in name
        or "\\" in name
        or _SESSION_NAME_PATTERN.fullmatch(name) is None
    ):
        raise InputError(f"небезопасное имя каталога сессии: {name!r}")


def _first_collision(base: Path, repeat: int) -> Path | None:
    return next((candidate for candidate in series_dirs(base, repeat) if candidate.exists()), None)
