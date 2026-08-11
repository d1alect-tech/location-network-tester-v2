"""Закрытая таблица допустимых protocol-to-estimator переходов."""

from dataclasses import dataclass
from typing import Final, override

from lnt.experiments import Protocol, ProtocolDeclaration

from .models import Estimator, ProtocolInferenceDeclaration

PROTOCOL_TO_ESTIMATOR: Final[dict[Protocol, tuple[Estimator, ...]]] = {
    Protocol.AB: (Estimator.PAIRED_DIFFERENCE,),
    Protocol.ABA: (Estimator.QUALIFIED_WITHIN_RUN_CONTRAST,),
    Protocol.REPEATED_BLOCKS: (Estimator.BLOCK_PAIRED,),
    Protocol.COHORT: (Estimator.DESCRIPTIVE_ONLY,),
    Protocol.LONGITUDINAL: (Estimator.DESCRIPTIVE_ONLY,),
}


@dataclass(frozen=True, slots=True)
class EstimatorRejectedError(ValueError):
    """Протокол не разрешает запрошенную оценку."""

    protocol: Protocol
    estimator: str
    reason_code: str

    @override
    def __str__(self) -> str:
        return (
            f"протокол {self.protocol.value}: оценка {self.estimator!r} отклонена "
            f"({self.reason_code})"
        )


def authorize_estimator(
    protocol: ProtocolDeclaration,
    estimator: Estimator | str,
    *,
    inference: ProtocolInferenceDeclaration | None = None,
) -> Estimator | str:
    """Возвращает только разрешённую протоколом оценку или typed rejection."""
    requested = estimator.value if isinstance(estimator, Estimator) else estimator
    allowed = PROTOCOL_TO_ESTIMATOR[protocol.kind]
    if allowed != (Estimator.DESCRIPTIVE_ONLY,):
        if estimator not in allowed:
            raise EstimatorRejectedError(
                protocol.kind,
                requested,
                "estimator_not_allowed_for_protocol",
            )
        return estimator
    if (
        inference is None
        or not inference.independent_units_declared
        or not inference.predefined_estimator
        or requested != inference.predefined_estimator
    ):
        raise EstimatorRejectedError(protocol.kind, requested, "descriptive_only_protocol")
    return requested
