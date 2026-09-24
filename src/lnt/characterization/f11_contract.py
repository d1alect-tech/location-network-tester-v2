"""Проверка объявлений F11 и построение его фиксированной геометрии."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.bands import ResolvedBand
from lnt.characterization.f11_result import QUANTITIES, F11Result
from lnt.characterization.records import Status
from lnt.features.bands import BandDefinition, BandSet, EstimandDirection, FrequencyUnit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lnt.characterization.f11_result import F11EventInventory, F15ModeSource


_BAND_COUNT: Final = 3
_BAND_EDGE_COUNT: Final = 2
_MODE_COUNT: Final = 4
_BAND_RULE: Final = "left_closed_right_open_last_closed"
_MODE_SOURCE: Final = "f15_interpretable_modes"
_MODE_RULE: Final = "event_peak_window_nearest_canonical_medoid"
_MODE_TIE: Final = "lowest_canonical_mode_label"
_QUANTILE_METHOD: Final = "linear"


@dataclass(frozen=True, slots=True, kw_only=True)
class F11Declarations:
    """Полный tunable surface.recipe для F11 без скрытых правил."""

    phase_bins: int
    bands_hz: Sequence[Sequence[float]]
    band_interval_rule: str
    mode_source_family_id: str
    mode_conditioning_rule: str
    mode_count: int
    mode_distance_tie_break: str
    quantities: Sequence[str]
    quantiles: Sequence[float]
    quantile_method: str
    cdf_points: int
    minimum_support: int
    maximum_events: int


@dataclass(frozen=True, slots=True, kw_only=True)
class F11Settings:
    """Проверенные числовые гейты и геометрия одного запуска F11."""

    phase_bins: int
    bands_hz: tuple[tuple[float, float], ...]
    resolved_bands: tuple[ResolvedBand, ...]
    mode_count: int
    quantiles: tuple[float, ...]
    cdf_probabilities: tuple[float, ...]
    minimum_support: int
    maximum_events: int


def build_settings(declarations: F11Declarations) -> F11Settings:
    """Проверить числовые гейты и собрать общую полосовую сетку."""
    bins = int(declarations.phase_bins)
    modes = int(declarations.mode_count)
    points = int(declarations.cdf_points)
    minimum = int(declarations.minimum_support)
    maximum = int(declarations.maximum_events)
    if bins <= 0 or modes != _MODE_COUNT or points <= 0 or minimum <= 0 or maximum <= 0:
        raise ValueError("F11 numeric gates must be positive and mode_count must equal four")
    selected_quantiles = tuple(float(value) for value in declarations.quantiles)
    if not selected_quantiles or any(
        not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in selected_quantiles
    ):
        raise ValueError("F11 quantiles must be finite and inside [0, 1]")
    if len(declarations.bands_hz) != _BAND_COUNT or any(
        len(pair) != _BAND_EDGE_COUNT for pair in declarations.bands_hz
    ):
        raise ValueError("F11 requires three two-edge frequency bands")
    pairs = tuple((float(pair[0]), float(pair[1])) for pair in declarations.bands_hz)
    if len(pairs) != _BAND_COUNT or any(
        not math.isfinite(low) or not math.isfinite(high) or low < 0.0 or high <= low
        for low, high in pairs
    ):
        raise ValueError("F11 requires three finite ordered frequency bands")
    if any(left[1] > right[0] for left, right in pairwise(pairs)):
        raise ValueError("F11 bands must not overlap")
    definitions = tuple(
        BandDefinition(
            name=f"f11_band_{index:04d}",
            low=low,
            high=high,
            unit=FrequencyUnit.HZ,
            direction=EstimandDirection.DESCRIPTIVE,
        )
        for index, (low, high) in enumerate(pairs)
    )
    BandSet(bands=definitions)
    resolved = tuple(ResolvedBand(item, item, None) for item in definitions)
    return F11Settings(
        phase_bins=bins,
        bands_hz=pairs,
        resolved_bands=resolved,
        mode_count=modes,
        quantiles=selected_quantiles,
        cdf_probabilities=tuple(
            float(value) for value in np.linspace(0.0, 1.0, points, dtype=np.float64)
        ),
        minimum_support=minimum,
        maximum_events=maximum,
    )


def check_rules(declarations: F11Declarations) -> None:
    """Отклонить не объявленные правила F11."""
    if declarations.band_interval_rule != _BAND_RULE:
        raise ValueError(f"band_interval_rule must be {_BAND_RULE!r}")
    if declarations.mode_source_family_id != _MODE_SOURCE:
        raise ValueError(f"mode_source_family_id must be {_MODE_SOURCE!r}")
    if declarations.mode_conditioning_rule != _MODE_RULE:
        raise ValueError(f"mode_conditioning_rule must be {_MODE_RULE!r}")
    if declarations.mode_distance_tie_break != _MODE_TIE:
        raise ValueError(f"mode_distance_tie_break must be {_MODE_TIE!r}")
    if tuple(declarations.quantities) != QUANTITIES:
        raise ValueError("F11 quantities must use the locked vocabulary")
    if declarations.quantile_method != _QUANTILE_METHOD:
        raise ValueError(f"quantile_method must be {_QUANTILE_METHOD!r}")


def phase_edges(bins: int) -> tuple[float, ...]:
    """Опубликовать равномерные границы фазовых ячеек."""
    return tuple(2.0 * math.pi * index / bins for index in range(bins + 1))


def unavailable_result(
    codes: tuple[str, ...],
    inventory: F11EventInventory,
    mode_source: F15ModeSource,
    settings: F11Settings,
    *,
    n_phase_unavailable: int = 0,
) -> F11Result:
    """Вернуть отказ без ячеек, квантилей или выдуманной CDF."""
    return F11Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        cells=(),
        phase_bin_edges_rad=phase_edges(settings.phase_bins),
        bands_hz=settings.bands_hz,
        mode_labels=mode_source.canonical_labels,
        quantiles=settings.quantiles,
        cdf_probabilities=settings.cdf_probabilities,
        cdf_grids=((), (), (), ()),
        event_count=len(inventory.events),
        evaluated_event_count=0,
        omitted_event_count=0,
        n_missing=0,
        n_mode_missing=0,
        n_dominant_band_unavailable=0,
        n_phase_unavailable=n_phase_unavailable,
    )
