"""Общие фикстуры: детерминированный RNG и временные директории сессий."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Final

import numpy as np
import pytest

DEFAULT_SEED = 6022
_PATH_ENV: Final = ("APPDATA", "LOCALAPPDATA")
_ORIGINAL_PATH_ENV: dict[str, str | None] = {}
_session_paths: tempfile.TemporaryDirectory[str] | None = None


def pytest_sessionstart(session: pytest.Session) -> None:
    """Ставит безопасный process-wide fallback ещё до collection тестов."""
    del session
    global _session_paths  # noqa: PLW0603
    _session_paths = tempfile.TemporaryDirectory(prefix="lnt-pytest-paths-")
    root = Path(_session_paths.name)
    for name in _PATH_ENV:
        _ORIGINAL_PATH_ENV[name] = os.environ.get(name)
    os.environ["APPDATA"] = str(root / "roaming")
    os.environ["LOCALAPPDATA"] = str(root / "local")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Возвращает окружение хоста только после завершения всех тестов."""
    del session, exitstatus
    global _session_paths  # noqa: PLW0603
    for name, value in _ORIGINAL_PATH_ENV.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    if _session_paths is not None:
        _session_paths.cleanup()
        _session_paths = None


@pytest.fixture(autouse=True)
def isolate_lnt_app_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Не позволяет ни одному тесту писать в реальные AppData каталоги LNT."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-appdata"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming-appdata"))


@pytest.fixture
def no_hantek_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Блокирует импорт драйвера: сценарий «нет драйвера» и с установленным extra."""
    monkeypatch.setitem(sys.modules, "PyHT6022", None)
    monkeypatch.setitem(sys.modules, "PyHT6022.LibUsbScope", None)


@pytest.fixture
def rng() -> np.random.Generator:
    """Детерминированный генератор для воспроизводимых тестовых сигналов."""
    return np.random.default_rng(DEFAULT_SEED)


@pytest.fixture
def session_root(tmp_path: Path) -> Path:
    """Корень для тестовых сессий (pytest сам убирает tmp_path)."""
    root = tmp_path / "sessions"
    root.mkdir()
    return root


@pytest.fixture
def runtime_db(tmp_path: Path) -> Path:
    """Изолированный путь runtime-хранилища для интеграционных тестов."""
    return tmp_path / "runtime.sqlite3"


@pytest.fixture
def small_mains_wave(rng: np.random.Generator) -> np.ndarray:
    """Короткий 50 Гц сигнал (0.5 с @ 100 кС/с) с лёгким шумом — для юнитов."""
    sample_rate = 100_000
    t = np.arange(int(0.5 * sample_rate), dtype=np.float64) / sample_rate
    wave = 6.0 * np.sqrt(2.0) * np.sin(2.0 * np.pi * 50.0 * t)
    noise = rng.normal(0.0, 0.002, t.shape)
    return (wave + noise).astype(np.float32)
