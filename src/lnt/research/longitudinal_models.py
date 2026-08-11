"""Типы описательного продольного анализа."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

LOW_N_THRESHOLD: Final = 10


class CorrelationStatus(StrEnum):
    """Доступность численной корреляции."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    CORRELATION_UNAVAILABLE = "correlation_unavailable"


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadataValue:
    """Доступное типизированное metadata/context значение."""

    key: str
    value: str | float | bool


@dataclass(frozen=True, slots=True, kw_only=True)
class Observation:
    """Одна независимая наблюдаемая единица."""

    observation_id: str
    timestamp: str | None
    source_offset: str
    location: str
    condition: str
    predictor: float | None
    outcome: float | None
    metadata: tuple[MetadataValue, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisRequest:
    """Воспроизводимые параметры описательного анализа."""

    minimum_n: int = 5
    max_lag: int = 3
    bootstrap_samples: int = 1_000
    seed: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class Gap:
    """Видимый интервал между соседними наблюдениями."""

    after_utc: str
    before_utc: str
    duration_seconds: float


@dataclass(frozen=True, slots=True, kw_only=True)
class DataQuality:
    """Явная обработка грязных временных данных."""

    input_count: int
    usable_count: int
    missing_timestamp_count: int
    duplicate_count: int
    dedupe_policy: str
    gaps: tuple[Gap, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Trend:
    """Среднее outcome внутри одной описательной группы."""

    group_dimension: str
    group_value: str
    n: int
    missing_count: int
    mean: float | None
    result_kind: str = "descriptive_exploratory"
    exploratory: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrelationInterval:
    """Процентильный bootstrap-интервал коэффициента."""

    low: float
    high: float


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrelationFinding:
    """Некausal описательная ранговая связь."""

    lag: int
    status: CorrelationStatus
    coefficient: float | None
    interval: CorrelationInterval | None
    n: int
    missing_count: int
    p_value: float | None
    q_value: float | None
    multiple_testing: str
    confound_columns: tuple[str, ...]
    confound_warning: str
    result_kind: str = "descriptive_exploratory"
    exploratory: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class LongitudinalResult:
    """Полный результат только описательного исследования."""

    trends: tuple[Trend, ...]
    correlations: tuple[CorrelationFinding, ...]
    data_quality: DataQuality
    normalized_timestamps: tuple[datetime, ...]
    result_kind: str = "descriptive_exploratory"
