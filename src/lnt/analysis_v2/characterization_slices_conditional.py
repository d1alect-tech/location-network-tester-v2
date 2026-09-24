"""Слайс условных семейств: адаптация F15 и корневых событий для F11."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Final, cast

from lnt.analysis_store.characterization_family import CharacterizationFamily
from lnt.characterization.f11_contract import F11Declarations
from lnt.characterization.f11_engine import compute_f11_conditional_distributions
from lnt.characterization.f11_result import F11Event, F11EventInventory, F15ModeSource
from lnt.characterization.sync_grid import complete_window_count, nominal_window_samples

from .characterization_slices import _checkpoint, _num

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.f11_result import F11Result
    from lnt.characterization.f15_result import F15Result
    from lnt.characterization.phase_model import PhaseCycles
    from lnt.scope_io import CancellationToken

__all__ = ["_compute_f11", "build_f11_event_inventory", "build_f15_mode_source"]

_F11_INDEX: Final = 10

type TextReader = Callable[[CharacterizationFamily, str], str]
type StringReader = Callable[[CharacterizationFamily, str], tuple[str, ...]]
type FloatReader = Callable[[CharacterizationFamily, str], tuple[float, ...]]
type Readers = tuple[TextReader, StringReader, FloatReader]


def build_f15_mode_source(
    f15: F15Result,
    sample_count: int,
    sample_rate_hz: float,
    overlap_fraction: float,
) -> F15ModeSource:
    """Развернуть сохранённые строки F15 на каноническую сетку полных окон."""
    total = complete_window_count(
        int(sample_count), nominal_window_samples(f15.window_s, sample_rate_hz)
    )
    labels: list[str | None] = [None] * total
    for index, label in zip(f15.window_indices, f15.labels, strict=True):
        window_index = int(index)
        if not 0 <= window_index < total:
            raise ValueError("F15 retained window is outside the complete window grid")
        labels[window_index] = f"mode_{int(label)}"
    return F15ModeSource(
        status=f15.status,
        window_s=f15.window_s,
        overlap_fraction=overlap_fraction,
        feature_medians=tuple(float(value) for value in f15.feature_medians),
        feature_mads=tuple(float(value) for value in f15.feature_mads),
        canonical_labels=tuple(f"mode_{index}" for index in range(f15.medoid_indices.size)),
        canonical_standardized_features=tuple(
            tuple(float(value) for value in f15.standardized_features[int(index)])
            for index in f15.medoid_indices
        ),
        # F15 считает признаки только для even-floor-selected окон; сохранённая
        # метка нужна F11 без повторного вычисления. Неограниченная W×7 матрица
        # нарушила бы maximum_labels, поэтому за её пределом остаётся
        # mode_assignment_unavailable.
        #
        # ponytail: потолок 81.92 с (4096 окон × 0.02 с); если длинные записи
        # станут режимом, публиковать сырые признаки всех окон из F15.
        window_features=(None,) * total,
        window_labels=tuple(labels),
    )


def build_f11_event_inventory(inventory: RootEvents, sample_rate_hz: float) -> F11EventInventory:
    """Перенести измеренные поля корневого инвентаря без повторного детектора."""
    rate = float(sample_rate_hz)
    return F11EventInventory(
        events=tuple(
            F11Event(
                ordinal=event.ordinal,
                peak_sample=event.peak_sample,
                peak_time_s=event.peak_time_s,
                polarity=event.polarity,
                absolute_peak_v=abs(float(event.peak_value_v)),
                duration_s=(event.end_sample - event.start_sample + 1) / rate,
                dominant_band=event.dominant_band,
                v2_s=event.v2_s,
            )
            for event in inventory.events
        ),
        gap_count=inventory.gap_count,
        omitted_gap_count=inventory.omitted_gap_count,
    )


def _compute_f11(  # noqa: PLR0913, PLR0917 - полный набор входов seam
    phase: PhaseCycles,
    inventory: RootEvents,
    f15: F15Result,
    recipe: CharacterizationRecipe,
    readers: Readers,
    bands: tuple[ResolvedBand, ...],
    sample_count: int,
    sample_rate_hz: float,
    overlap_fraction: float,
    cancellation: CancellationToken,
) -> F11Result:
    """Собрать F11 из готовой фазы, F15, корневых событий и общей полосовой сетки."""
    _checkpoint(cancellation)
    text, strings, floats = readers
    f11_family = recipe.families[_F11_INDEX]
    declarations = F11Declarations(
        phase_bins=int(_num(f11_family, "phase_bins")),
        bands_hz=cast("tuple[tuple[float, float], ...]", f11_family.value("bands_hz")),
        band_interval_rule=text(f11_family, "band_interval_rule"),
        mode_source_family_id=text(f11_family, "mode_source_family_id"),
        mode_conditioning_rule=text(f11_family, "mode_conditioning_rule"),
        mode_count=int(_num(f11_family, "mode_count")),
        mode_distance_tie_break=text(f11_family, "mode_distance_tie_break"),
        quantities=strings(f11_family, "quantities"),
        quantiles=floats(f11_family, "quantiles"),
        quantile_method=text(f11_family, "quantile_method"),
        cdf_points=int(_num(f11_family, "cdf_points")),
        minimum_support=int(_num(f11_family, "minimum_support")),
        maximum_events=int(_num(f11_family, "maximum_events")),
    )
    result = compute_f11_conditional_distributions(
        phase,
        build_f11_event_inventory(inventory, sample_rate_hz),
        build_f15_mode_source(
            f15,
            sample_count,
            sample_rate_hz,
            overlap_fraction,
        ),
        declarations,
        bands,
    )
    _checkpoint(cancellation)
    return result
