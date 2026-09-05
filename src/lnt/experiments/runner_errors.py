"""Ошибки границ протокола: отказ авто-подтверждения, seed, состояние."""

from __future__ import annotations

from dataclasses import dataclass
from typing import override


@dataclass(frozen=True, slots=True)
class AutoConfirmationRejectedError(Exception):
    """Real physical interventions can never be auto-confirmed."""

    code: str = "real_intervention_auto_confirmation_forbidden"

    @override
    def __str__(self) -> str:
        return "физическое вмешательство нельзя подтвердить автоматически в реальном режиме"


@dataclass(frozen=True, slots=True)
class RandomizationSeedRequiredError(Exception):
    """A randomized protocol cannot start without a persisted seed."""

    code: str = "protocol_randomization_seed_required"

    @override
    def __str__(self) -> str:
        return "для рандомизации протокола требуется сохранённый seed"


@dataclass(frozen=True, slots=True)
class ProtocolStateError(Exception):
    """Persisted state violates a runner invariant."""

    code: str

    @override
    def __str__(self) -> str:
        return f"запуск протокола содержит недопустимое состояние: {self.code}"


__all__ = [
    "AutoConfirmationRejectedError",
    "ProtocolStateError",
    "RandomizationSeedRequiredError",
]
