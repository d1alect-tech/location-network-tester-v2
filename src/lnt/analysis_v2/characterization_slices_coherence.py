"""Слайс F17: циклическая спектральная когерентность двух каналов."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.f17_contract import PHASE_REFERENCE_UNAVAILABLE
from lnt.characterization.f17_engine import compute_f17_cyclic_spectral_coherence
from lnt.characterization.f17_result import F17Declarations, F17Result, unavailable_f17

from .characterization_slices import _checkpoint, _num, _text
from .characterization_slices_extended import _float_tuple

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
    from lnt.scope_io import CancellationToken

    from .types import Float32Array

__all__ = ["_compute_f17"]

_F17_INDEX: Final = 16


def _compute_f17(
    channel_by_name: Mapping[str, Float32Array],
    phase: PhaseCycles,
    phase_means_by_name: Mapping[str, PhaseMeans],
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F17Result:
    """Собрать F17 из двух объявленных каналов, общей фазы и двух наборов средних.

    Верхний канал произведения — CH1, нижний — CH2 (f17_contract:
    ``ch1_upper_times_conjugate_ch2_lower``). Отсутствующий канал означает и
    отсутствие его фазовых средних, поэтому F17 объявляется недоступным с
    пустыми доменами, а не собирается из подставного массива.
    """
    _checkpoint(cancellation)
    upper = channel_by_name.get("ch1")
    lower = channel_by_name.get("ch2")
    upper_means = phase_means_by_name.get("ch1")
    lower_means = phase_means_by_name.get("ch2")
    if upper is None or lower is None or upper_means is None or lower_means is None:
        return unavailable_f17((PHASE_REFERENCE_UNAVAILABLE,), 0)
    family = recipe.families[_F17_INDEX]
    declarations = F17Declarations(
        phase_bins=int(_num(family, "phase_bins")),
        cyclic_frequencies_hz=_float_tuple(family, "cyclic_frequencies_hz"),
        segment_samples=int(_num(family, "segment_samples")),
        window=_text(family, "window"),
        overlap_fraction=_num(family, "overlap_fraction"),
        analysis_low_hz=_num(family, "analysis_low_hz"),
        analysis_high_hz=_num(family, "analysis_high_hz"),
        nyquist_fraction_max=_num(family, "nyquist_fraction_max"),
        frequency_mapping=_text(family, "frequency_mapping"),
        surrogate=_text(family, "surrogate"),
        surrogate_count=int(_num(family, "surrogate_count")),
        surrogate_seed=int(_num(family, "surrogate_seed")),
        multiple_testing=_text(family, "multiple_testing"),
        false_discovery_rate=_num(family, "false_discovery_rate"),
        minimum_complete_cycles=int(_num(family, "minimum_complete_cycles")),
        minimum_frames=int(_num(family, "minimum_frames")),
        maximum_stored_cells=int(_num(family, "maximum_stored_cells")),
    )
    result = compute_f17_cyclic_spectral_coherence(
        ch1_samples=upper,
        ch2_samples=lower,
        phase=phase,
        ch1_means=upper_means,
        ch2_means=lower_means,
        declarations=declarations,
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    return result
