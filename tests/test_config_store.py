import json
import os
from pathlib import Path

import pytest

from lnt.config import (
    CONFIG_SCHEMA_VERSION,
    Config,
    ConfigLoadStatus,
    ConfigWriteError,
    load_config,
    write_config,
)


def test_load_config_when_file_is_missing_returns_defaults(tmp_path: Path) -> None:
    default_root = Path.home() / "lnt-sessions"

    result = load_config(tmp_path / "config.json", default_session_root=default_root)

    assert result.config == Config(session_root=default_root)
    assert result.status is ConfigLoadStatus.DEFAULTS_MISSING
    assert result.recovered_path is None


def test_write_and_load_config_when_values_are_valid(tmp_path: Path) -> None:
    path = tmp_path / "настройки" / "config.json"
    config = Config(session_root=tmp_path / ("сессии-" * 20))

    write_config(path, config)
    result = load_config(path, default_session_root=Path.home() / "lnt-sessions")

    assert result.config == config
    assert result.status is ConfigLoadStatus.LOADED
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == CONFIG_SCHEMA_VERSION


def test_load_config_when_json_is_corrupt_recovers_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")
    default_root = Path("C:/Users/tester/lnt-sessions")

    result = load_config(path, default_session_root=default_root)

    assert result.config == Config(session_root=default_root)
    assert result.status is ConfigLoadStatus.RECOVERED_CORRUPT
    assert result.recovered_path is not None
    assert result.recovered_path.read_text(encoding="utf-8") == "{broken"
    assert not path.exists()


def test_write_config_when_replace_fails_preserves_previous_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "config.json"
    old_bytes = b'{"schema_version":1,"session_root":"C:/old"}\n'
    path.write_bytes(old_bytes)

    def fail_replace(_source: Path | str, _destination: Path | str) -> None:
        raise PermissionError("read only")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(ConfigWriteError) as captured:
        write_config(path, Config(session_root=Path("C:/new")))

    assert captured.value.path == path
    assert path.read_bytes() == old_bytes
    assert list(tmp_path.glob(".config.json.partial-*")) == []


def test_write_config_when_parent_is_read_only_returns_typed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "read-only" / "config.json"

    def fail_mkdir(
        _path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        del mode, parents, exist_ok
        raise PermissionError("read only")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(ConfigWriteError) as captured:
        write_config(path, Config(session_root=Path.home() / "lnt-sessions"))

    assert captured.value.path == path
