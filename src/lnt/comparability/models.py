"""Типизированные входы и результаты v2-сопоставимости."""

from dataclasses import dataclass
from enum import StrEnum
from typing import override

from lnt.acquisition_quality import AcquisitionQuality
from lnt.types import ChannelMode, SessionType


class ComparisonKind(StrEnum):
    """Пять явно поддержанных классов сравнения."""

    LEGACY = "legacy"
    RC_1CH = "rc_1ch"
    RC_2CH = "rc_2ch"
    SELF_NOISE = "self_noise"
    LINE_QUALITY = "line_quality"


class SetupKind(StrEnum):
    """Стабильная идентичность CH1 setup без dataclass-эвристик."""

    LEGACY_MISSING = "legacy_missing"
    FLOATING_DIFFERENTIAL_RC_SHUNT_V1 = "floating_differential_rc_shunt_v1"
    SCOPE_INPUT_TERMINATED_V1 = "scope_input_terminated_v1"
    TRANSFORMER_LINE_PROBE_V1 = "transformer_line_probe_v1"


class FindingLevel(StrEnum):
    """Уровень решения по одному измерению матрицы."""

    OK = "ok"
    WARNING = "warning"
    BLOCK = "block"


@dataclass(frozen=True, slots=True, kw_only=True)
class AdcSetup:
    """Идентичность аппаратного диапазона АЦП."""

    range_code: int
    range_v: float


@dataclass(frozen=True, slots=True, kw_only=True)
class WelchGrid:
    """Параметры, полностью задающие сравниваемую сетку Welch."""

    window: str
    nperseg: int
    noverlap: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CalibrationIdentity:
    """Идентичность и факт применения калибровки АЦП."""

    identity: str | None
    applied: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextValue:
    """Одно контекстное поле и его роль в сопоставимости."""

    field: str
    value: str | float | bool
    comparable: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionDescriptor:
    """Полный научный дескриптор сессии для v2-сравнения."""

    session_id: str
    comparison_kind: ComparisonKind
    session_type: SessionType
    channel_mode: ChannelMode
    setup_kind: SetupKind
    probe_multiplier: float
    adc_setup: AdcSetup
    sample_rate_hz: float
    recipe_identity: str
    grid: WelchGrid
    baseline_identity: str | None
    calibration: CalibrationIdentity
    quality: AcquisitionQuality
    context_fields: tuple[ContextValue, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ComparabilityFinding:
    """Решение по измерению с точными именами затронутых полей."""

    dimension: str
    level: FindingLevel
    code: str
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ComparabilityReport:
    """Полная матрица решений; comparable истинно только без блоков."""

    findings: tuple[ComparabilityFinding, ...]

    @property
    def blocks(self) -> tuple[ComparabilityFinding, ...]:
        """Возвращает все блокирующие решения без скрытого отбрасывания."""
        return tuple(item for item in self.findings if item.level is FindingLevel.BLOCK)

    @property
    def warnings(self) -> tuple[ComparabilityFinding, ...]:
        """Возвращает все предупреждения."""
        return tuple(item for item in self.findings if item.level is FindingLevel.WARNING)

    @property
    def comparable(self) -> bool:
        """Разрешает численный результат только при пустом наборе blocks."""
        return not self.blocks


@dataclass(frozen=True, slots=True)
class ComparabilityBlockedError(ValueError):
    """Типизированный отказ численного сравнения."""

    reason_codes: tuple[str, ...]

    @override
    def __str__(self) -> str:
        """Возвращает русское сообщение с машинными кодами."""
        return f"сравнение заблокировано: {', '.join(self.reason_codes)}"


def require_numeric_comparison(report: ComparabilityReport) -> None:
    """Запрещает вычисление численного результата для неqualified пары."""
    if report.blocks:
        raise ComparabilityBlockedError(tuple(item.code for item in report.blocks))
