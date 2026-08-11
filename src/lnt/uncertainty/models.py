"""Типизированные объекты области неопределённости и JSON-представления."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.context.json_codec import JsonValue


class Measurand(StrEnum):
    """Закрытый реестр скалярных измеряемых величин."""

    BAND_RMS = "band_rms"
    BAND_POWER = "band_power"
    SECONDARY_RMS = "secondary_rms"
    PRIMARY_RMS_CALIBRATED = "primary_rms_calibrated"
    THD = "thd"
    HARMONIC_RATIO = "harmonic_ratio"


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasurandDefinition:
    """Метаданные поддержанного скалярного measurand."""

    measurand: Measurand
    quantity_kind: str
    calibration_required: bool


MEASURAND_REGISTRY: tuple[MeasurandDefinition, ...] = (
    MeasurandDefinition(
        measurand=Measurand.BAND_RMS, quantity_kind="linear_rms", calibration_required=False
    ),
    MeasurandDefinition(
        measurand=Measurand.BAND_POWER, quantity_kind="linear_power", calibration_required=False
    ),
    MeasurandDefinition(
        measurand=Measurand.SECONDARY_RMS, quantity_kind="linear_rms", calibration_required=True
    ),
    MeasurandDefinition(
        measurand=Measurand.PRIMARY_RMS_CALIBRATED,
        quantity_kind="linear_rms",
        calibration_required=True,
    ),
    MeasurandDefinition(
        measurand=Measurand.THD, quantity_kind="linear_ratio", calibration_required=False
    ),
    MeasurandDefinition(
        measurand=Measurand.HARMONIC_RATIO,
        quantity_kind="linear_ratio",
        calibration_required=False,
    ),
)


class PropagationMethod(StrEnum):
    """Поддержанные и явно неподдержанный пути распространения."""

    LINEAR = "linear_domain"
    MONTE_CARLO = "monte_carlo"
    UNSUPPORTED_NONLINEAR = "unsupported_nonlinear"


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalDistribution:
    """Нормальное Type-B распределение, заданное стандартной неопределённостью."""

    standard_uncertainty: float


@dataclass(frozen=True, slots=True, kw_only=True)
class RectangularDistribution:
    """Равномерное Type-B распределение с явной полушириной."""

    half_width: float


@dataclass(frozen=True, slots=True, kw_only=True)
class TriangularDistribution:
    """Симметричное треугольное Type-B распределение с явной полушириной."""

    half_width: float


type TypeBDistribution = NormalDistribution | RectangularDistribution | TriangularDistribution


@dataclass(frozen=True, slots=True, kw_only=True)
class SensitivityCoefficient:
    """Именованный коэффициент чувствительности конкретной модели."""

    name: str
    value: float


@dataclass(frozen=True, slots=True, kw_only=True)
class TypeBComponent:
    """Явно предоставленная составляющая Type-B профиля."""

    name: str
    distribution: TypeBDistribution
    sensitivity: SensitivityCoefficient
    correlation_group: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CovarianceTerm:
    """Предоставленная вызывающей стороной ковариация двух компонентов."""

    left: str
    right: str
    covariance: float


@dataclass(frozen=True, slots=True, kw_only=True)
class MonteCarloSettings:
    """Параметры воспроизводимого детерминированного Monte Carlo."""

    seed: int
    draw_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ComponentContribution:
    """Сериализуемый вклад одной Type-B составляющей."""

    name: str
    distribution: str
    standard_uncertainty: float
    sensitivity_name: str
    sensitivity_value: float

    def to_mapping(self) -> dict[str, JsonValue]:
        """Возвращает JSON-safe описание вклада."""
        return {
            "name": self.name,
            "distribution": self.distribution,
            "standard_uncertainty": self.standard_uncertainty,
            "sensitivity_name": self.sensitivity_name,
            "sensitivity_value": self.sensitivity_value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class UncertaintyResult:
    """Численный бюджет либо reason-coded отказ без ложного числа."""

    measurand: Measurand
    estimate: float
    unit: str
    status: str
    method: str
    reason_code: str | None = None
    reason_message: str | None = None
    standard_uncertainty: float | None = None
    expanded_uncertainty: float | None = None
    coverage_method: str | None = None
    coverage_factor: float | None = None
    covariance_included: bool = False
    components: tuple[ComponentContribution, ...] = ()
    monte_carlo_seed: int | None = None
    monte_carlo_draw_count: int | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        """Сериализует результат, исключая численные поля при отказе."""
        result: dict[str, JsonValue] = {
            "measurand": self.measurand.value,
            "estimate": self.estimate,
            "unit": self.unit,
            "status": self.status,
            "method": self.method,
            "covariance_included": self.covariance_included,
            "components": [component.to_mapping() for component in self.components],
        }
        optional: Mapping[str, str | int | float | None] = {
            "reason_code": self.reason_code,
            "reason_message": self.reason_message,
            "standard_uncertainty": self.standard_uncertainty,
            "expanded_uncertainty": self.expanded_uncertainty,
            "coverage_method": self.coverage_method,
            "coverage_factor": self.coverage_factor,
            "monte_carlo_seed": self.monte_carlo_seed,
            "monte_carlo_draw_count": self.monte_carlo_draw_count,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class SingleRecordDescription:
    """Разрешение и вариабельность одной записи, не неопределённость измерения."""

    resolution_hz: float
    bin_width_hz: float
    spectral_variability: float
    spectral_variability_unit: str

    def to_mapping(self) -> dict[str, JsonValue]:
        """Возвращает честно маркированное JSON-представление одной записи."""
        return {
            "classification": "not_measurement_uncertainty",
            "reason_code": "single_record_variability_only",
            "reason_message": (
                "Одна запись описывает только разрешение и внутриполосную "
                "спектральную вариабельность"
            ),
            "method": "welch_resolution_and_within_record_variability",
            "resolution_hz": self.resolution_hz,
            "bin_width_hz": self.bin_width_hz,
            "spectral_variability": self.spectral_variability,
            "spectral_variability_unit": self.spectral_variability_unit,
            "spectral_variability_label": "within_record_spectral_variability",
        }
