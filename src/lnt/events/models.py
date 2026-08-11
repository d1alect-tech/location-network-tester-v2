"""Typed candidate-event inventory and JSON-safe payload shapes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from lnt.events.settings import DetectionSettings, DetectionSettingsDict

Float64Array = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


class Polarity(StrEnum):
    """Observed sign composition of a candidate event."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    BIPOLAR = "bipolar"


class QualificationStatus(StrEnum):
    """Whether a candidate meets all persisted reporting thresholds."""

    QUALIFIED = "qualified"
    BELOW_MINIMUM_SNR = "below_minimum_snr"
    TOO_SHORT = "too_short"


class CandidateEventDict(TypedDict):
    """JSON-safe candidate-event payload."""

    start_sample: int
    end_sample: int
    peak_sample: int
    start_time_s: float
    end_time_s: float
    peak_time_s: float
    peak_value_v: float
    polarity: str
    dominant_band: str | None
    excess_energy_v2_s: float
    snr: float
    qualification_status: str
    boundary: bool
    clipped: bool


class GapDict(TypedDict):
    """JSON-safe unqualified interval payload."""

    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float


class EventInventoryDict(TypedDict):
    """JSON-safe complete inventory payload."""

    schema_version: int
    language: str
    sample_rate_hz: float
    sample_count: int
    settings_hash: str
    settings: DetectionSettingsDict
    baseline_qualification_rule_id: str | None
    events: list[CandidateEventDict]
    unqualified_gaps: list[GapDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class BaselineFloor:
    """Prevalidated compatible baseline noise sigma and per-sample qualification."""

    noise_sigma_v: Float64Array
    qualified: BoolArray
    qualification_rule_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateEvent:
    """A detected signal candidate; it is explicitly not a causal conclusion."""

    start_sample: int
    end_sample: int
    peak_sample: int
    start_time_s: float
    end_time_s: float
    peak_time_s: float
    peak_value_v: float
    polarity: Polarity
    dominant_band: str | None
    excess_energy_v2_s: float
    snr: float
    qualification_status: QualificationStatus
    boundary: bool
    clipped: bool

    def to_dict(self) -> CandidateEventDict:
        """Serialize the candidate to JSON-safe primitives."""
        return {
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "peak_sample": self.peak_sample,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "peak_time_s": self.peak_time_s,
            "peak_value_v": self.peak_value_v,
            "polarity": self.polarity.value,
            "dominant_band": self.dominant_band,
            "excess_energy_v2_s": self.excess_energy_v2_s,
            "snr": self.snr,
            "qualification_status": self.qualification_status.value,
            "boundary": self.boundary,
            "clipped": self.clipped,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class UnqualifiedGap:
    """Inclusive sample interval where a trustworthy noise floor was unavailable."""

    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float

    def to_dict(self) -> GapDict:
        """Serialize the gap to JSON-safe primitives."""
        return {
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EventInventory:
    """Deterministic inventory labelled in Russian as event candidates."""

    schema_version: int
    sample_rate_hz: float
    sample_count: int
    settings_hash: str
    settings: DetectionSettings
    baseline_qualification_rule_id: str | None
    events: tuple[CandidateEvent, ...]
    unqualified_gaps: tuple[UnqualifiedGap, ...]

    def to_dict(self) -> EventInventoryDict:
        """Serialize the complete reproducible inventory."""
        return {
            "schema_version": self.schema_version,
            "language": "кандидаты событий",
            "sample_rate_hz": self.sample_rate_hz,
            "sample_count": self.sample_count,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "baseline_qualification_rule_id": self.baseline_qualification_rule_id,
            "events": [event.to_dict() for event in self.events],
            "unqualified_gaps": [gap.to_dict() for gap in self.unqualified_gaps],
        }
