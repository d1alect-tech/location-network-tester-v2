"""Family slice computations added after the initial six (module size split).

Слайсы первых шести семейств живут в ``characterization_slices.py``. Лимит 250
чистых LOC на модуль (``tests/test_module_size.py``) не даёт дописывать туда
дальше, поэтому новые семейства идут сюда, пока и этот модуль не потребует
своего сплита; общие читатели рецепта и ``_checkpoint`` переиспользуются
импортом, а не копированием.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f07_cepstrum import compute_f07_comb_cepstrum

from .characterization_slices import _checkpoint, _int_tuple, _num

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.f01_phase_cycle import F01Result
    from lnt.characterization.f07_result import F07Result
    from lnt.scope_io import CancellationToken

    from .types import Float32Array

__all__ = ["_compute_f07"]

_F07_INDEX: Final = 6


def _text(family: CharacterizationFamily, name: str) -> str:
    """Текстовое поле рецепта: отказ вместо приведения к строке."""
    raw = family.value(name)
    if not isinstance(raw, str) or not raw:
        raise CharacterizationError("status_invariant", f"{family.id} {name} must be text")
    return raw


def _str_tuple(family: CharacterizationFamily, name: str) -> tuple[str, ...]:
    """Строковый список рецепта: отказ вместо приведения типов."""
    raw = family.value(name)
    if not isinstance(raw, tuple) or not raw:
        raise CharacterizationError("status_invariant", f"{family.id} {name} must be text list")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise CharacterizationError("status_invariant", f"{family.id} {name} must be text list")
        values.append(item)
    return tuple(values)


def _compute_f07(
    f01: F01Result,
    samples: Float32Array,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F07Result:
    """Кепстр, боковые полосы и гребёнка по ведущему кадру объявленной длины.

    Окна и кроссчек шага залочены рецептом (``characterization_locked.py``:
    ``windows=("hann","blackman")``, ``spacing_crosscheck=``
    ``"magnitude_spectrum_autocorrelation"``), но читаются из блока семейства
    как объявленные параметры: свободных ручек здесь нет.
    """
    family = recipe.families[_F07_INDEX]
    return compute_f07_comb_cepstrum(
        samples,
        sample_rate_hz=sample_rate_hz,
        f01_result=f01,
        fft_samples=int(_num(family, "fft_samples")),
        windows=_str_tuple(family, "windows"),
        log_floor_db_below_maximum=_num(family, "log_floor_db_below_maximum"),
        minimum_quefrency_samples=int(_num(family, "minimum_quefrency_samples")),
        offset_bins=_int_tuple(family, "offset_bins"),
        spacing_crosscheck=_text(family, "spacing_crosscheck"),
        window_peak_tolerance_bins=int(_num(family, "window_peak_tolerance_bins")),
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
