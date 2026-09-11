"""Immutable shared records for characterization results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from lnt.characterization.errors import CharacterizationError


class Status(StrEnum):
    """Availability of a family result."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class Unit(StrEnum):
    """Closed persisted unit vocabulary."""

    V = "V"
    V2 = "V^2"
    V2_S = "V^2 s"
    HZ = "Hz"
    S = "s"
    RAD = "rad"
    RATIO = "ratio"
    COUNT = "count"
    V2_PER_HZ = "V^2/Hz"


class SignalPlane(StrEnum):
    """Measured plane described by a family."""

    CH1_SCOPE_INPUT = "ch1_scope_input"
    CH2_TRANSFORMER_SECONDARY = "ch2_transformer_secondary"
    CROSS_CHANNEL = "cross_channel_measured_planes"


_UNIT_SUFFIX = {
    Unit.V: "_v",
    Unit.V2: "_v2",
    Unit.V2_S: "_v2_s",
    Unit.HZ: "_hz",
    Unit.S: "_s",
    Unit.RAD: "_rad",
    Unit.V2_PER_HZ: "_v2_per_hz",
}


def validate_unit_name(name: str, unit: Unit) -> None:
    """Require SI suffixes on persisted numeric names."""
    suffix = _UNIT_SUFFIX.get(unit)
    if not name or (suffix is not None and not name.endswith(suffix)):
        raise CharacterizationError("unit_suffix", f"{name!r} does not match {unit.value}")


def _finite(value: float, field: str) -> None:
    if not math.isfinite(value):
        raise CharacterizationError("nonfinite", f"{field} must be finite")


@dataclass(frozen=True, slots=True, kw_only=True)
class Window:
    """Declared analysis window."""

    kind: str
    duration_s: float | None
    sample_count: int | None
    overlap_fraction: float

    def __post_init__(self) -> None:
        """Validate declared window geometry."""
        if not self.kind or not 0 <= self.overlap_fraction < 1:
            raise CharacterizationError("window", "invalid window")
        if self.duration_s is not None:
            _finite(self.duration_s, "window.duration_s")
            if self.duration_s <= 0:
                raise CharacterizationError("window", "duration_s must be positive")
        if self.sample_count is not None and self.sample_count <= 0:
            raise CharacterizationError("window", "sample_count must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class Band:
    """Closed measured frequency band."""

    low_hz: float
    high_hz: float

    def __post_init__(self) -> None:
        """Validate finite ordered band edges."""
        _finite(self.low_hz, "band.low_hz")
        _finite(self.high_hz, "band.high_hz")
        if self.low_hz < 0 or self.high_hz <= self.low_hz:
            raise CharacterizationError("band", "invalid frequency band")


@dataclass(frozen=True, slots=True, kw_only=True)
class Filter:
    """Declared signal filter."""

    kind: str
    order: int | None
    phase: str

    def __post_init__(self) -> None:
        """Validate the filter declaration."""
        if not self.kind or not self.phase or (self.order is not None and self.order <= 0):
            raise CharacterizationError("filter", "invalid filter")


@dataclass(frozen=True, slots=True, kw_only=True)
class Inference:
    """Fixed single-session inference boundary."""

    estimate_scope: str = "single_session_descriptive"
    population_inference: str = "withheld"
    reason_code: str = "independent_capture_units_required"

    def __post_init__(self) -> None:
        """Reject population inference from one capture."""
        if (
            self.estimate_scope != "single_session_descriptive"
            or self.population_inference != "withheld"
            or self.reason_code != "independent_capture_units_required"
        ):
            raise CharacterizationError("inference", "population inference is not permitted")


@dataclass(frozen=True, slots=True, kw_only=True)
class Support:
    """Full observed and stored support accounting."""

    start_s: float
    end_s: float
    duration_s: float
    sample_count: int
    observation_count: int
    missing_count: int
    stored_count: int
    selection_rule: str

    def __post_init__(self) -> None:
        """Validate interval arithmetic and all support counts."""
        for field, value in (
            ("start_s", self.start_s),
            ("end_s", self.end_s),
            ("duration_s", self.duration_s),
        ):
            _finite(value, f"support.{field}")
        if (
            self.start_s < 0
            or self.end_s < self.start_s
            or not math.isclose(
                self.duration_s, self.end_s - self.start_s, rel_tol=0.0, abs_tol=1e-12
            )
        ):
            raise CharacterizationError("support_interval", "support interval is inconsistent")
        counts = (self.sample_count, self.observation_count, self.missing_count, self.stored_count)
        if (
            any(value < 0 for value in counts)
            or self.sample_count != self.observation_count + self.missing_count
            or self.stored_count > self.observation_count
            or not self.selection_rule
            or (self.selection_rule == "all" and self.stored_count != self.observation_count)
        ):
            raise CharacterizationError("support_counts", "support counts are inconsistent")


@dataclass(frozen=True, slots=True, kw_only=True)
class Qc:
    """Family quality-control outcome."""

    passed: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate stable unique quality-control reasons."""
        if any(not code for code in self.reason_codes) or len(set(self.reason_codes)) != len(
            self.reason_codes
        ):
            raise CharacterizationError("qc", "QC reason codes must be unique and nonempty")


@dataclass(frozen=True, slots=True, kw_only=True)
class ScalarSummary:
    """Finite scalar used by characterization comparisons."""

    name: str
    value: float
    unit: Unit
    circular: bool = False

    def __post_init__(self) -> None:
        """Validate finiteness, unit suffix, and circular units."""
        validate_unit_name(self.name, self.unit)
        _finite(self.value, f"summary.{self.name}")
        if self.circular and self.unit is not Unit.RAD:
            raise CharacterizationError("circular_unit", "circular summaries must use radians")
