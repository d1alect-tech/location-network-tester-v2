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
from lnt.characterization.f01_bundle import build_f01_bundle
from lnt.characterization.f01_phase_cycle import compute_f01_phase_cycle
from lnt.scope_io import NEVER_CANCELLED, CancellationToken

from .artifact_inputs import characterization_inputs
from .types import AnalysisCancelledError, AnalysisRunResult, Float32Array

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

    Ключ строится из recipe_sha256, sha256_file сырых каналов, явных
    digest tunables и CodeIdentity; повторный прогон возвращает cache_hit.
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
    samples = channel_by_name.get("ch1", channels[0])
    result = compute_f01_phase_cycle(
        samples,
        sample_rate_hz=sample_rate_hz,
        sync_reference=channel_by_name.get("ch2"),
    )
    _checkpoint(cancellation)
    bundle, arrays, tables = build_f01_bundle(result, recipe)
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
