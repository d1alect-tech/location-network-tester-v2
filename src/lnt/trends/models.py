"""Типизированные тренды: Theil-Sen, CUSUM, crest, discard 2000."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.errors import InputError

TRENDS_VERSION: Final = 1
DEFAULT_CHUNK_SAMPLES: Final = 1_048_576
DEFAULT_DISCARD_SAMPLES: Final = 2000
DEFAULT_THEIL_SEN_MAX_PAIRS: Final = 256
DEFAULT_CUSUM_THRESHOLD_SIGMA: Final = 3.0
DEFAULT_MIN_SEGMENT_LENGTH: Final = 10


class TrendsSettingsDict(TypedDict):
    """JSON-safe настройки трендов."""

    trends_version: int
    preset_name: str
    chunk_samples: int
    discard_samples: int
    theil_sen_max_pairs: int
    cusum_threshold_sigma: float
    min_segment_length: int


class TrendChangePointDict(TypedDict):
    """JSON-safe точка изменения."""

    index: int
    time_s: float
    mean_before: float
    mean_after: float


class TrendsInventoryDict(TypedDict):
    """JSON-safe инвентарь трендов."""

    schema_version: int
    settings_hash: str
    settings: TrendsSettingsDict
    sample_rate_hz: float
    sample_count: int
    effective_sample_count: int
    duration_s: float
    discard_samples: int
    rms_v: float
    peak_v: float
    crest_factor: float
    theil_sen_slope: float
    theil_sen_intercept: float
    change_points: list[TrendChangePointDict]
    eeprom_readback_hash: str
    eeprom_verified: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class TrendsSettings:
    """Полные воспроизводимые настройки детектора трендов."""

    trends_version: int
    preset_name: str
    chunk_samples: int
    discard_samples: int
    theil_sen_max_pairs: int
    cusum_threshold_sigma: float
    min_segment_length: int

    def __post_init__(self) -> None:
        if self.trends_version != TRENDS_VERSION:
            raise InputError("тренды: неподдерживаемая версия")
        if not self.preset_name or self.chunk_samples <= 0:
            raise InputError("тренды: имя пресета и размер блока некорректны")
        if self.discard_samples < 0 or self.theil_sen_max_pairs <= 0:
            raise InputError("тренды: discard и max_pairs некорректны")
        if not math.isfinite(self.cusum_threshold_sigma) or self.cusum_threshold_sigma <= 0:
            raise InputError("тренды: порог CUSUM некорректен")
        if self.min_segment_length < 2:
            raise InputError("тренды: min_segment_length >=2")

    def to_dict(self) -> TrendsSettingsDict:
        return {
            "trends_version": self.trends_version,
            "preset_name": self.preset_name,
            "chunk_samples": self.chunk_samples,
            "discard_samples": self.discard_samples,
            "theil_sen_max_pairs": self.theil_sen_max_pairs,
            "cusum_threshold_sigma": self.cusum_threshold_sigma,
            "min_segment_length": self.min_segment_length,
        }


def trends_preset(name: str = "trends_default") -> TrendsSettings:
    """Разворачивает preset."""
    if name != "trends_default":
        raise InputError(f"тренды: неизвестный preset {name!r}")
    return TrendsSettings(
        trends_version=TRENDS_VERSION,
        preset_name=name,
        chunk_samples=DEFAULT_CHUNK_SAMPLES,
        discard_samples=DEFAULT_DISCARD_SAMPLES,
        theil_sen_max_pairs=DEFAULT_THEIL_SEN_MAX_PAIRS,
        cusum_threshold_sigma=DEFAULT_CUSUM_THRESHOLD_SIGMA,
        min_segment_length=DEFAULT_MIN_SEGMENT_LENGTH,
    )


def trends_settings_hash(settings: TrendsSettings) -> str:
    """SHA-256 канонического JSON настроек."""
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class TrendChangePoint:
    """Точка изменения (CUSUM/binary segmentation)."""

    index: int
    time_s: float
    mean_before: float
    mean_after: float

    def to_dict(self) -> TrendChangePointDict:
        return {
            "index": self.index,
            "time_s": self.time_s,
            "mean_before": self.mean_before,
            "mean_after": self.mean_after,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TrendsInventory:
    """Детерминированный инвентарь трендов."""

    schema_version: int
    settings_hash: str
    settings: TrendsSettings
    sample_rate_hz: float
    sample_count: int
    effective_sample_count: int
    duration_s: float
    discard_samples: int
    rms_v: float
    peak_v: float
    crest_factor: float
    theil_sen_slope: float
    theil_sen_intercept: float
    change_points: tuple[TrendChangePoint, ...]
    eeprom_readback_hash: str
    eeprom_verified: bool

    def to_dict(self) -> TrendsInventoryDict:
        return {
            "schema_version": self.schema_version,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "sample_rate_hz": self.sample_rate_hz,
            "sample_count": self.sample_count,
            "effective_sample_count": self.effective_sample_count,
            "duration_s": self.duration_s,
            "discard_samples": self.discard_samples,
            "rms_v": self.rms_v,
            "peak_v": self.peak_v,
            "crest_factor": self.crest_factor,
            "theil_sen_slope": self.theil_sen_slope,
            "theil_sen_intercept": self.theil_sen_intercept,
            "change_points": [c.to_dict() for c in self.change_points],
            "eeprom_readback_hash": self.eeprom_readback_hash,
            "eeprom_verified": self.eeprom_verified,
        }
