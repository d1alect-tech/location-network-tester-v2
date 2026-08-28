"""Типизированные события нотчинга и JSON-безопасные формы payload."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.errors import InputError

NOTCHING_VERSION: Final = 1
DEFAULT_LOWPASS_HZ: Final = 500.0
DEFAULT_THRESHOLD_PCT: Final = 15.0
DEFAULT_MIN_WIDTH_US: Final = 20.0
DEFAULT_CHUNK_SAMPLES: Final = 1_048_576


class NotchingSettingsDict(TypedDict):
    """JSON-safe полные эффективные настройки детектора."""

    notching_version: int
    preset_name: str
    lowpass_hz: float
    threshold_pct: float
    min_width_us: float
    chunk_samples: int


class NotchEventDict(TypedDict):
    """JSON-safe payload одного нотча."""

    start_time_s: float
    end_time_s: float
    duration_us: float
    depth_v: float
    area_v_us: float


class NotchingInventoryDict(TypedDict):
    """JSON-safe полный инвентарь нотчинга."""

    schema_version: int
    settings_hash: str
    settings: NotchingSettingsDict
    sample_rate_hz: float
    sample_count: int
    duration_s: float
    notch_count: int
    notches_per_second: float
    expected_crossings: int
    observed_crossings: int
    spurious_crossings: int
    jitter_us: float
    notches: list[NotchEventDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class NotchingSettings:
    """Все пороги для воспроизводимого детектора нотчинга."""

    notching_version: int
    preset_name: str
    lowpass_hz: float
    threshold_pct: float
    min_width_us: float
    chunk_samples: int

    def __post_init__(self) -> None:
        """Валидирует пороги на границе конструирования."""
        if self.notching_version != NOTCHING_VERSION:
            raise InputError("нотчинг: неподдерживаемая версия алгоритма")
        if not self.preset_name or self.chunk_samples <= 0:
            raise InputError("нотчинг: имя пресета и размер блока некорректны")
        if any(
            not math.isfinite(v) for v in (self.lowpass_hz, self.threshold_pct, self.min_width_us)
        ):
            raise InputError("нотчинг: пороги должны быть конечными")
        if self.lowpass_hz <= 0 or self.threshold_pct <= 0 or self.min_width_us < 0:
            raise InputError("нотчинг: пороги должны быть положительными")

    def to_dict(self) -> NotchingSettingsDict:
        """Сериализует настройки без неявных defaults."""
        return {
            "notching_version": self.notching_version,
            "preset_name": self.preset_name,
            "lowpass_hz": self.lowpass_hz,
            "threshold_pct": self.threshold_pct,
            "min_width_us": self.min_width_us,
            "chunk_samples": self.chunk_samples,
        }


def notching_preset(name: str = "notching_default") -> NotchingSettings:
    """Разворачивает preset в полные настройки."""
    if name != "notching_default":
        raise InputError(f"нотчинг: неизвестный preset {name!r}")
    return NotchingSettings(
        notching_version=NOTCHING_VERSION,
        preset_name=name,
        lowpass_hz=DEFAULT_LOWPASS_HZ,
        threshold_pct=DEFAULT_THRESHOLD_PCT,
        min_width_us=DEFAULT_MIN_WIDTH_US,
        chunk_samples=DEFAULT_CHUNK_SAMPLES,
    )


def notching_settings_hash(settings: NotchingSettings) -> str:
    """SHA-256 канонического JSON настроек."""
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class NotchEvent:
    """Один нотч: глубина, площадь, длительность."""

    start_time_s: float
    end_time_s: float
    duration_us: float
    depth_v: float
    area_v_us: float

    def to_dict(self) -> NotchEventDict:
        """Сериализует нотч в JSON-безопасные примитивы."""
        return {
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "duration_us": self.duration_us,
            "depth_v": self.depth_v,
            "area_v_us": self.area_v_us,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class NotchingInventory:
    """Детерминированный инвентарь нотчинга записи."""

    schema_version: int
    settings_hash: str
    settings: NotchingSettings
    sample_rate_hz: float
    sample_count: int
    duration_s: float
    notch_count: int
    notches_per_second: float
    expected_crossings: int
    observed_crossings: int
    spurious_crossings: int
    jitter_us: float
    notches: tuple[NotchEvent, ...]

    def to_dict(self) -> NotchingInventoryDict:
        """Сериализует инвентарь целиком."""
        return {
            "schema_version": self.schema_version,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "sample_rate_hz": self.sample_rate_hz,
            "sample_count": self.sample_count,
            "duration_s": self.duration_s,
            "notch_count": self.notch_count,
            "notches_per_second": self.notches_per_second,
            "expected_crossings": self.expected_crossings,
            "observed_crossings": self.observed_crossings,
            "spurious_crossings": self.spurious_crossings,
            "jitter_us": self.jitter_us,
            "notches": [n.to_dict() for n in self.notches],
        }
