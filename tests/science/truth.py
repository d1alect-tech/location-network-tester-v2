"""Independent analytic truth values and strict comparison helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import override


@dataclass(frozen=True, slots=True)
class TruthMismatchError(AssertionError):
    """A measured estimand lies outside its independently justified tolerance."""

    measured: float
    expected: float
    tolerance: float
    rationale: str

    @override
    def __str__(self) -> str:
        return (
            f"measured={self.measured:g}, expected={self.expected:g}, "
            f"tolerance={self.tolerance:g}: {self.rationale}"
        )


def verify_scalar(
    measured: float,
    *,
    expected: float,
    absolute_tolerance: float,
    rationale: str,
) -> None:
    """Reject non-finite or out-of-tolerance results with scientific context."""
    if not rationale.strip():
        raise TruthMismatchError(measured, expected, absolute_tolerance, "missing rationale")
    if not math.isfinite(measured) or abs(measured - expected) > absolute_tolerance:
        raise TruthMismatchError(measured, expected, absolute_tolerance, rationale)
