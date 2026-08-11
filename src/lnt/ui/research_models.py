"""Strict HTTP models for experiment and research boundaries."""
# ruff: noqa: D101, TC001

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from lnt.experiments import Experiment
from lnt.research import Hypothesis


class StrictModel(BaseModel):
    """Reject undeclared request fields and mutation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class ExperimentWrite(StrictModel):
    experiment: Experiment
    expected_revision: Annotated[int, Field(ge=0)]


class RunStart(StrictModel):
    run_id: str = Field(pattern=r"^[a-zA-Z0-9._-]+$")
    mode: Literal["real", "simulator"]
    seed: Annotated[int, Field(ge=0)] | None = None


class RunConfirm(StrictModel):
    actor: str = Field(min_length=1)
    auto_confirm: bool = False


class PairInput(StrictModel):
    unit_id: str = Field(min_length=1)
    value_a: float
    value_b: float


class AbaInput(StrictModel):
    unit_id: str = Field(min_length=1)
    value_a1: float
    value_b: float
    value_a2: float


class StatisticsRun(StrictModel):
    kind: Literal["ab", "aba", "repeated_blocks", "cohort", "longitudinal"]
    estimand: str = Field(min_length=1)
    units: str = Field(min_length=1)
    pairs: tuple[PairInput, ...] = Field(default=(), max_length=10_000)
    aba_units: tuple[AbaInput, ...] = Field(default=(), max_length=10_000)
    seed: Annotated[int, Field(ge=0)] = 0


class MetadataInput(StrictModel):
    key: str = Field(min_length=1)
    value: str | float | bool


class ObservationInput(StrictModel):
    observation_id: str = Field(min_length=1)
    timestamp: str | None
    source_offset: str
    location: str
    condition: str
    predictor: float | None
    outcome: float | None
    metadata: tuple[MetadataInput, ...] = ()


class TrendQuery(StrictModel):
    observations: tuple[ObservationInput, ...] = Field(max_length=10_000)
    minimum_n: Annotated[int, Field(ge=2, le=10_000)] = 5
    max_lag: Annotated[int, Field(ge=0, le=100)] = 3
    bootstrap_samples: Annotated[int, Field(ge=100, le=10_000)] = 1_000
    seed: Annotated[int, Field(ge=0)] = 0
    units: str = Field(min_length=1)


class HypothesisWrite(StrictModel):
    hypothesis: Hypothesis
    expected_revision: Annotated[int, Field(ge=0)]
