"""Общие фикстуры: детерминированный RNG и временные директории сессий."""

import sys
from pathlib import Path

import numpy as np
import pytest

DEFAULT_SEED = 6022


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
def small_mains_wave(rng: np.random.Generator) -> np.ndarray:
    """Короткий 50 Гц сигнал (0.5 с @ 100 кС/с) с лёгким шумом — для юнитов."""
    sample_rate = 100_000
    t = np.arange(int(0.5 * sample_rate), dtype=np.float64) / sample_rate
    wave = 6.0 * np.sqrt(2.0) * np.sin(2.0 * np.pi * 50.0 * t)
    noise = rng.normal(0.0, 0.002, t.shape)
    return (wave + noise).astype(np.float32)
