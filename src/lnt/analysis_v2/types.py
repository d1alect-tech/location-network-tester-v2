"""Typed contracts shared by the analysis v2 orchestration boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path  # noqa: TC003 - runtime dataclass field
from typing import Protocol, override

import numpy as np
from numpy.typing import NDArray

from lnt.analysis_store import AnalysisRecipe  # noqa: TC001 - runtime dataclass field
from lnt.scope_io import CancellationToken  # noqa: TC001 - runtime dataclass field

type Float32Array = NDArray[np.float32]


class SessionKind(StrEnum):
    """Session variants supported by analysis v2."""

    MEASUREMENT = "measurement"
    SELF_NOISE = "self_noise"
    LINE_QUALITY = "line_quality"
    CM_DM = "cm_dm"


@dataclass(frozen=True, slots=True)
class AnalysisCancelledError(Exception):
    """Typed cooperative cancellation acknowledgement."""

    branch: str

    @override
    def __str__(self) -> str:
        return f"анализ отменён на ветви {self.branch}"


@dataclass(frozen=True, slots=True, kw_only=True)
class BranchFailure:
    """Typed isolated failure of one optional branch."""

    branch: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BranchOutput:
    """Files produced by one branch."""

    files: dict[str, bytes]


@dataclass(frozen=True, slots=True, kw_only=True)
class BranchContext:
    """Trusted branch inputs and cancellation seam."""

    kind: SessionKind
    session_dir: Path
    sample_rate_hz: float
    channels: tuple[Float32Array, ...]
    recipe: AnalysisRecipe
    cancellation: CancellationToken

    def checkpoint(self) -> None:
        """Acknowledge cancellation at a bounded work boundary."""
        if self.cancellation.is_cancelled():
            raise AnalysisCancelledError("checkpoint")


class AnalysisEngine(Protocol):
    """Adapter contract for existing numerical engines."""

    def run_branch(self, name: str, context: BranchContext) -> BranchOutput:
        """Run one optional branch."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisRunResult:
    """Published analysis result or verified cache hit."""

    artifact_key: str
    artifact_dir: Path
    cache_hit: bool
    failures: tuple[BranchFailure, ...]
