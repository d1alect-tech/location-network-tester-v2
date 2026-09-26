"""Слайс F18: бикогерентность по объявленным триадам базовых частот."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f18_engine import compute_f18_bicoherence_triads
from lnt.characterization.f18_result import F18Declarations, F18Result

from .characterization_slices import _checkpoint, _num, _text
from .characterization_slices_extended import _float_tuple

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
    from lnt.scope_io import CancellationToken

    from .types import Float32Array

__all__ = ["_compute_f18"]

_F18_INDEX: Final = 17


def _compute_f18(  # noqa: PLR0913, PLR0917 - полный набор входов seam
    samples: Float32Array,
    phase: PhaseCycles,
    means: PhaseMeans,
    inventory: RootEvents,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F18Result:
    """Собрать F18 из фазового остатка и объявленной сетки STFT рецепта."""
    _checkpoint(cancellation)
    family = recipe.families[_F18_INDEX]
    declarations = F18Declarations(
        phase_bins=int(_num(family, "phase_bins")),
        segment_duration_s=_num(family, "segment_duration_s"),
        window=_text(family, "window"),
        overlap_fraction=_num(family, "overlap_fraction"),
        base_frequencies_hz=_float_tuple(family, "base_frequencies_hz"),
        triad_rule=_text(family, "triad_rule"),
        analysis_high_hz=_num(family, "analysis_high_hz"),
        nyquist_fraction_max=_num(family, "nyquist_fraction_max"),
        frequency_mapping=_text(family, "frequency_mapping"),
        maximum_triads=int(_num(family, "maximum_triads")),
        phase_randomized_surrogate_count=int(_num(family, "phase_randomized_surrogate_count")),
        iaaft_surrogate_count=int(_num(family, "iaaft_surrogate_count")),
        iaaft_iterations=int(_num(family, "iaaft_iterations")),
        iaaft_relative_rms_magnitude_tolerance=_num(
            family, "iaaft_relative_rms_magnitude_tolerance"
        ),
        surrogate_seed=int(_num(family, "surrogate_seed")),
        dual_null_p_value=_text(family, "dual_null_p_value"),
        multiple_testing=_text(family, "multiple_testing"),
        false_discovery_rate=_num(family, "false_discovery_rate"),
        minimum_frames=int(_num(family, "minimum_frames")),
    )
    result = compute_f18_bicoherence_triads(
        samples,
        phase,
        means,
        inventory,
        declarations,
        recipe.stft,
        recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    return result
