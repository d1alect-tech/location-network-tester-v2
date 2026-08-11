"""Строгие модели научного отчёта schema 1."""

from enum import StrEnum
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lnt.statistics.models import DescriptiveEffect, InferentialEffect


class ReportModel(BaseModel):
    """Общая неизменяемая граница report schema 1."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class QcState(StrEnum):
    """Состояние T30 для одного участника анализа."""

    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNAVAILABLE = "unavailable"


class PlaneKind(StrEnum):
    """Раздельные измерительные плоскости."""

    SOURCE = "source"
    SECONDARY = "secondary"
    PRIMARY = "primary"


class Provenance(ReportModel):
    """Идентичность данных, рецепта и кода."""

    session_ids: tuple[str, ...] = Field(min_length=1)
    experiment_id: str | None
    recipe_sha256s: tuple[str, ...]
    code_identity: str = Field(min_length=1)
    created_at: str = Field(pattern=r"Z$")


class SetupContext(ReportModel):
    """Снимок установки и контекста измерения."""

    ch1_setup: str = Field(min_length=1)
    profile: str | None
    metadata_snapshot_refs: tuple[str, ...]
    notes: tuple[str, ...] = ()


class QcDecision(ReportModel):
    """Аудируемое решение включения T30."""

    member_id: str = Field(min_length=1)
    state: QcState
    reason: str = Field(min_length=1)


class RecipeReference(ReportModel):
    """Использованный рецепт и связанный артефакт."""

    recipe_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str = Field(min_length=1)
    artifact_key: str = Field(min_length=1)


class ResultMetadataModel(ReportModel):
    """Полная обязательная маркировка T31."""

    sampling_unit: str
    hierarchy: tuple[str, ...]
    n: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    exclusions: tuple[QcDecision, ...]
    estimator_name: str
    interval_method: str


class IntervalModel(ReportModel):
    """Численный интервал и его уровень доверия."""

    low: float
    high: float
    confidence_level: float


class EstimandResult(ReportModel):
    """Нормализованный inferential или descriptive результат T31."""

    result_kind: Literal["inferential", "descriptive"]
    mean_effect: float
    median_effect: float
    robust_effect: float
    interval: IntervalModel | None
    stored_differences: tuple[float, ...]
    metadata: ResultMetadataModel


class MeasurementPlane(ReportModel):
    """Одна явно названная измерительная плоскость."""

    kind: PlaneKind
    available: bool
    reason_code: str | None = None
    session_id: str
    member_id: str
    unit: str
    estimator: str
    n: int = Field(ge=0)
    values: tuple[InferentialEffect | DescriptiveEffect, ...] = ()

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        """Требует причину для недоступной плоскости."""
        if self.available and self.reason_code is not None:
            raise ValueError("available plane cannot have reason_code")
        if not self.available and not self.reason_code:
            raise ValueError("unavailable plane requires reason_code")
        return self


class PlaneReport(ReportModel):
    """Сериализуемая плоскость с нормализованными результатами."""

    kind: PlaneKind
    available: bool
    reason_code: str | None
    session_id: str
    member_id: str
    unit: str
    estimator: str
    n: int
    values: tuple[EstimandResult, ...]


class DriftConfounds(ReportModel):
    """A/B/A-дрейф и объявленные T32 confound-колонки."""

    aba_label: str
    drift_value: float | None
    drift_unit: str
    confound_columns: tuple[str, ...]


class EventSummary(ReportModel):
    """Сводка полного T23 inventory кандидатов событий."""

    candidate_count: int = Field(ge=0)
    qualified_count: int = Field(ge=0)
    unqualified_gap_count: int = Field(ge=0)
    unit: str
    estimator: str
    n: int = Field(ge=0)


class Limitation(ReportModel):
    """Машиночитаемое ограничение с русским пояснением."""

    code: str
    detail: str
    source: Literal["automatic", "protocol"]


class HypothesisLink(ReportModel):
    """Ссылка на гипотезу и её неcausal статус."""

    hypothesis_id: str
    status: str
    status_label: str


class ReportInputs(ReportModel):
    """Типизированные уже вычисленные входы чистого builder-а."""

    provenance: Provenance
    setup: SetupContext
    qc: tuple[QcDecision, ...]
    recipes: tuple[RecipeReference, ...]
    primary_estimands: tuple[InferentialEffect | DescriptiveEffect, ...]
    secondary_estimands: tuple[InferentialEffect | DescriptiveEffect, ...]
    planes: tuple[MeasurementPlane, ...]
    drift_confounds: DriftConfounds
    events: EventSummary | None
    hypotheses: tuple[HypothesisLink, ...]
    protocol_qualifications: tuple[str, ...] = Field(min_length=1)
    missing_artifacts: tuple[str, ...] = ()


class ReportSchema1(ReportModel):
    """Замороженный корневой контракт научного отчёта LNT."""

    schema_version: Literal[1] = 1
    provenance: Provenance
    setup_context: SetupContext
    qc_exclusions: tuple[QcDecision, ...]
    recipes_used: tuple[RecipeReference, ...]
    primary_estimands: tuple[EstimandResult, ...]
    secondary_estimands: tuple[EstimandResult, ...]
    planes: tuple[PlaneReport, ...] = Field(min_length=3, max_length=3)
    drift_confounds: DriftConfounds
    events_summary: EventSummary | None
    limitations: tuple[Limitation, ...] = Field(min_length=1)
    linked_hypotheses: tuple[HypothesisLink, ...]

    @model_validator(mode="after")
    def validate_planes(self) -> Self:
        """Замораживает порядок source, secondary, primary в schema 1."""
        expected = (PlaneKind.SOURCE, PlaneKind.SECONDARY, PlaneKind.PRIMARY)
        if tuple(plane.kind for plane in self.planes) != expected:
            raise ValueError("planes must be source, secondary, primary")
        return self
