"""F11 fixed_phase_band_f15_mode_empirical_distributions: записи и константы."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.records import Status, Unit

if TYPE_CHECKING:
    from lnt.events.models import Polarity

METHOD: Final = "fixed_phase_band_f15_mode_empirical_distributions"
BANDS_HZ: Final = ((3000.0, 10000.0), (10000.0, 50000.0), (50000.0, 200000.0))
QUANTITIES: Final = (
    "absolute_peak_v",
    "duration_s",
    "dominant_frequency_hz",
    "v2_s",
    "polarity_counts",
)
QUANTITY_COUNT: Final = 4
CDF_PROBABILITIES: Final = np.linspace(0.0, 1.0, 129)
MINIMUM_SUPPORT: Final = 20
MAXIMUM_EVENTS: Final = 4096
QUANTITY_UNITS: Final = (Unit.V, Unit.S, Unit.HZ, Unit.V2_S)
PERSISTED_QUANTITY_NAMES: Final = (
    "f11_absolute_peak_v",
    "f11_duration_s",
    "f11_dominant_frequency_hz",
    "f11_v2_s",
)
QUANTILES: Final = (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)

PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
INSUFFICIENT_SUPPORT: Final = "insufficient_support"
BIN_EMPTY: Final = "bin_empty"
DOMINANT_BAND_UNAVAILABLE: Final = "dominant_band_unavailable"
MODE_UNAVAILABLE: Final = "mode_unavailable"
MODE_ASSIGNMENT_UNAVAILABLE: Final = "mode_assignment_unavailable"
EVENT_LIMIT: Final = "event_limit"
GAPS_PRESENT: Final = "gaps_present"

DECLARED_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    INSUFFICIENT_SUPPORT,
    BIN_EMPTY,
    DOMINANT_BAND_UNAVAILABLE,
    MODE_UNAVAILABLE,
    MODE_ASSIGNMENT_UNAVAILABLE,
    EVENT_LIMIT,
    GAPS_PRESENT,
)

CLAIM_BOUNDARY: Final = (
    "conditional descriptions of one session; F15 modes are deterministic measured-feature "
    "groups and polarity is an event attribute; no physical source, operating state, "
    "population effect, or causal effect is established"
)

type FeatureVector = tuple[float, ...]
type CellKey = tuple[int, int, str]
type EventValues = tuple[float | None, float | None, float | None]


@dataclass(frozen=True, slots=True, kw_only=True)
class F11Event:
    """Одно событие F11 с измеренными непрерывными величинами и пиком."""

    ordinal: int
    peak_sample: int
    peak_time_s: float
    polarity: Polarity
    absolute_peak_v: float | None
    duration_s: float | None
    dominant_band: str | None
    v2_s: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class F11EventInventory:
    """Событийный вход F11 и явный учёт пропусков корневого инвентаря."""

    events: tuple[F11Event, ...]
    gap_count: int = 0
    omitted_gap_count: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class F15ModeSource:
    """Публичное окно F15, необходимое F11 для назначения канонических мод."""

    status: Status
    window_s: float
    overlap_fraction: float
    feature_medians: FeatureVector
    feature_mads: FeatureVector
    canonical_labels: tuple[str, ...]
    canonical_standardized_features: tuple[FeatureVector, ...]
    window_features: tuple[FeatureVector | None, ...]
    window_labels: tuple[str | None, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class F11QuantityResult:
    """Поддержка, квантили и эмпирическая CDF одной непрерывной величины."""

    quantity: str
    observed_count: int
    missing_count: int
    status: Status
    reason_codes: tuple[str, ...]
    quantiles: tuple[float | None, ...]
    cdf_probabilities: tuple[float, ...] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class F11Cell:
    """Ячейка phase × band × F15 mode с явной поддержкой и четырьмя CDF."""

    phase_bin: int
    band_index: int
    mode_label: str
    support_count: int
    positive_count: int
    negative_count: int
    status: Status
    reason_codes: tuple[str, ...]
    distributions: tuple[F11QuantityResult, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class F11Result:
    """Ограниченный результат F11 и полный учёт событийного входа."""

    status: Status
    reason_codes: tuple[str, ...]
    cells: tuple[F11Cell, ...]
    phase_bin_edges_rad: tuple[float, ...]
    bands_hz: tuple[tuple[float, float], ...]
    mode_labels: tuple[str, ...]
    quantiles: tuple[float, ...]
    cdf_probabilities: tuple[float, ...]
    cdf_grids: tuple[tuple[float, ...], ...]
    event_count: int
    evaluated_event_count: int
    omitted_event_count: int
    n_missing: int
    n_mode_missing: int
    n_dominant_band_unavailable: int
    n_phase_unavailable: int
