"""Типизированные APD ITU-R P.2089 и Middleton Class A модели."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.errors import InputError

APD_VERSION: Final = 1
DEFAULT_CHUNK_SAMPLES: Final = 1_048_576
DEFAULT_NUM_LEVELS: Final = 256


class ApdSettingsDict(TypedDict):
    """JSON-safe настройки APD."""

    apd_version: int
    preset_name: str
    chunk_samples: int
    num_levels: int


class ApdPointDict(TypedDict):
    """Точка APD: уровень dB над rms и вероятность превышения."""

    level_db: float
    exceedance_prob: float
    amplitude_v: float


class MiddletonParamsDict(TypedDict):
    """Оценка Middleton Class A."""

    overlap_index_A: float
    gamma: float
    rms_v: float
    kurtosis: float
    mean_power: float


class ApdInventoryDict(TypedDict):
    """Полный инвентарь APD."""

    schema_version: int
    settings_hash: str
    settings: ApdSettingsDict
    sample_rate_hz: float
    sample_count: int
    duration_s: float
    rms_v: float
    middleton: MiddletonParamsDict
    apd_slope_db_per_decade: float
    apd: list[ApdPointDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class ApdSettings:
    """Полные настройки детектора APD."""

    apd_version: int
    preset_name: str
    chunk_samples: int
    num_levels: int

    def __post_init__(self) -> None:
        """Отвергает чужую версию схемы и непригодные размеры блока/сетки уровней."""
        if self.apd_version != APD_VERSION:
            raise InputError("apd: неподдерживаемая версия")
        if not self.preset_name or self.chunk_samples <= 0 or self.num_levels <= 1:
            raise InputError("apd: имя пресета и размеры некорректны")

    def to_dict(self) -> ApdSettingsDict:
        """Возвращает настройки в виде, от которого считается хеш пресета."""
        return {
            "apd_version": self.apd_version,
            "preset_name": self.preset_name,
            "chunk_samples": self.chunk_samples,
            "num_levels": self.num_levels,
        }


def apd_preset(
    name: str = "apd_default", *, chunk_samples: int = DEFAULT_CHUNK_SAMPLES
) -> ApdSettings:
    """Разворачивает preset в полные настройки."""
    if name != "apd_default":
        raise InputError(f"apd: неизвестный preset {name!r}")
    return ApdSettings(
        apd_version=APD_VERSION,
        preset_name=name,
        chunk_samples=chunk_samples,
        num_levels=DEFAULT_NUM_LEVELS,
    )


def apd_settings_hash(settings: ApdSettings) -> str:
    """SHA-256 канонического JSON настроек."""
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ApdPoint:
    """Точка APD."""

    level_db: float
    exceedance_prob: float
    amplitude_v: float

    def to_dict(self) -> ApdPointDict:
        """Уровень (дБ), вероятность превышения и амплитуда (В) одной точки кривой."""
        return {
            "level_db": self.level_db,
            "exceedance_prob": self.exceedance_prob,
            "amplitude_v": self.amplitude_v,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class MiddletonParams:
    """Параметры Middleton Class A по моментам."""

    overlap_index_A: float  # noqa: N815
    gamma: float
    rms_v: float
    kurtosis: float
    mean_power: float

    def to_dict(self) -> MiddletonParamsDict:
        """Параметры Middleton Class A по моментам: A, Г, RMS, эксцесс, средняя мощность."""
        return {
            "overlap_index_A": self.overlap_index_A,
            "gamma": self.gamma,
            "rms_v": self.rms_v,
            "kurtosis": self.kurtosis,
            "mean_power": self.mean_power,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ApdInventory:
    """Детерминированный инвентарь APD записи."""

    schema_version: int
    settings_hash: str
    settings: ApdSettings
    sample_rate_hz: float
    sample_count: int
    duration_s: float
    rms_v: float
    middleton: MiddletonParams
    apd_slope_db_per_decade: float
    apd: tuple[ApdPoint, ...]

    def to_dict(self) -> ApdInventoryDict:
        """Полный инвентарь для apd.json: настройки, моменты, наклон и сама кривая APD."""
        return {
            "schema_version": self.schema_version,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "sample_rate_hz": self.sample_rate_hz,
            "sample_count": self.sample_count,
            "duration_s": self.duration_s,
            "rms_v": self.rms_v,
            "middleton": self.middleton.to_dict(),
            "apd_slope_db_per_decade": self.apd_slope_db_per_decade,
            "apd": [p.to_dict() for p in self.apd],
        }
