"""Строгие пользовательские записи гипотез."""

from enum import StrEnum
from typing import ClassVar, Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


class FrozenModel(BaseModel):
    """Запрещает неявные поля и мутацию persisted-моделей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class ExpectedDirection(StrEnum):
    """Ожидаемое пользователем направление наблюдаемой связи."""

    INCREASE = "increase"
    DECREASE = "decrease"
    NO_DIRECTION = "no_direction"


class HypothesisStatus(StrEnum):
    """Неcausal пользовательская оценка состояния гипотезы."""

    DRAFT = "draft"
    TESTING = "testing"
    CONSISTENT_WITH_OBSERVATIONS = "consistent_with_observations"
    NOT_CONSISTENT = "not_consistent"
    INCONCLUSIVE = "inconclusive"


class LinkedEstimand(FrozenModel):
    """Явная ссылка на эксперимент и его estimand."""

    experiment_id: str = Field(min_length=1)
    estimand: str = Field(min_length=1)


class EvidenceReference(FrozenModel):
    """Типизированная ссылка на уже вычисленный результат."""

    result_id: str = Field(min_length=1)
    result_kind: str = Field(pattern=r"^descriptive_")


class Revision(FrozenModel):
    """Автор одной явной пользовательской revision."""

    revision: int = Field(ge=1)
    occurred_at: str = Field(pattern=r"Z$")
    actor: str = Field(pattern=r"^user:")
    reason: str = Field(min_length=1)


class Hypothesis(FrozenModel):
    """Только пользовательская теория с двумя направлениями evidence."""

    schema_version: int
    hypothesis_id: str = Field(pattern=r"^[a-z0-9._-]+$")
    revision: int = Field(ge=1)
    statement: str = Field(min_length=1)
    expected_direction: ExpectedDirection
    mechanism: str = Field(min_length=1)
    linked_estimands: tuple[LinkedEstimand, ...]
    confounds: tuple[str, ...]
    evidence_for: tuple[EvidenceReference, ...]
    evidence_against: tuple[EvidenceReference, ...]
    status: HypothesisStatus
    revision_history: tuple[Revision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_revision(self) -> Self:
        """Связывает текущую revision с явным user audit event."""
        valid = (
            self.schema_version == 1
            and self.revision_history[-1].revision == self.revision
            and tuple(item.revision for item in self.revision_history)
            == tuple(range(1, self.revision + 1))
        )
        if not valid:
            raise PydanticCustomError("revision_history", "revision_history")
        return self


def hypothesis_status_label(status: HypothesisStatus) -> str:
    """Возвращает неcausal русскую подпись статуса."""
    labels: Final = {
        HypothesisStatus.DRAFT: "черновик",
        HypothesisStatus.TESTING: "проверяется",
        HypothesisStatus.CONSISTENT_WITH_OBSERVATIONS: "согласуется с наблюдениями",
        HypothesisStatus.NOT_CONSISTENT: "не согласуется с наблюдениями",
        HypothesisStatus.INCONCLUSIVE: "недостаточно данных",
    }
    return labels[status]
