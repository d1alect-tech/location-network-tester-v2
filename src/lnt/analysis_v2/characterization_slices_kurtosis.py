"""Слайс F12: спектральная куртозис по объявленным масштабам STFT."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f12_engine import compute_f12_spectral_kurtosis
from lnt.characterization.f12_result import F12Declarations, F12Result

from .characterization_slices import _checkpoint, _int_tuple, _num, _text

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.clipping import ClippingBounds
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
    from lnt.scope_io import CancellationToken

    from .types import Float32Array

__all__ = ["_compute_f12"]

_F12_INDEX: Final = 11


def _compute_f12(  # noqa: PLR0913, PLR0917 - полный набор входов seam
    samples: Float32Array,
    phase: PhaseCycles,
    means: PhaseMeans,
    clipping: ClippingBounds,
    inventory: RootEvents,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F12Result:
    """Собрать F12 из фазового остатка, средних, инвентаря и границ клиппирования."""
    _checkpoint(cancellation)
    family = recipe.families[_F12_INDEX]
    declarations = F12Declarations(
        phase_bins=int(_num(family, "phase_bins")),
        segment_samples=_int_tuple(family, "segment_samples"),
        window=_text(family, "window"),
        overlap_fraction=_num(family, "overlap_fraction"),
        detrend=_text(family, "detrend"),
        analysis_low_hz=_num(family, "analysis_low_hz"),
        analysis_high_hz=_num(family, "analysis_high_hz"),
        nyquist_fraction_max=_num(family, "nyquist_fraction_max"),
        minimum_frames=int(_num(family, "minimum_frames")),
        surrogate=_text(family, "surrogate"),
        surrogate_count=int(_num(family, "surrogate_count")),
        surrogate_seed=int(_num(family, "surrogate_seed")),
        search_adjustment=_text(family, "search_adjustment"),
        multiple_testing=_text(family, "multiple_testing"),
        false_discovery_rate=_num(family, "false_discovery_rate"),
        maximum_stored_bins=int(_num(family, "maximum_stored_bins")),
    )
    result = compute_f12_spectral_kurtosis(
        samples,
        phase,
        means,
        clipping,
        inventory,
        declarations,
        recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    return result
