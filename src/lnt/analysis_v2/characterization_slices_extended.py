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
from lnt.characterization.f08_transient import compute_f08_transient_morphology
from lnt.characterization.f09_ordering import compute_f09_event_ordering
from lnt.characterization.f10_threshold_surface import compute_f10_threshold_surface

from .characterization_slices import _checkpoint, _int_tuple, _num

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.clipping import ClippingBounds
    from lnt.characterization.event_models import RootEvent, RootEvents
    from lnt.characterization.f01_phase_cycle import F01Result
    from lnt.characterization.f07_result import F07Result
    from lnt.characterization.f08_result import F08Result
    from lnt.characterization.f09_result import F09Result
    from lnt.characterization.f10_result import F10Result
    from lnt.characterization.phase import PhaseCycles, PhaseMeans
    from lnt.scope_io import CancellationToken

    from .types import Float32Array

__all__ = ["_compute_f07", "_compute_f08", "_compute_f09", "_compute_f10", "_float_tuple"]

_F07_INDEX: Final = 6
_F08_INDEX: Final = 7
_F09_INDEX: Final = 8
_F10_INDEX: Final = 9


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


def _float_tuple(family: CharacterizationFamily, name: str) -> tuple[float, ...]:
    """Числовой список рецепта: отказ вместо приведения типов."""
    raw = family.value(name)
    if not isinstance(raw, tuple) or not raw:
        raise CharacterizationError("status_invariant", f"{family.id} {name} must be number list")
    values: list[float] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise CharacterizationError(
                "status_invariant", f"{family.id} {name} must be number list"
            )
        values.append(float(item))
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


def _compute_f08(
    samples: Float32Array,
    events: tuple[RootEvent, ...],
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F08Result:
    """Морфология и затухание каждого объявленного события по общему инвентарю."""
    family = recipe.families[_F08_INDEX]
    return compute_f08_transient_morphology(
        samples,
        events,
        sample_rate_hz=sample_rate_hz,
        baseline=_text(family, "baseline"),
        ringing_frequency_low_hz=_num(family, "ringing_frequency_low_hz"),
        ringing_frequency_high_hz=_num(family, "ringing_frequency_high_hz"),
        decay_time_minimum_samples=int(_num(family, "decay_time_minimum_samples")),
        decay_time_max_s=_num(family, "decay_time_max_s"),
        amplitude_maximum_peak_multiple=_num(family, "amplitude_maximum_peak_multiple"),
        phase_low_rad=_num(family, "phase_low_rad"),
        phase_high_rad=_num(family, "phase_high_rad"),
        maximum_function_evaluations=int(_num(family, "maximum_function_evaluations")),
        minimum_snr_db=_num(family, "minimum_snr_db"),
        residual_fraction_max=_num(family, "residual_fraction_max"),
        minimum_zero_crossings=int(_num(family, "minimum_zero_crossings")),
        maximum_events=int(_num(family, "maximum_events")),
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )


def _compute_f09(
    inventory: RootEvents,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F09Result:
    """Порядок событий и ожидания по общему инвентарю: детектор не вызывается."""
    family = recipe.families[_F09_INDEX]
    return compute_f09_event_ordering(
        inventory,
        event_type_fields=_str_tuple(family, "event_type_fields"),
        cluster_gap_s=_num(family, "cluster_gap_s"),
        minimum_event_count=int(_num(family, "minimum_event_count")),
        dead_time_handling=_text(family, "dead_time_handling"),
        gap_handling=_text(family, "gap_handling"),
        maximum_events=int(_num(family, "maximum_events")),
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )


def _compute_f10(  # noqa: PLR0913, PLR0917 - явные параметры среза, без скрытого контекста
    samples: Float32Array,
    phase: PhaseCycles,
    means: PhaseMeans,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    clipping: ClippingBounds,
    cancellation: CancellationToken,
) -> F10Result:
    """Поверхность порог × длительность × бин фазы по общему корню фазы.

    ``phase`` и ``means`` — готовые общие корни (спека F10:55 требует
    квалифицированную фазу CH2); ``clipping`` объявлен спекой:57 — клипированные
    интервалы исключаются, поэтому границы приходят из манифеста, а не
    выдумываются. ``gap_mask`` не передаётся: фазовые пропуски уже выражены
    корнем циклов (F10-решение в evidence task-19).
    """
    family = recipe.families[_F10_INDEX]
    return compute_f10_threshold_surface(
        samples,
        phase,
        means,
        sample_rate_hz=sample_rate_hz,
        phase_bins=int(_num(family, "phase_bins")),
        scale=_text(family, "scale"),
        threshold_sigma=_float_tuple(family, "threshold_sigma"),
        minimum_duration_s=_float_tuple(family, "minimum_duration_s"),
        quantiles=_float_tuple(family, "quantiles"),
        edge_episode_handling=_text(family, "edge_episode_handling"),
        maximum_episodes=int(_num(family, "maximum_episodes")),
        resources=recipe.resource_limits,
        clipping=clipping,
        checkpoint=lambda: _checkpoint(cancellation),
    )
