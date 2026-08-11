"""Детерминированные пути данных приложения LNT для Windows."""

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class PathResolutionNote(StrEnum):
    """Машиночитаемая причина применения резервного базового каталога."""

    APPDATA_FALLBACK = "appdata_fallback"
    LOCALAPPDATA_FALLBACK = "localappdata_fallback"


@dataclass(frozen=True, slots=True, kw_only=True)
class AppPathOverrides:
    """Явные базовые пути для тестов и внешних интерфейсов."""

    home: Path | None = None
    roaming_base: Path | None = None
    local_base: Path | None = None
    session_root: Path | None = None
    test_root: Path | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AppPaths:
    """Все постоянные и одноразовые пути приложения."""

    config_path: Path
    catalog_db: Path
    runtime_db: Path
    cache_dir: Path
    log_dir: Path
    support_dir: Path
    session_root: Path
    notes: tuple[PathResolutionNote, ...]


def resolve_app_paths(overrides: AppPathOverrides | None = None) -> AppPaths:
    """Разрешает пути один раз, поддерживая явную изоляцию тестового корня."""
    selected = overrides or AppPathOverrides()
    if selected.test_root is not None:
        home = selected.test_root / "home"
        roaming_base = selected.test_root / "roaming"
        local_base = selected.test_root / "local"
        notes: tuple[PathResolutionNote, ...] = ()
    else:
        home = selected.home or Path.home()
        appdata = os.environ.get("APPDATA")
        localappdata = os.environ.get("LOCALAPPDATA")
        roaming_base = selected.roaming_base or (
            Path(appdata) if appdata else home / "AppData" / "Roaming"
        )
        local_base = selected.local_base or (
            Path(localappdata) if localappdata else home / "AppData" / "Local"
        )
        notes = tuple(
            note
            for note, fallback_used in (
                (
                    PathResolutionNote.APPDATA_FALLBACK,
                    selected.roaming_base is None and not appdata,
                ),
                (
                    PathResolutionNote.LOCALAPPDATA_FALLBACK,
                    selected.local_base is None and not localappdata,
                ),
            )
            if fallback_used
        )

    roaming_app = roaming_base / "LNT"
    local_app = local_base / "LNT"
    return AppPaths(
        config_path=roaming_app / "config.json",
        catalog_db=local_app / "catalog.sqlite3",
        runtime_db=local_app / "runtime.sqlite3",
        cache_dir=local_app / "cache",
        log_dir=local_app / "logs",
        support_dir=local_app / "support",
        session_root=selected.session_root or home / "lnt-sessions",
        notes=notes,
    )
