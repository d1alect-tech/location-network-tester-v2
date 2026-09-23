"""Family slice computations for the characterization seam."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - runtime artifact paths
from typing import TYPE_CHECKING, Final, cast

from lnt.characterization.clipping import resolve_clipping
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.events import compute_root_events
from lnt.characterization.f01_phase_cycle import compute_f01_phase_cycle
from lnt.characterization.f02_amplitude_shape import (
    compute_f02_amplitude_time_shape,
    resample_cycle_template,
)
from lnt.characterization.f03_interharmonic import compute_f03_interharmonic_tracks
from lnt.characterization.f04_periodicity import compute_f04_multicycle_periodicity
from lnt.characterization.f05_phase_stats import compute_f05_phase_conditioned_statistics
from lnt.characterization.f06_modulation import compute_f06_modulation_trajectories
from lnt.manifest import manifest_from_json
from lnt.session_store import MANIFEST_FILENAME

from .types import AnalysisCancelledError, Float32Array

if TYPE_CHECKING:
    from lnt.analysis_store import CharacterizationRecipe
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.clipping import ChannelName, ClippingBounds
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.f01_phase_cycle import F01Result
    from lnt.characterization.f02_amplitude_shape import F02Result
    from lnt.characterization.f03_result import F03Result
    from lnt.characterization.f04_periodicity import F04Result
    from lnt.characterization.f05_phase_stats import F05Result
    from lnt.characterization.f06_modulation import F06Result
    from lnt.characterization.phase import PhaseCycles
    from lnt.scope_io import CancellationToken
    from lnt.types import SessionManifest

__all__ = [
    "_checkpoint",
    "_clipping_for",
    "_compute_f01",
    "_compute_f02",
    "_compute_f03",
    "_compute_f04",
    "_compute_f05",
    "_compute_f06",
    "_int_tuple",
    "_num",
    "_root_events",
    "_session_manifest",
]

_F02_INDEX: Final = 1
_F03_INDEX: Final = 2
_F04_INDEX: Final = 3
_F05_INDEX: Final = 4
_F06_INDEX: Final = 5


def _num(family: CharacterizationFamily, name: str) -> float:
    """Числовое поле рецепта: домены проверены numeric-rules при разборе."""
    return float(cast("int | float", family.value(name)))


def _int_tuple(family: CharacterizationFamily, name: str) -> tuple[int, ...]:
    """Целочисленный список рецепта: отказ вместо приведения типов."""
    raw = family.value(name)
    if not isinstance(raw, tuple):
        raise CharacterizationError("status_invariant", f"{family.id} {name} must be an int list")
    values: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise CharacterizationError(
                "status_invariant", f"{family.id} {name} must be an int list"
            )
        values.append(item)
    return tuple(values)


def _checkpoint(cancellation: CancellationToken) -> None:
    """Подтверждает отмену до тяжёлой работы и до публикации."""
    if cancellation.is_cancelled():
        raise AnalysisCancelledError("characterization")


def _root_events(
    samples: Float32Array,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    clipping: ClippingBounds,
    cancellation: CancellationToken,
) -> RootEvents:
    """Инвентарь корневых событий: один расчёт на оба семейства, читающие события."""
    _checkpoint(cancellation)
    return compute_root_events(
        samples,
        sample_rate_hz=sample_rate_hz,
        recipe=recipe,
        clipping=clipping,
        checkpoint=lambda: _checkpoint(cancellation),
    )


def _session_manifest(session_dir: Path) -> SessionManifest:
    """Манифест сессии: один парсинг на все семейства, которым нужны его поля."""
    return manifest_from_json((session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))


def _clipping_for(
    manifest: SessionManifest,
    measured_name: str,
    recipe: CharacterizationRecipe,
) -> ClippingBounds:
    """Границы клиппирования измеренного канала: один расчёт на все семейства.

    Вынесено из ``_root_events``, потому что границы нужны не только инвентарю
    событий: F10 исключает клипированные интервалы (спека F10:57). Манифест
    приходит готовым, чтобы второй парсинг не завёл второй источник истины.
    """
    return resolve_clipping(
        manifest,
        cast("ChannelName", measured_name),
        recipe.events.clipping_fraction_of_range,
    )


def _compute_f01(
    samples: Float32Array,
    sync_reference: Float32Array,
    sample_rate_hz: float,
) -> F01Result:
    """Корень фазы и сетки: оценка f1 по измеренному каналу и синхронной опоре."""
    return compute_f01_phase_cycle(
        samples,
        sample_rate_hz=sample_rate_hz,
        sync_reference=sync_reference,
    )


def _compute_f02(
    f01: F01Result,
    samples: Float32Array,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    root_events: RootEvents,
) -> F02Result:
    """Подгонка шаблона F01 по измеренному каналу и готовому инвентарю событий."""
    if f01.x_template_v is None or f01.f1_hz is None:
        # Шаблона нет: F02 объявлен недоступным, а не подобран по нулям.
        return compute_f02_amplitude_time_shape(samples, None, (), sample_rate_hz=sample_rate_hz)
    family = recipe.families[_F02_INDEX]
    return compute_f02_amplitude_time_shape(
        samples,
        resample_cycle_template(f01.x_template_v, f1_hz=f01.f1_hz, sample_rate_hz=sample_rate_hz),
        root_events.events,
        sample_rate_hz=sample_rate_hz,
        subsample_divisor=int(_num(family, "subsample_divisor")),
        minimum_event_snr_db=_num(family, "minimum_event_snr_db"),
        residual_fraction_max=_num(family, "residual_fraction_max"),
        maximum_events=int(_num(family, "maximum_events")),
    )


def _compute_f03(
    f01: F01Result,
    samples: Float32Array,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F03Result:
    """Треки интергармоник по сетке F01 и объявленным гейтам семейства."""
    family = recipe.families[_F03_INDEX]
    return compute_f03_interharmonic_tracks(
        samples,
        sample_rate_hz=sample_rate_hz,
        f01_result=f01,
        window_s=_num(family, "window_s"),
        bin_spacing_hz=_num(family, "bin_spacing_hz"),
        association_tolerance_bins=int(_num(family, "association_tolerance_bins")),
        detection_margin_db=_num(family, "detection_margin_db"),
        local_median_bin_count=int(_num(family, "local_median_bin_count")),
        minimum_lifetime_windows=int(_num(family, "minimum_lifetime_windows")),
        subharmonic_orders=_int_tuple(family, "subharmonic_orders"),
        maximum_tracks=int(_num(family, "maximum_tracks")),
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )


def _compute_f04(  # noqa: PLR0913, PLR0917 - явные параметры среза, без скрытого контекста
    phase: PhaseCycles,
    carrier: Float32Array,
    mains: Float32Array,
    f06: F06Result,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    manifest: SessionManifest,
    cancellation: CancellationToken,
) -> F04Result:
    """ADEV сети и несущей и АКФ циклов по корням фазы и траектории F06."""
    family = recipe.families[_F04_INDEX]
    if family.value("carrier_source_family_id") != "f06_modulation_trajectories":
        raise CharacterizationError("status_invariant", "f04 carrier must come from f06")
    return compute_f04_multicycle_periodicity(
        mains,
        sample_rate_hz=sample_rate_hz,
        phase=phase,
        carrier=carrier,
        f06_result=f06,
        line_frequency_hz=float(manifest.line_frequency_hz),
        averaging_factors=_int_tuple(family, "averaging_factors"),
        maximum_averaging_fraction_of_record=_num(family, "maximum_averaging_fraction_of_record"),
        minimum_cycles=int(_num(family, "minimum_cycles")),
        carrier_minimum_snr_db=_num(family, "carrier_minimum_snr_db"),
        autocorrelation_lags_cycles=_int_tuple(family, "autocorrelation_lags_cycles"),
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )


def _compute_f05(
    samples: Float32Array,
    phase: PhaseCycles,
    root_events: RootEvents,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F05Result:
    """Моменты фазовых бинов измеренного канала по циклам опорного CH2."""
    family = recipe.families[_F05_INDEX]
    return compute_f05_phase_conditioned_statistics(
        samples,
        phase,
        root_events.events,
        phase_bins=int(_num(family, "phase_bins")),
        minimum_support_per_bin=int(_num(family, "minimum_support_per_bin")),
        variance_ddof=int(_num(family, "variance_ddof")),
        checkpoint=lambda: _checkpoint(cancellation),
    )


def _compute_f06(
    samples: Float32Array,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    cancellation: CancellationToken,
) -> F06Result:
    """Траектории огибающей, фазы и мгновенной частоты по объявленной полосе несущей."""
    family = recipe.families[_F06_INDEX]
    return compute_f06_modulation_trajectories(
        samples,
        sample_rate_hz=sample_rate_hz,
        band_low_hz=_num(family, "band_low_hz"),
        band_high_hz=_num(family, "band_high_hz"),
        nyquist_fraction_max=recipe.stft.nyquist_fraction_max,
        filter_order=int(_num(family, "filter_order")),
        minimum_snr_db=_num(family, "minimum_snr_db"),
        maximum_components_in_band=int(_num(family, "maximum_components_in_band")),
        phase_increment_max_rad=_num(family, "phase_increment_max_rad"),
        envelope_zero_fraction_of_median=_num(family, "envelope_zero_fraction_of_median"),
        maximum_stored_samples=int(_num(family, "maximum_stored_samples")),
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
