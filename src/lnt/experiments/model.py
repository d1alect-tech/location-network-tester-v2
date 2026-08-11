"""Корневая модель и строгий разбор experiment schema 1."""

from collections.abc import Mapping
from typing import Final, Self

from pydantic import Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from lnt.context.json_codec import JsonValue, decode_object, encode_canonical
from lnt.experiments.errors import ExperimentValidationError
from lnt.experiments.values import (
    Condition,
    ConfoundCheck,
    ExperimentStatus,
    Factor,
    FrozenModel,
    Intervention,
    Member,
    ProtocolDeclaration,
    ProtocolStep,
    Revision,
    StudyEstimand,
)

EXPERIMENT_SCHEMA_VERSION: Final = 1
_PROTOCOL_REASONS: Final = {
    "sampling_unit": "sampling_unit_missing",
    "pairing_key": "pairing_key_missing",
    "site_key": "hierarchy_key_missing",
    "subject_key": "hierarchy_key_missing",
    "block_key": "hierarchy_key_missing",
    "within_unit_aggregation": "aggregation_missing",
    "minimum_n": "minimum_n_missing",
    "independence_assumptions": "independence_missing",
    "assignment_scheme": "assignment_missing",
    "order_scheme": "order_missing",
    "multiplicity_policy": "multiplicity_policy_missing",
}


class Experiment(FrozenModel):
    """Полный auditable snapshot эксперимента."""

    experiment_schema_version: int
    experiment_id: str = Field(pattern=r"^[a-z0-9._-]+$")
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    status: ExperimentStatus
    revision: int = Field(ge=1)
    factors: tuple[Factor, ...] = Field(min_length=1)
    conditions: tuple[Condition, ...] = Field(min_length=1)
    protocol: ProtocolDeclaration
    steps: tuple[ProtocolStep, ...] = Field(min_length=1)
    members: tuple[Member, ...] = Field(min_length=1)
    interventions: tuple[Intervention, ...]
    primary_estimands: tuple[StudyEstimand, ...] = Field(min_length=1)
    secondary_estimands: tuple[StudyEstimand, ...]
    confound_checklist: tuple[ConfoundCheck, ...]
    revision_history: tuple[Revision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_invariants(self) -> Self:
        """Отвергает неоднозначные IDs, ordinals и ссылки."""
        if self.experiment_schema_version != EXPERIMENT_SCHEMA_VERSION:
            raise PydanticCustomError("unsupported_schema_version", "unsupported_schema_version")
        factor_ids = [item.factor_id for item in self.factors]
        condition_ids = [item.condition_id for item in self.conditions]
        if len(set(factor_ids)) != len(factor_ids):
            raise PydanticCustomError("duplicate_factor_id", "duplicate_factor_id")
        if len(set(condition_ids)) != len(condition_ids):
            raise PydanticCustomError("duplicate_condition_id", "duplicate_condition_id")
        if [item.order for item in self.steps] != list(range(1, len(self.steps) + 1)):
            raise PydanticCustomError("invalid_step_order", "invalid_step_order")
        member_keys = [(item.role, item.order) for item in self.members]
        if len(set(member_keys)) != len(member_keys):
            raise PydanticCustomError("duplicate_member_role_order", "duplicate_member_role_order")
        if any(item.condition_id not in condition_ids for item in self.steps + self.members):
            raise PydanticCustomError("unknown_condition_reference", "unknown_condition_reference")
        if self.revision_history[-1].revision != self.revision:
            raise PydanticCustomError("revision_history_mismatch", "revision_history_mismatch")
        return self

    def to_mapping(self) -> dict[str, JsonValue]:
        """Возвращает JSON-safe полное представление."""
        return decode_object(self.model_dump_json(), "experiment.json")


def experiment_from_mapping(raw: Mapping[str, JsonValue]) -> Experiment:
    """Строго разбирает persisted experiment и локализует ошибку."""
    protocol = raw.get("protocol")
    if isinstance(protocol, dict):
        for field, reason_code in _PROTOCOL_REASONS.items():
            if field not in protocol:
                raise ExperimentValidationError(reason_code, f"protocol.{field} не объявлен")
    try:
        return Experiment.model_validate(raw)
    except ValidationError as error:
        text = str(error)
        reason_code = next(
            (
                code
                for code in ("duplicate_member_role_order", "unknown_condition_reference")
                if code in text
            ),
            "experiment_schema_invalid",
        )
        raise ExperimentValidationError(
            reason_code, "experiment.json не прошёл строгую проверку"
        ) from error


def experiment_to_canonical_json(experiment: Experiment) -> bytes:
    """Возвращает канонические байты schema 1."""
    return encode_canonical(experiment.to_mapping(), "experiment.json")
