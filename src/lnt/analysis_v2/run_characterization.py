"""Dedicated characterization seam parallel to the SessionKind dispatch."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - runtime artifact paths

from lnt.analysis_store import (
    ArtifactCorruptError,
    ArtifactStore,
    CharacterizationRecipe,
    CodeIdentity,
)
from lnt.characterization import encode_bundle
from lnt.characterization.bands import resolve_characterization_bands
from lnt.characterization.characterization_bundle import build_characterization_bundle
from lnt.characterization.phase import compute_phase_cycles, compute_phase_means
from lnt.scope_io import NEVER_CANCELLED, CancellationToken

from .artifact_inputs import characterization_inputs
from .characterization_slices import (
    _checkpoint,
    _clipping_for,
    _compute_f01,
    _compute_f02,
    _compute_f03,
    _compute_f04,
    _compute_f05,
    _compute_f06,
    _root_events,
    _session_manifest,
)
from .characterization_slices_extended import (
    _compute_f07,
    _compute_f08,
    _compute_f09,
    _compute_f10,
    _compute_f15,
)
from .types import AnalysisRunResult, Float32Array

__all__ = ["run_characterization"]


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

    Считает F01, один общий корневой инвентарь событий, корень фазы по CH2 и его
    фазовые средние, затем F02 по шаблону F01, F03 по сетке F01, F05 по готовым
    событиям и циклам, F06 по объявленной полосе несущей, F04 по корням фазы
    и несущей F06, F07 по ведущему кадру, F08 по событиям, F09 по инвентарю
    событий, F10 по корню фазы, средним и клиппированию и F15 по тем же корням.
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
    manifest = _session_manifest(session_dir)
    clipping = _clipping_for(manifest, meas_name, recipe)
    result = _compute_f01(samples, channel_by_name[ref_name], sample_rate_hz)
    _checkpoint(cancellation)
    root_events = _root_events(samples, sample_rate_hz, recipe, clipping, cancellation)
    _checkpoint(cancellation)
    phase = compute_phase_cycles(
        channel_by_name.get("ch2"),
        sample_rate_hz=sample_rate_hz,
        settings=recipe.phase,
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    means = compute_phase_means(
        samples,
        phase,
        settings=recipe.phase,
        resources=recipe.resource_limits,
        checkpoint=lambda: _checkpoint(cancellation),
    )
    _checkpoint(cancellation)
    f02 = _compute_f02(result, samples, sample_rate_hz, recipe, root_events)
    f03 = _compute_f03(result, samples, sample_rate_hz, recipe, cancellation)
    f05 = _compute_f05(samples, phase, root_events, recipe, cancellation)
    f06 = _compute_f06(samples, sample_rate_hz, recipe, cancellation)
    f04 = _compute_f04(
        phase,
        samples,
        channel_by_name[ref_name],
        f06,
        sample_rate_hz,
        recipe,
        manifest,
        cancellation,
    )
    f07 = _compute_f07(result, samples, sample_rate_hz, recipe, cancellation)
    f08 = _compute_f08(samples, root_events.events, sample_rate_hz, recipe, cancellation)
    f09 = _compute_f09(root_events, recipe, cancellation)
    f10 = _compute_f10(
        samples,
        phase,
        means,
        sample_rate_hz,
        recipe,
        clipping,
        cancellation,
    )
    bands = resolve_characterization_bands(recipe, sample_rate_hz)
    _checkpoint(cancellation)
    f15 = _compute_f15(
        samples,
        phase,
        means,
        f10,
        root_events,
        bands,
        sample_rate_hz,
        recipe,
        cancellation,
    )
    _checkpoint(cancellation)
    bundle, arrays, tables = build_characterization_bundle(
        result,
        f02,
        f03,
        f04,
        f05,
        f06,
        f07,
        f08,
        f09,
        f10,
        f15,
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
