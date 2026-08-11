"""Перечисления и вложенные значения experiment schema 1."""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from lnt.features.bands import EstimandDirection


class FrozenModel(BaseModel):
    """Общая строгая конфигурация persisted-моделей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class ExperimentStatus(StrEnum):
    """Жизненный цикл эксперимента."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Protocol(StrEnum):
    """Поддерживаемые планы измерений."""

    AB = "ab"
    ABA = "aba"
    REPEATED_BLOCKS = "repeated_blocks"
    COHORT = "cohort"
    LONGITUDINAL = "longitudinal"


class FactorKind(StrEnum):
    """Тип явно объявленного фактора."""

    CATEGORICAL = "categorical"
    CONTINUOUS = "continuous"
    BOOLEAN = "boolean"


class MultiplicityPolicy(StrEnum):
    """Политика множественных проверок."""

    NONE = "none"
    HOLM = "holm"
    BONFERRONI = "bonferroni"
    FDR_BH = "fdr_bh"


class Factor(FrozenModel):
    """Фактор и допустимые уровни без разбора label сессии."""

    factor_id: str = Field(min_length=1)
    kind: FactorKind
    levels: tuple[str | float | bool, ...] = Field(min_length=1)


class FactorValue(FrozenModel):
    """Явное значение фактора в condition."""

    factor_id: str = Field(min_length=1)
    value: str | float | bool


class Condition(FrozenModel):
    """Именованная комбинация значений факторов."""

    condition_id: str = Field(min_length=1)
    values: tuple[FactorValue, ...] = Field(min_length=1)


class ProtocolDeclaration(FrozenModel):
    """Полный protocol-to-estimator контракт."""

    kind: Protocol
    sampling_unit: str = Field(min_length=1)
    site_key: str = Field(min_length=1)
    subject_key: str = Field(min_length=1)
    block_key: str = Field(min_length=1)
    pairing_key: str = Field(min_length=1)
    assignment_scheme: str = Field(min_length=1)
    order_scheme: str = Field(min_length=1)
    within_unit_aggregation: str = Field(min_length=1)
    independence_assumptions: tuple[str, ...] = Field(min_length=1)
    minimum_n: int = Field(ge=2)
    multiplicity_policy: MultiplicityPolicy


class ProtocolStep(FrozenModel):
    """Один строго упорядоченный шаг протокола."""

    order: int = Field(ge=1)
    condition_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class Member(FrozenModel):
    """Явное членство сессии и назначение condition."""

    session_id: str = Field(min_length=1)
    storage_ref: str = Field(min_length=1)
    role: str = Field(min_length=1)
    condition_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    block_key: str | None = None
    pairing_key: str | None = None


class Intervention(FrozenModel):
    """Временная отметка изменения condition."""

    intervention_id: str = Field(min_length=1)
    occurred_at: str = Field(pattern=r"Z$")
    condition_id: str = Field(min_length=1)


class StudyEstimand(FrozenModel):
    """Оцениваемый feature, contrast и направление интерпретации."""

    feature_key: str = Field(min_length=1)
    direction: EstimandDirection
    contrast: str = Field(min_length=1)


class ConfoundCheck(FrozenModel):
    """Явный пункт проверки смешивающего фактора."""

    key: str = Field(min_length=1)
    checked: bool
    note: str | None = None


class Revision(FrozenModel):
    """Аудит-метаданные одной принятой revision."""

    revision: int = Field(ge=1)
    occurred_at: str = Field(pattern=r"Z$")
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
