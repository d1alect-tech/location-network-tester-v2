"""Неизменяемые результаты вычисления спектральных признаков."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from lnt.features.bands import BandDefinition, BandDefinitionDict, EstimandDirection


class NoiseFloorDict(TypedDict):
    """JSON-safe робастная оценка спектрального фона."""

    median_v2_per_hz: float | None
    p05_v2_per_hz: float | None
    p95_v2_per_hz: float | None
    qualified_bin_count: int
    total_bin_count: int
    qualified: bool
    reason_code: str | None


class PeakFeatureDict(TypedDict):
    """JSON-safe параметры доминирующего пика."""

    frequency_hz: float
    power_v2_per_hz: float
    prominence_db: float
    q_factor: float | None
    q_reason_code: str | None
    qualified: bool


class BandFeatureDict(TypedDict):
    """JSON-safe полосовой спектральный estimand."""

    feature_schema_version: int
    band: BandDefinitionDict
    direction: str
    integrated_power_v2: float | None
    power_unit: str
    rms_v: float | None
    rms_unit: str
    noise_floor: NoiseFloorDict
    peak: PeakFeatureDict | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NoiseFloor:
    """Медиана и квантили только по квалифицированным бинам."""

    median_v2_per_hz: float | None
    p05_v2_per_hz: float | None
    p95_v2_per_hz: float | None
    qualified_bin_count: int
    total_bin_count: int
    qualified: bool
    reason_code: str | None

    def to_dict(self) -> NoiseFloorDict:
        """Сериализует оценку и qualification provenance."""
        return {
            "median_v2_per_hz": self.median_v2_per_hz,
            "p05_v2_per_hz": self.p05_v2_per_hz,
            "p95_v2_per_hz": self.p95_v2_per_hz,
            "qualified_bin_count": self.qualified_bin_count,
            "total_bin_count": self.total_bin_count,
            "qualified": self.qualified,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PeakFeature:
    """Пик с prominence и квалифицированным Q."""

    frequency_hz: float
    power_v2_per_hz: float
    prominence_db: float
    q_factor: float | None
    q_reason_code: str | None
    qualified: bool

    def to_dict(self) -> PeakFeatureDict:
        """Сериализует пик без NaN-заполнителей."""
        return {
            "frequency_hz": self.frequency_hz,
            "power_v2_per_hz": self.power_v2_per_hz,
            "prominence_db": self.prominence_db,
            "q_factor": self.q_factor,
            "q_reason_code": self.q_reason_code,
            "qualified": self.qualified,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class BandFeature:
    """Линейная мощность, RMS, фон и пик одной полосы."""

    band: BandDefinition
    integrated_power_v2: float | None
    rms_v: float | None
    noise_floor: NoiseFloor
    peak: PeakFeature | None
    feature_schema_version: int = 1

    @property
    def direction(self) -> EstimandDirection:
        """Возвращает обязательное направление estimand."""
        return self.band.direction

    def to_dict(self) -> BandFeatureDict:
        """Сериализует значения с единицами и qualification."""
        return {
            "feature_schema_version": self.feature_schema_version,
            "band": self.band.to_dict(),
            "direction": self.direction.value,
            "integrated_power_v2": self.integrated_power_v2,
            "power_unit": "V²",
            "rms_v": self.rms_v,
            "rms_unit": "V",
            "noise_floor": self.noise_floor.to_dict(),
            "peak": None if self.peak is None else self.peak.to_dict(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectralFeatures:
    """PSD-признаки всех заявленных полос."""

    bands: tuple[BandFeature, ...]
    feature_schema_version: int = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectrogramWindowFeatures:
    """Полосовые признаки одного временного окна overview."""

    window_id: str
    time_s: float
    bands: tuple[BandFeature, ...]
    feature_schema_version: int = 1
