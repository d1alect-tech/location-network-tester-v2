"""Dedicated characterization seam parallel to the SessionKind dispatch."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - runtime artifact paths
from typing import TYPE_CHECKING, Final, cast

from lnt.analysis_store import (
    ArtifactCorruptError,
    ArtifactStore,
    CharacterizationRecipe,
    CodeIdentity,
)
from lnt.characterization import encode_bundle
from lnt.characterization.clipping import resolve_clipping
from lnt.characterization.events import compute_root_events
from lnt.characterization.f01_phase_cycle import compute_f01_phase_cycle
from lnt.characterization.f02_amplitude_shape import (
    compute_f02_amplitude_time_shape,
    resample_cycle_template,
)
from lnt.characterization.f05_phase_stats import compute_f05_phase_conditioned_statistics
from lnt.characterization.f06_bundle import build_f01_f02_f05_f06_bundle
from lnt.characterization.f06_modulation import compute_f06_modulation_trajectories
from lnt.characterization.phase import compute_phase_cycles
from lnt.manifest import manifest_from_json
from lnt.scope_io import NEVER_CANCELLED, CancellationToken
from lnt.session_store import MANIFEST_FILENAME

from .artifact_inputs import characterization_inputs
from .types import AnalysisCancelledError, AnalysisRunResult, Float32Array

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.clipping import ChannelName
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.f01_phase_cycle import F01Result
    from lnt.characterization.f02_amplitude_shape import F02Result
    from lnt.characterization.f05_phase_stats import F05Result
    from lnt.characterization.f06_modulation import F06Result
    from lnt.characterization.phase import PhaseCycles

__all__ = ["run_characterization"]

_F02_INDEX: Final = 1
_F05_INDEX: Final = 4
_F06_INDEX: Final = 5


def _num(family: CharacterizationFamily, name: str) -> float:
    """Числовое поле рецепта: домены проверены numeric-rules при разборе."""
    return float(cast("int | float", family.value(name)))


def _root_events(  # noqa: PLR0913, PLR0917 - явные параметры среза, без скрытого контекста
    samples: Float32Array,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    session_dir: Path,
    measured_name: str,
    cancellation: CancellationToken,
) -> RootEvents:
    """Инвентарь корневых событий: один расчёт на оба семейства, читающие события."""
    manifest = manifest_from_json((session_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    clipping = resolve_clipping(
        manifest,
        cast("ChannelName", measured_name),
        recipe.events.clipping_fraction_of_range,
    )
    _checkpoint(cancellation)
    return compute_root_events(
        samples,
        sample_rate_hz=sample_rate_hz,
        recipe=recipe,
        clipping=clipping,
        checkpoint=lambda: _checkpoint(cancellation),
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


def run_characterization(  # noqa: PLR0913 - seam параллелен dispatch, параметры явные
    recipe: CharacterizationRecipe,
    session_dir: Path,
    channels: tuple[Float32Array, ...],
    sample_rate_hz: float,
    cancellation: CancellationToken = NEVER_CANCELLED,
    *,
    code_identity: CodeIdentity | None = None,
) -> AnalysisRunResult:
    """Выполняет characterization поверх ArtifactStore без SessionKind-dispatch.

    Считает F01, один общий корневой инвентарь событий, корень фазы по CH2,
    затем F02 по шаблону F01, F05 по готовым событиям и циклам и F06 по
    объявленной полосе несущей.
    Ключ строится из recipe_sha256, sha256_file сырых каналов, явных
    digest tunables и CodeIdentity; повторный прогон возвращает cache_hit.

    Предусловие: session_dir содержит читаемый manifest.json — он нужен
    resolve_clipping на шаге корневых событий. Маршрут валидирует сессию через
    load_session до вызова seam, поэтому отсутствующий манифест сюда не
    доходит; прямой вызов seam с битым манифестом получит OSError, который
    маршрут уже переводит в failed-job (`routes_analysis_v2.py:175`).

    project_default не вызывается, BranchContext не используется.
    """
    if len(channels) != len(recipe.channels):
        raise ValueError("число каналов не совпадает с recipe.channels")
    if not sample_rate_hz > 0:
        raise ValueError("sample_rate_hz должен быть положительным")
    identity = code_identity if code_identity is not None else CodeIdentity.current()
    channel_paths = tuple(session_dir / f"{name}.npy" for name in recipe.channels)
    inputs = characterization_inputs(recipe, channel_paths, identity)
    store = ArtifactStore(session_dir)
    try:
        cached = store.find(inputs.artifact_key)
    except ArtifactCorruptError:
        store.invalidate(inputs.artifact_key)
        cached = None
    if cached is not None:
        return AnalysisRunResult(
            artifact_key=inputs.artifact_key,
            artifact_dir=cached,
            cache_hit=True,
            failures=(),
        )
    _checkpoint(cancellation)
    channel_by_name = dict(zip(recipe.channels, channels, strict=True))
    ref_name = recipe.phase.reference_channel
    meas_name = next(name for name in recipe.channels if name != ref_name)
    samples = channel_by_name[meas_name]
    result = compute_f01_phase_cycle(
        samples,
        sample_rate_hz=sample_rate_hz,
        sync_reference=channel_by_name[ref_name],
    )
    _checkpoint(cancellation)
    root_events = _root_events(
        samples, sample_rate_hz, recipe, session_dir, meas_name, cancellation
    )
    _checkpoint(cancellation)
    phase = compute_phase_cycles(
        channel_by_name.get("ch2"),
        sample_rate_hz=sample_rate_hz,
        settings=recipe.phase,
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    f02 = _compute_f02(result, samples, sample_rate_hz, recipe, root_events)
    f05 = _compute_f05(samples, phase, root_events, recipe, cancellation)
    f06 = _compute_f06(samples, sample_rate_hz, recipe, cancellation)
    _checkpoint(cancellation)
    bundle, arrays, tables = build_f01_f02_f05_f06_bundle(
        result,
        f02,
        f05,
        f06,
        recipe,
        measured_channel=meas_name,
        sample_rate_hz=sample_rate_hz,
        record_duration_s=samples.size / sample_rate_hz,
    )
    files = encode_bundle(
        bundle, arrays, tables, max_artifact_bytes=recipe.resource_limits.max_artifact_bytes
    )
    _checkpoint(cancellation)
    artifact_dir = store.publish(inputs, files)
    return AnalysisRunResult(
        artifact_key=inputs.artifact_key,
        artifact_dir=artifact_dir,
        cache_hit=False,
        failures=(),
    )


def _checkpoint(cancellation: CancellationToken) -> None:
    """Подтверждает отмену до тяжёлой работы и до публикации."""
    if cancellation.is_cancelled():
        raise AnalysisCancelledError("characterization")
