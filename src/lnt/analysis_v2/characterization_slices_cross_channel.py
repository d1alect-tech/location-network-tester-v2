"""Слайс F14: двусторонняя ассоциация событий между каналами."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f14_engine import compute_f14_cross_channel_event_association
from lnt.characterization.f14_result import F14Declarations, F14Result
from lnt.characterization.phase import compute_phase_means

from .characterization_slices import (
    _checkpoint,
    _clipping_for,
    _int_tuple,
    _num,
    _root_events,
    _text,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
    from lnt.scope_io import CancellationToken
    from lnt.types import SessionManifest

    from .types import Float32Array

__all__ = ["_compute_f14", "build_channel_roots"]

_F14_INDEX: Final = 13


def _compute_f14(  # noqa: PLR0913, PLR0917 - полный набор входов seam
    phase: PhaseCycles,
    ch1_samples: Float32Array | None,
    ch1_phase_means: PhaseMeans | None,
    ch1_events: RootEvents | None,
    ch2_samples: Float32Array | None,
    ch2_phase_means: PhaseMeans | None,
    ch2_events: RootEvents | None,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F14Result:
    """Собрать F14 из двух явных каналов, общей фазы и двух полных replay-инвентарей."""
    _checkpoint(cancellation)
    family = recipe.families[_F14_INDEX]
    declarations = F14Declarations(
        trigger_window_low_s=_num(family, "trigger_window_low_s"),
        trigger_window_high_s=_num(family, "trigger_window_high_s"),
        relative_time_bins=int(_num(family, "relative_time_bins")),
        nearest_event_lag_low_s=_num(family, "nearest_event_lag_low_s"),
        nearest_event_lag_high_s=_num(family, "nearest_event_lag_high_s"),
        nearest_event_tie_break=_text(family, "nearest_event_tie_break"),
        phase_bins=int(_num(family, "phase_bins")),
        cycle_shift_offsets=_int_tuple(family, "cycle_shift_offsets"),
        minimum_triggers=int(_num(family, "minimum_triggers")),
        maximum_triggers_per_direction=int(_num(family, "maximum_triggers_per_direction")),
        boundary_handling=_text(family, "boundary_handling"),
    )
    result = compute_f14_cross_channel_event_association(
        phase=phase,
        ch1_samples=ch1_samples,
        ch1_phase_means=ch1_phase_means,
        ch1_events=ch1_events,
        ch2_samples=ch2_samples,
        ch2_phase_means=ch2_phase_means,
        ch2_events=ch2_events,
        declarations=declarations,
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    return result


def build_channel_roots(  # noqa: PLR0913, PLR0917 - полный набор входов обвязки F14
    channel_by_name: Mapping[str, Float32Array],
    phase: PhaseCycles,
    meas_name: str,
    means: PhaseMeans,
    root_events: RootEvents,
    manifest: SessionManifest,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> tuple[dict[str, PhaseMeans], dict[str, RootEvents]]:
    """Построить фазовые средние и replay-инвентарь второго канала ровно один раз.

    F14 получает тот же фазовый корень и измеренный инвентарь; для второго канала
    его means и replay-инвентарь строятся здесь. Вынесено из
    ``run_characterization.py`` ради лимита 250 LOC: файл был на 245 строках, а
    три оставшихся семейства добавляли по четыре строки каждое.
    """
    phase_means_by_name = {meas_name: means}
    events_by_name = {meas_name: root_events}
    for name in ("ch1", "ch2"):
        if name == meas_name:
            continue
        channel = channel_by_name.get(name)
        if channel is None:
            continue
        channel_clipping = _clipping_for(manifest, name, recipe)
        phase_means_by_name[name] = compute_phase_means(
            channel,
            phase,
            settings=recipe.phase,
            resources=recipe.resource_limits,
            checkpoint=lambda: _checkpoint(cancellation),
        )
        events_by_name[name] = _root_events(
            channel, sample_rate_hz, recipe, channel_clipping, cancellation
        )
        _checkpoint(cancellation)
    return phase_means_by_name, events_by_name
