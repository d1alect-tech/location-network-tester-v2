"""Слайс F13: коактивность общих фазово-остаточных полосовых огибающих."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Final, cast

from lnt.analysis_store.characterization_family import CharacterizationFamily
from lnt.characterization.f13_engine import compute_f13_band_envelope_coactivity
from lnt.characterization.f13_result import F13Declarations, F13Result

from .characterization_slices import _checkpoint, _num

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.envelope_models import BandEnvelopes
    from lnt.scope_io import CancellationToken

__all__ = ["_compute_f13"]

_F13_INDEX: Final = 12

type TextReader = Callable[[CharacterizationFamily, str], str]


def _compute_f13(
    source: BandEnvelopes,
    bands: tuple[ResolvedBand, ...],
    recipe: CharacterizationRecipe,
    text: TextReader,
    cancellation: CancellationToken,
) -> F13Result:
    """Собрать F13 из общего band-envelope корня и объявленной полосовой сетки."""
    _checkpoint(cancellation)
    family = recipe.families[_F13_INDEX]
    declarations = F13Declarations(
        bands_hz=cast("tuple[tuple[float, float], ...]", family.value("bands_hz")),
        filter=text(family, "filter"),
        filter_order=int(_num(family, "filter_order")),
        filter_phase=text(family, "filter_phase"),
        filter_edge_guard_fraction=_num(family, "filter_edge_guard_fraction"),
        phase_bins=int(_num(family, "phase_bins")),
        activity_threshold_mad=_num(family, "activity_threshold_mad"),
        lag_low_s=_num(family, "lag_low_s"),
        lag_high_s=_num(family, "lag_high_s"),
        maximum_lag_points=int(_num(family, "maximum_lag_points")),
        lag_tie_break=text(family, "lag_tie_break"),
        minimum_active_samples=int(_num(family, "minimum_active_samples")),
    )
    result = compute_f13_band_envelope_coactivity(
        source,
        declarations,
        bands,
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    return result
