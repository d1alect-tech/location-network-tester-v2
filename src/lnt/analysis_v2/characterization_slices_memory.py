"""Слайс F16: мультимасштабная память фазового остатка."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f16_engine import compute_f16_multiscale_memory
from lnt.characterization.f16_result import F16Declarations, F16Result

from .characterization_slices import _checkpoint, _num, _text
from .characterization_slices_extended import _float_tuple

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
    from lnt.scope_io import CancellationToken

    from .types import Float32Array

__all__ = ["_compute_f16"]

_F16_INDEX: Final = 15


def _compute_f16(  # noqa: PLR0913, PLR0917 - полный набор входов seam
    samples: Float32Array,
    phase: PhaseCycles,
    means: PhaseMeans,
    inventory: RootEvents,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F16Result:
    """Собрать F16 из общих корневых отсчётов, корня фазы, средних и инвентаря."""
    _checkpoint(cancellation)
    family = recipe.families[_F16_INDEX]
    declarations = F16Declarations(
        phase_bins=int(_num(family, "phase_bins")),
        autocovariance=_text(family, "autocovariance"),
        lags_s=_float_tuple(family, "lags_s"),
        recurrence_radius_mad=_float_tuple(family, "recurrence_radius_mad"),
        count_windows_s=_float_tuple(family, "count_windows_s"),
        count_window_overlap_fraction=_num(family, "count_window_overlap_fraction"),
        partial_count_window_handling=_text(family, "partial_count_window_handling"),
        fano_variance_ddof=int(_num(family, "fano_variance_ddof")),
        minimum_pairs=int(_num(family, "minimum_pairs")),
        minimum_count_windows=int(_num(family, "minimum_count_windows")),
        maximum_fft_segment_samples=int(_num(family, "maximum_fft_segment_samples")),
    )
    result = compute_f16_multiscale_memory(
        samples,
        phase,
        means,
        inventory,
        declarations,
        recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    return result
