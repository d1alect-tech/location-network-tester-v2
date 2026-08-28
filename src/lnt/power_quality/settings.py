"""Версионированные, полностью явные настройки детектора качества питания."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.errors import InputError
from lnt.power_quality.constants import (
    DEFAULT_BAND_HIGH_PCT,
    DEFAULT_BAND_LOW_PCT,
    DEFAULT_DROPOUT_MAX_PCT,
    DEFAULT_MERGE_GAP_HALF_CYCLES,
    POWER_QUALITY_VERSION,
    RVC_STEP_THRESHOLD_PCT,
    RVC_SUSTAIN_CYCLES,
    RVC_SUSTAIN_TOLERANCE_PCT,
)


class PowerQualitySettingsDict(TypedDict):
    """JSON-safe полные эффективные настройки детектора."""

    power_quality_version: int
    preset_name: str
    band_low_pct: float
    band_high_pct: float
    merge_gap_half_cycles: int
    dropout_max_pct: float
    rvc_step_threshold_pct: float
    rvc_sustain_cycles: int
    rvc_sustain_tolerance_pct: float
    chunk_samples: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PowerQualitySettings:
    """Все пороги, необходимые для точного воспроизведения детекции."""

    power_quality_version: int
    preset_name: str
    band_low_pct: float
    band_high_pct: float
    merge_gap_half_cycles: int
    dropout_max_pct: float
    rvc_step_threshold_pct: float
    rvc_sustain_cycles: int
    rvc_sustain_tolerance_pct: float
    chunk_samples: int

    def __post_init__(self) -> None:
        """Валидирует каждый эффективный порог на границе конструирования."""
        scalars = (
            self.band_low_pct,
            self.band_high_pct,
            self.dropout_max_pct,
            self.rvc_step_threshold_pct,
            self.rvc_sustain_tolerance_pct,
        )
        if self.power_quality_version != POWER_QUALITY_VERSION:
            raise InputError("качество питания: неподдерживаемая версия алгоритма")
        if not self.preset_name or self.chunk_samples <= 0 or self.merge_gap_half_cycles < 0:
            raise InputError("качество питания: имя пресета и размеры должны быть корректны")
        if any(not math.isfinite(value) for value in scalars):
            raise InputError("качество питания: пороги должны быть конечными числами")
        if self.rvc_sustain_cycles < 1:
            raise InputError("качество питания: RVC должен удерживаться минимум цикл")
        if not 0.0 < self.band_low_pct < self.band_high_pct:
            raise InputError("качество питания: полоса устойчивого режима некорректна")
        if not 0.0 < self.dropout_max_pct < self.band_low_pct:
            raise InputError("качество питания: порог dropout должен быть ниже полосы")
        if self.rvc_step_threshold_pct <= 0.0 or self.rvc_sustain_tolerance_pct < 0.0:
            raise InputError("качество питания: пороги RVC должны быть положительными")

    def to_dict(self) -> PowerQualitySettingsDict:
        """Сериализует все эффективные пороги без неявных значений по умолчанию."""
        return {
            "power_quality_version": self.power_quality_version,
            "preset_name": self.preset_name,
            "band_low_pct": self.band_low_pct,
            "band_high_pct": self.band_high_pct,
            "merge_gap_half_cycles": self.merge_gap_half_cycles,
            "dropout_max_pct": self.dropout_max_pct,
            "rvc_step_threshold_pct": self.rvc_step_threshold_pct,
            "rvc_sustain_cycles": self.rvc_sustain_cycles,
            "rvc_sustain_tolerance_pct": self.rvc_sustain_tolerance_pct,
            "chunk_samples": self.chunk_samples,
        }


_DEFAULT_CHUNK_SAMPLES: Final = 1_048_576


def power_quality_preset(name: str) -> PowerQualitySettings:
    """Разворачивает именованный пресет в полные персистентные настройки."""
    match name:
        case "itic_default":
            return PowerQualitySettings(
                power_quality_version=POWER_QUALITY_VERSION,
                preset_name=name,
                band_low_pct=DEFAULT_BAND_LOW_PCT,
                band_high_pct=DEFAULT_BAND_HIGH_PCT,
                merge_gap_half_cycles=DEFAULT_MERGE_GAP_HALF_CYCLES,
                dropout_max_pct=DEFAULT_DROPOUT_MAX_PCT,
                rvc_step_threshold_pct=RVC_STEP_THRESHOLD_PCT,
                rvc_sustain_cycles=RVC_SUSTAIN_CYCLES,
                rvc_sustain_tolerance_pct=RVC_SUSTAIN_TOLERANCE_PCT,
                chunk_samples=_DEFAULT_CHUNK_SAMPLES,
            )
        case _:
            raise InputError(f"качество питания: неизвестный preset {name!r}")
