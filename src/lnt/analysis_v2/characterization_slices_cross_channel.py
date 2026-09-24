"""Слайс F14: двусторонняя ассоциация событий между каналами."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f14_engine import compute_f14_cross_channel_event_association
from lnt.characterization.f14_result import F14Declarations, F14Result

from .characterization_slices import _checkpoint, _int_tuple, _num, _text

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
    from lnt.scope_io import CancellationToken

    from .types import Float32Array

__all__ = ["_compute_f14"]

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
