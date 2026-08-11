"""Неизменяемые входы и маркированные результаты статистики."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, override

from lnt.comparability import InclusionState, MemberInclusion

if TYPE_CHECKING:
    from lnt.experiments import ProtocolDeclaration


class Estimator(StrEnum):
    """Имена оценок, зафиксированных протоколом."""

    PAIRED_DIFFERENCE = "paired_difference"
    QUALIFIED_WITHIN_RUN_CONTRAST = "qualified_within_run_contrast"
    BLOCK_PAIRED = "block_paired"
    DESCRIPTIVE_ONLY = "descriptive_only"


@dataclass(frozen=True, slots=True, kw_only=True)
class ExclusionRecord:
    """Исключённая единица и аудит-причина T30."""

    member_id: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisContext:
    """Объявленный протокол, иерархия и состояние доступных данных."""

    protocol: ProtocolDeclaration
    hierarchy: tuple[str, ...]
    missing_count: int
    member_states: tuple[MemberInclusion, ...] = ()

    @property
    def exclusions(self) -> tuple[ExclusionRecord, ...]:
        """Материализует только явно исключённые единицы."""
        return tuple(
            ExclusionRecord(member_id=item.member_id, reason=item.current.reason)
            for item in self.member_states
            if item.current.state is InclusionState.EXCLUDED
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultMetadata:
    """Обязательная маркировка каждого численного результата."""

    sampling_unit: str
    hierarchy: tuple[str, ...]
    n: int
    missing_count: int
    exclusions: tuple[ExclusionRecord, ...]
    estimator_name: str
    interval_method: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EffectInterval:
    """Двусторонний 95-процентный интервал."""

    low: float
    high: float
    confidence_level: float = 0.95


@dataclass(frozen=True, slots=True, kw_only=True)
class InferentialEffect:
    """Парная оценка с bootstrap-интервалом независимых единиц."""

    mean_effect: float
    median_effect: float
    robust_effect: float
    interval: EffectInterval
    stored_differences: tuple[float, ...]
    metadata: ResultMetadata


@dataclass(frozen=True, slots=True, kw_only=True)
class DescriptiveEffect:
    """Описательные дельты без доступного интервала."""

    mean_effect: float
    median_effect: float
    robust_effect: float
    stored_differences: tuple[float, ...]
    metadata: ResultMetadata
    interval: None = None


type EffectResult = InferentialEffect | DescriptiveEffect


@dataclass(frozen=True, slots=True)
class RawRepeatedSamplesError(TypeError):
    """Вместо агрегата независимой единицы переданы сырые повторы."""

    unit_id: str

    @override
    def __str__(self) -> str:
        return f"единица {self.unit_id}: требуются агрегаты, а не сырые повторы"


@dataclass(frozen=True, slots=True)
class PairingError(ValueError):
    """Ключи A и B не образуют одну независимую пару."""

    unit_id_a: str
    unit_id_b: str

    @override
    def __str__(self) -> str:
        return f"нарушена парность: {self.unit_id_a} != {self.unit_id_b}"


@dataclass(frozen=True, slots=True, kw_only=True)
class PairedUnit:
    """Ровно два агрегата одной независимой единицы."""

    unit_id_a: str
    unit_id_b: str
    value_a: float
    value_b: float


def paired_unit_from_aggregates(
    *,
    unit_id_a: str,
    unit_id_b: str,
    value_a: float | tuple[float, ...],
    value_b: float | tuple[float, ...],
) -> PairedUnit:
    """Разбирает boundary-вход и запрещает сырые внутригрупповые повторы."""
    match value_a, value_b:
        case float() | int(), float() | int():
            return PairedUnit(
                unit_id_a=unit_id_a,
                unit_id_b=unit_id_b,
                value_a=float(value_a),
                value_b=float(value_b),
            )
        case _:
            raise RawRepeatedSamplesError(unit_id_a)


@dataclass(frozen=True, slots=True, kw_only=True)
class AbaUnit:
    """Три агрегата A1/B/A2 одной независимой единицы."""

    unit_id: str
    value_a1: float
    value_b: float
    value_a2: float


@dataclass(frozen=True, slots=True, kw_only=True)
class QualifiedWithinRunContrast:
    """Некausalный A/B/A-контраст с отдельно сохранённым дрейфом."""

    effect: EffectResult
    drift: EffectResult
    metadata: ResultMetadata
    result_kind: str = "qualified within-run contrast"
    description_ru: str = "Квалифицированный внутрисерийный контраст; причинный вывод недоступен."


@dataclass(frozen=True, slots=True, kw_only=True)
class ContrastRefusal:
    """Типизированный отказ A/B/A при неприемлемом A-дрейфе."""

    reason_code: str
    drift_effect: float
    contrast_effect: float
    metadata: ResultMetadata
    result_kind: str = "qualified within-run contrast"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtocolInferenceDeclaration:
    """Явное дополнение для разрешённой cohort/longitudinal оценки."""

    independent_units_declared: bool
    predefined_estimator: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureValue:
    """Один линейный feature/band/harmonic estimand."""

    key: str
    value: float


@dataclass(frozen=True, slots=True, kw_only=True)
class FeaturePair:
    """Парные таблицы признаков одной независимой единицы."""

    unit_id_a: str
    unit_id_b: str
    values_a: tuple[FeatureValue, ...]
    values_b: tuple[FeatureValue, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureEffect:
    """Маркированная оценка одной строки таблицы признаков."""

    key: str
    effect: EffectResult


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectrumPair:
    """Парные линейные спектры одной независимой единицы."""

    unit_id_a: str
    unit_id_b: str
    values_a: tuple[float, ...]
    values_b: tuple[float, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectralCluster:
    """Непрерывный диапазон соседних значимых бинов."""

    low_hz: float
    high_hz: float
    bin_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectralResult:
    """Сохранённые bin-wise эффекты, BH q-values и кластеры."""

    frequencies_hz: tuple[float, ...]
    effects: tuple[EffectResult, ...]
    p_values: tuple[float, ...]
    q_values: tuple[float, ...]
    clusters: tuple[SpectralCluster, ...]
    metadata: ResultMetadata
