"""Версионированные определения частотных полос."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Final, TypedDict

from lnt.features.errors import FeatureSchemaError

FEATURE_SCHEMA_VERSION: Final = 1


class FrequencyUnit(StrEnum):
    """Поддерживаемые единицы границ полос."""

    HZ = "Hz"
    KHZ = "kHz"
    MHZ = "MHz"


class EstimandDirection(StrEnum):
    """Направление интерпретации оценки без неявного знака улучшения."""

    LOWER = "lower"
    HIGHER = "higher"
    TARGET = "target"
    DESCRIPTIVE = "descriptive"


class BandOverlapPolicy(StrEnum):
    """Явная политика пересечения полос."""

    NON_OVERLAPPING = "non_overlapping"
    OVERLAPPING_ALLOWED = "overlapping_allowed"


class BandDefinitionDict(TypedDict):
    """JSON-safe определение полосы."""

    name: str
    low: float
    high: float
    unit: str
    low_hz: float
    high_hz: float
    direction: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BandDefinition:
    """Именованная полоса с исходными единицами и estimand direction."""

    name: str
    low: float
    high: float
    unit: FrequencyUnit
    direction: EstimandDirection

    def __post_init__(self) -> None:
        """Проверяет конечность и строгий порядок границ."""
        if (
            not self.name
            or not math.isfinite(self.low)
            or not math.isfinite(self.high)
            or self.low < 0.0
            or self.high <= self.low
        ):
            raise FeatureSchemaError("признаки: некорректные границы полосы")

    @classmethod
    def parse(
        cls,
        *,
        name: str,
        low: float,
        high: float,
        unit: str,
        direction: str | None = None,
    ) -> BandDefinition:
        """Разбирает пользовательскую полосу на границе доверия."""
        try:
            parsed_unit = FrequencyUnit(unit)
        except ValueError:
            raise FeatureSchemaError(f"признаки: неизвестная единица {unit!r}") from None
        if direction is None:
            raise FeatureSchemaError("признаки: direction обязателен")
        try:
            parsed_direction = EstimandDirection(direction)
        except ValueError:
            raise FeatureSchemaError(f"признаки: неизвестный direction {direction!r}") from None
        return cls(name=name, low=low, high=high, unit=parsed_unit, direction=parsed_direction)

    @property
    def low_hz(self) -> float:
        """Возвращает нижнюю границу в герцах."""
        return self.low * _unit_scale(self.unit)

    @property
    def high_hz(self) -> float:
        """Возвращает верхнюю границу в герцах."""
        return self.high * _unit_scale(self.unit)

    def to_dict(self) -> BandDefinitionDict:
        """Сериализует исходные и нормализованные границы."""
        return {
            "name": self.name,
            "low": self.low,
            "high": self.high,
            "unit": self.unit.value,
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "direction": self.direction.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class BandSet:
    """Проверенный набор полос feature schema v1."""

    bands: tuple[BandDefinition, ...]
    overlap_policy: BandOverlapPolicy = BandOverlapPolicy.NON_OVERLAPPING
    feature_schema_version: int = FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Проверяет версию, имена и заявленную overlap policy."""
        if self.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise FeatureSchemaError("признаки: неподдерживаемая feature_schema_version")
        if not self.bands:
            raise FeatureSchemaError("признаки: требуется хотя бы одна полоса")
        ordered = sorted(self.bands, key=lambda band: (band.low_hz, band.high_hz))
        if self.overlap_policy is BandOverlapPolicy.NON_OVERLAPPING and any(
            left.high_hz > right.low_hz for left, right in pairwise(ordered)
        ):
            raise FeatureSchemaError("признаки: полосы пересекаются при non_overlapping")
        names = tuple(band.name for band in self.bands)
        if len(set(names)) != len(names):
            raise FeatureSchemaError("признаки: имена полос должны быть уникальны")

    @classmethod
    def from_recipe_edges(
        cls,
        edges_hz: tuple[float, ...],
        directions: tuple[EstimandDirection, ...],
        names: tuple[str, ...] | None = None,
    ) -> BandSet:
        """Строит полосы непосредственно из ``BandsSettings.edges_hz``."""
        band_count = len(edges_hz) - 1
        resolved_names = names or tuple(f"band_{index:04d}" for index in range(1, band_count + 1))
        if band_count < 1 or len(directions) != band_count or len(resolved_names) != band_count:
            raise FeatureSchemaError("признаки: edges, names и directions имеют разную длину")
        return cls(
            bands=tuple(
                BandDefinition(
                    name=resolved_names[index],
                    low=edges_hz[index],
                    high=edges_hz[index + 1],
                    unit=FrequencyUnit.HZ,
                    direction=directions[index],
                )
                for index in range(band_count)
            )
        )


def feature_band_preset(name: str) -> BandSet:
    """Возвращает документированный встроенный split рабочей полосы LNT.

    Декадные границы 30/300 кГц дают три устойчивые области внутри исторической
    полосы 3 кГц–3 МГц без предположения о конкретной физической причине пиков.
    """
    if name != "lnt_working_v1":
        raise FeatureSchemaError(f"признаки: неизвестный preset {name!r}")
    return BandSet(
        bands=(
            BandDefinition(
                name="low",
                low=3.0,
                high=30.0,
                unit=FrequencyUnit.KHZ,
                direction=EstimandDirection.LOWER,
            ),
            BandDefinition(
                name="mid",
                low=30.0,
                high=300.0,
                unit=FrequencyUnit.KHZ,
                direction=EstimandDirection.LOWER,
            ),
            BandDefinition(
                name="high",
                low=0.3,
                high=3.0,
                unit=FrequencyUnit.MHZ,
                direction=EstimandDirection.LOWER,
            ),
        )
    )


def _unit_scale(unit: FrequencyUnit) -> float:
    match unit:
        case FrequencyUnit.HZ:
            return 1.0
        case FrequencyUnit.KHZ:
            return 1_000.0
        case FrequencyUnit.MHZ:
            return 1_000_000.0
