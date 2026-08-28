"""Типизированные события EFT/burst 61000-4-4 и JSON-формы."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.errors import InputError

BURST_VERSION: Final = 1
DEFAULT_THRESHOLD_FACTOR: Final = 8.0
DEFAULT_MIN_BURST_MS: Final = 5.0
DEFAULT_MAX_BURST_MS: Final = 55.0
DEFAULT_BURST_DURATION_MS: Final = 15.0
DEFAULT_BURST_PERIOD_MS: Final = 300.0
DEFAULT_CHUNK_SAMPLES: Final = 1_048_576


class BurstSettingsDict(TypedDict):
    """JSON-safe настройки burst-детектора."""

    burst_version: int
    preset_name: str
    threshold_factor: float
    min_burst_duration_ms: float
    max_burst_duration_ms: float
    burst_duration_ms: float
    burst_period_ms: float
    chunk_samples: int


class BurstEventDict(TypedDict):
    """JSON-safe единичный burst."""

    start_time_s: float
    end_time_s: float
    duration_ms: float
    peak_envelope_v: float


class BurstSequenceDict(TypedDict):
    """JSON-safe последовательность bursts (300 мс период)."""

    start_time_s: float
    end_time_s: float
    burst_count: int
    period_ms: float


class BurstInventoryDict(TypedDict):
    """JSON-safe инвентарь burst-детекции."""

    schema_version: int
    settings_hash: str
    settings: BurstSettingsDict
    sample_rate_hz: float
    sample_count: int
    duration_s: float
    burst_count: int
    bursts_per_second: float
    sequence_count: int
    bursts: list[BurstEventDict]
    sequences: list[BurstSequenceDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class BurstSettings:
    """Пороги для воспроизводимого EFT/burst детектора."""

    burst_version: int
    preset_name: str
    threshold_factor: float
    min_burst_duration_ms: float
    max_burst_duration_ms: float
    burst_duration_ms: float
    burst_period_ms: float
    chunk_samples: int

    def __post_init__(self) -> None:
        """Валидирует пороги на границе конструирования."""
        if self.burst_version != BURST_VERSION:
            raise InputError("burst: неподдерживаемая версия")
        if not self.preset_name or self.chunk_samples <= 0:
            raise InputError("burst: имя пресета и размер блока некорректны")
        vals = (
            self.threshold_factor,
            self.min_burst_duration_ms,
            self.max_burst_duration_ms,
            self.burst_duration_ms,
            self.burst_period_ms,
        )
        if any(not math.isfinite(v) for v in vals):
            raise InputError("burst: пороги должны быть конечными")
        if self.threshold_factor <= 0 or self.min_burst_duration_ms <= 0:
            raise InputError("burst: пороги должны быть >0")
        if self.min_burst_duration_ms > self.max_burst_duration_ms:
            raise InputError("burst: min > max длительности")

    def to_dict(self) -> BurstSettingsDict:
        """Сериализует настройки без неявных defaults."""
        return {
            "burst_version": self.burst_version,
            "preset_name": self.preset_name,
            "threshold_factor": self.threshold_factor,
            "min_burst_duration_ms": self.min_burst_duration_ms,
            "max_burst_duration_ms": self.max_burst_duration_ms,
            "burst_duration_ms": self.burst_duration_ms,
            "burst_period_ms": self.burst_period_ms,
            "chunk_samples": self.chunk_samples,
        }


def burst_preset(name: str = "burst_default") -> BurstSettings:
    """Разворачивает preset в настройки."""
    if name != "burst_default":
        raise InputError(f"burst: неизвестный preset {name!r}")
    return BurstSettings(
        burst_version=BURST_VERSION,
        preset_name=name,
        threshold_factor=DEFAULT_THRESHOLD_FACTOR,
        min_burst_duration_ms=DEFAULT_MIN_BURST_MS,
        max_burst_duration_ms=DEFAULT_MAX_BURST_MS,
        burst_duration_ms=DEFAULT_BURST_DURATION_MS,
        burst_period_ms=DEFAULT_BURST_PERIOD_MS,
        chunk_samples=DEFAULT_CHUNK_SAMPLES,
    )


def burst_settings_hash(settings: BurstSettings) -> str:
    """SHA-256 канонического JSON настроек."""
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class BurstEvent:
    """Один burst 15 мс: интервал и пик огибающей."""

    start_time_s: float
    end_time_s: float
    duration_ms: float
    peak_envelope_v: float

    def to_dict(self) -> BurstEventDict:
        return {
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "duration_ms": self.duration_ms,
            "peak_envelope_v": self.peak_envelope_v,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class BurstSequence:
    """Последовательность burst с периодом ~300 мс."""

    start_time_s: float
    end_time_s: float
    burst_count: int
    period_ms: float

    def to_dict(self) -> BurstSequenceDict:
        return {
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "burst_count": self.burst_count,
            "period_ms": self.period_ms,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class BurstInventory:
    """Инвентарь EFT/burst детекции."""

    schema_version: int
    settings_hash: str
    settings: BurstSettings
    sample_rate_hz: float
    sample_count: int
    duration_s: float
    burst_count: int
    bursts_per_second: float
    sequence_count: int
    bursts: tuple[BurstEvent, ...]
    sequences: tuple[BurstSequence, ...]

    def to_dict(self) -> BurstInventoryDict:
        return {
            "schema_version": self.schema_version,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "sample_rate_hz": self.sample_rate_hz,
            "sample_count": self.sample_count,
            "duration_s": self.duration_s,
            "burst_count": self.burst_count,
            "bursts_per_second": self.bursts_per_second,
            "sequence_count": self.sequence_count,
            "bursts": [b.to_dict() for b in self.bursts],
            "sequences": [s.to_dict() for s in self.sequences],
        }
