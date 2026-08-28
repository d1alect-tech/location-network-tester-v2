"""Типизированные гармоники IEC 61000-4-7 и JSON-формы."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.errors import InputError
from lnt.harmonics.constants import (
    H_MAX,
    H_MIN,
    HARMONICS_VERSION,
    NOMINAL_GRID_HZ,
    WINDOW_COUNT,
    WINDOW_DURATION_S,
)

DEFAULT_CHUNK_SAMPLES: Final = 1_048_576


class HarmonicsSettingsDict(TypedDict):
    """JSON-safe настройки гармоник."""

    harmonics_version: int
    preset_name: str
    window_duration_s: float
    window_count: int
    h_min: int
    h_max: int
    nominal_grid_hz: float
    chunk_samples: int


class HarmonicsWindowDict(TypedDict):
    """JSON-safe окно гармоник."""

    index: int
    start_time_s: float
    fundamental_rms: float
    thd: float
    h_subgroups: list[float]
    ihg: list[float]


class HarmonicsInventoryDict(TypedDict):
    """JSON-safe инвентарь гармоник."""

    schema_version: int
    settings_hash: str
    settings: HarmonicsSettingsDict
    sample_rate_hz: float
    estimated_grid_frequency_hz: float
    record_duration_s: float
    window_count: int
    windows: list[HarmonicsWindowDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class HarmonicsSettings:
    """Полные пороги для воспроизводимых гармоник."""

    harmonics_version: int
    preset_name: str
    window_duration_s: float
    window_count: int
    h_min: int
    h_max: int
    nominal_grid_hz: float
    chunk_samples: int

    def __post_init__(self) -> None:
        if self.harmonics_version != HARMONICS_VERSION:
            raise InputError("гармоники: неподдерживаемая версия")
        if not self.preset_name or self.chunk_samples <= 0:
            raise InputError("гармоники: имя пресета и размер блока некорректны")
        if not math.isfinite(self.window_duration_s) or self.window_duration_s <= 0:
            raise InputError("гармоники: длительность окна некорректна")
        if self.h_min < 1 or self.h_max < self.h_min:
            raise InputError("гармоники: диапазон гармоник некорректен")

    def to_dict(self) -> HarmonicsSettingsDict:
        return {
            "harmonics_version": self.harmonics_version,
            "preset_name": self.preset_name,
            "window_duration_s": self.window_duration_s,
            "window_count": self.window_count,
            "h_min": self.h_min,
            "h_max": self.h_max,
            "nominal_grid_hz": self.nominal_grid_hz,
            "chunk_samples": self.chunk_samples,
        }


def harmonics_preset(
    name: str = "harmonics_default", *, chunk_samples: int = DEFAULT_CHUNK_SAMPLES
) -> HarmonicsSettings:
    """Разворачивает preset в полные настройки."""
    if name != "harmonics_default":
        raise InputError(f"гармоники: неизвестный preset {name!r}")
    return HarmonicsSettings(
        harmonics_version=HARMONICS_VERSION,
        preset_name=name,
        window_duration_s=WINDOW_DURATION_S,
        window_count=WINDOW_COUNT,
        h_min=H_MIN,
        h_max=H_MAX,
        nominal_grid_hz=NOMINAL_GRID_HZ,
        chunk_samples=chunk_samples,
    )


def harmonics_settings_hash(settings: HarmonicsSettings) -> str:
    """SHA-256 канонического JSON настроек."""
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class HarmonicsWindow:
    """Окно 200 мс: THD и подгруппы."""

    index: int
    start_time_s: float
    fundamental_rms: float
    thd: float
    h_subgroups: tuple[float, ...]
    ihg: tuple[float, ...]

    def to_dict(self) -> HarmonicsWindowDict:
        return {
            "index": self.index,
            "start_time_s": self.start_time_s,
            "fundamental_rms": self.fundamental_rms,
            "thd": self.thd,
            "h_subgroups": list(self.h_subgroups),
            "ihg": list(self.ihg),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class HarmonicsInventory:
    """Детерминированный инвентарь гармоник записи."""

    schema_version: int
    settings_hash: str
    settings: HarmonicsSettings
    sample_rate_hz: float
    estimated_grid_frequency_hz: float
    record_duration_s: float
    window_count: int
    windows: tuple[HarmonicsWindow, ...]

    def to_dict(self) -> HarmonicsInventoryDict:
        return {
            "schema_version": self.schema_version,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "sample_rate_hz": self.sample_rate_hz,
            "estimated_grid_frequency_hz": self.estimated_grid_frequency_hz,
            "record_duration_s": self.record_duration_s,
            "window_count": self.window_count,
            "windows": [w.to_dict() for w in self.windows],
        }
