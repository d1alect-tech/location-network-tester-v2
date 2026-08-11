from pathlib import Path

import pytest

from lnt.app_paths import AppPathOverrides, PathResolutionNote, resolve_app_paths


def test_resolve_app_paths_when_base_dirs_are_explicit() -> None:
    home = Path("C:/Пользователи/") / ("длинный-каталог-" * 12)
    roaming = home / "Roaming"
    local = home / "Local"

    paths = resolve_app_paths(
        AppPathOverrides(home=home, roaming_base=roaming, local_base=local),
    )

    assert paths.config_path == roaming / "LNT" / "config.json"
    assert paths.catalog_db == local / "LNT" / "catalog.sqlite3"
    assert paths.runtime_db == local / "LNT" / "runtime.sqlite3"
    assert paths.cache_dir == local / "LNT" / "cache"
    assert paths.log_dir == local / "LNT" / "logs"
    assert paths.support_dir == local / "LNT" / "support"
    assert paths.session_root == home / "lnt-sessions"
    assert paths.notes == ()


def test_resolve_app_paths_when_windows_environment_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = Path("C:/Users/tester")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    paths = resolve_app_paths()

    assert paths.config_path == home / "AppData" / "Roaming" / "LNT" / "config.json"
    assert paths.catalog_db == home / "AppData" / "Local" / "LNT" / "catalog.sqlite3"
    assert paths.session_root == home / "lnt-sessions"
    assert paths.notes == (
        PathResolutionNote.APPDATA_FALLBACK,
        PathResolutionNote.LOCALAPPDATA_FALLBACK,
    )


def test_resolve_app_paths_when_test_root_is_injected(tmp_path: Path) -> None:
    paths = resolve_app_paths(AppPathOverrides(test_root=tmp_path))

    assert paths.config_path == tmp_path / "roaming" / "LNT" / "config.json"
    assert paths.runtime_db == tmp_path / "local" / "LNT" / "runtime.sqlite3"
    assert paths.session_root == tmp_path / "home" / "lnt-sessions"


def test_resolve_app_paths_when_session_root_is_overridden(tmp_path: Path) -> None:
    session_root = tmp_path / "пользовательские-сессии"

    paths = resolve_app_paths(
        AppPathOverrides(test_root=tmp_path / "isolated", session_root=session_root),
    )

    assert paths.session_root == session_root
    assert paths.catalog_db.parent != session_root
    assert paths.log_dir.parent != session_root
