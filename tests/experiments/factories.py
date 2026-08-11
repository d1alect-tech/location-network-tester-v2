"""Типизированные фабрики тестовых экспериментов."""

from lnt.experiments import (
    Condition,
    ConfoundCheck,
    Experiment,
    ExperimentStatus,
    Factor,
    FactorKind,
    FactorValue,
    Intervention,
    Member,
    MultiplicityPolicy,
    Protocol,
    ProtocolDeclaration,
    ProtocolStep,
    Revision,
    StudyEstimand,
)
from lnt.features.bands import EstimandDirection


def make_experiment(protocol: Protocol = Protocol.AB, revision: int = 1) -> Experiment:
    """Создаёт минимальный полностью явный эксперимент."""
    return Experiment(
        experiment_schema_version=1,
        experiment_id="latency-study",
        title="Задержка A/B",
        question="Уменьшает ли B задержку?",
        status=ExperimentStatus.DRAFT,
        revision=revision,
        factors=(
            Factor(
                factor_id="firmware",
                kind=FactorKind.CATEGORICAL,
                levels=("a", "b"),
            ),
        ),
        conditions=(
            Condition(
                condition_id="condition-a",
                values=(FactorValue(factor_id="firmware", value="a"),),
            ),
            Condition(
                condition_id="condition-b",
                values=(FactorValue(factor_id="firmware", value="b"),),
            ),
        ),
        protocol=ProtocolDeclaration(
            kind=protocol,
            sampling_unit="subject",
            site_key="site_id",
            subject_key="subject_id",
            block_key="block_id",
            pairing_key="pair_id",
            assignment_scheme="balanced_explicit",
            order_scheme="declared_step_order",
            within_unit_aggregation="median",
            independence_assumptions=("Независимы только разные subject_id.",),
            minimum_n=2,
            multiplicity_policy=MultiplicityPolicy.HOLM,
        ),
        steps=(
            ProtocolStep(order=1, condition_id="condition-a", instruction="Измерить A"),
            ProtocolStep(order=2, condition_id="condition-b", instruction="Измерить B"),
        ),
        members=(
            Member(
                session_id="session-a",
                storage_ref="session-a",
                role="measurement",
                condition_id="condition-a",
                order=1,
                block_key="block-1",
                pairing_key="pair-1",
            ),
            Member(
                session_id="missing-session",
                storage_ref="missing-session",
                role="measurement",
                condition_id="condition-b",
                order=2,
                block_key="block-1",
                pairing_key="pair-1",
            ),
        ),
        interventions=(
            Intervention(
                intervention_id="firmware-b",
                occurred_at="2026-08-11T10:00:00.000Z",
                condition_id="condition-b",
            ),
        ),
        primary_estimands=(
            StudyEstimand(
                feature_key="latency_s",
                direction=EstimandDirection.LOWER,
                contrast="condition-b - condition-a",
            ),
        ),
        secondary_estimands=(),
        confound_checklist=(ConfoundCheck(key="temperature", checked=True, note="Стабильна"),),
        revision_history=(
            Revision(
                revision=revision,
                occurred_at="2026-08-11T10:00:00.000Z",
                actor="tester",
                reason="Создание протокола",
            ),
        ),
    )
