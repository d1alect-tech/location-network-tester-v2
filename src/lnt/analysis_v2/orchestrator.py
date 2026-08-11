"""Integrity-checked orchestration of immutable optional analysis branches."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path  # noqa: TC003 - runtime artifact paths
from typing import Final

import numpy as np

from lnt.analysis_store import (
    AnalysisRecipe,
    ArtifactCorruptError,
    ArtifactInputs,
    ArtifactStore,
    CodeIdentity,
    NamedDigest,
)
from lnt.scope_io import NEVER_CANCELLED, CancellationToken

from .projection import project_default
from .types import (
    AnalysisCancelledError,
    AnalysisEngine,
    AnalysisRunResult,
    BranchContext,
    BranchFailure,
    SessionKind,
)

ProgressCallback = Callable[[str, int, int], None]
MAX_CHUNK_SECONDS: Final = 0.25
_DISPATCH: Final = {
    SessionKind.MEASUREMENT: ("psd", "spectrogram", "events", "features", "correction"),
    SessionKind.SELF_NOISE: ("psd", "spectrogram", "events", "features"),
    SessionKind.LINE_QUALITY: ("line_quality",),
}


class AnalysisOrchestrator:
    """Runs branch adapters while preserving raw capture and valid siblings."""

    def __init__(
        self, *, engine: AnalysisEngine, code_identity: CodeIdentity | None = None
    ) -> None:
        """Bind an engine and deterministic execution identity."""
        self._engine: AnalysisEngine = engine
        self._code_identity: CodeIdentity = code_identity or CodeIdentity.current()

    def run(  # noqa: C901, PLR0913 - orchestration boundary owns explicit run controls
        self,
        session_dir: Path,
        recipe: AnalysisRecipe,
        *,
        cancellation: CancellationToken = NEVER_CANCELLED,
        progress: ProgressCallback | None = None,
        project_legacy: bool = True,
        chunk_seconds: float = 0.25,
    ) -> AnalysisRunResult:
        """Validate cache, dispatch branches, publish atomically, then project default."""
        if not 0 < chunk_seconds <= MAX_CHUNK_SECONDS:
            raise ValueError("analysis chunk_seconds must be in (0, 0.25]")
        kind, sample_rate_hz = _session_metadata(session_dir)
        channel_paths = tuple(session_dir / f"{name}.npy" for name in recipe.channels)
        inputs = _artifact_inputs(recipe, channel_paths, self._code_identity)
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
                failures=_load_failures(cached),
            )
        channels = tuple(np.load(path, mmap_mode="r", allow_pickle=False) for path in channel_paths)
        context = BranchContext(
            kind=kind,
            session_dir=session_dir,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            recipe=recipe,
            cancellation=cancellation,
        )
        outputs: dict[str, bytes] = {}
        failures: list[BranchFailure] = []
        branches = _DISPATCH[kind]
        for index, branch in enumerate(branches, start=1):
            context.checkpoint()
            if progress is not None:
                progress(branch, index - 1, len(branches))
            try:
                branch_output = self._engine.run_branch(branch, context)
            except AnalysisCancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - branch boundary isolates optional engines
                failures.append(
                    BranchFailure(
                        branch=branch, error_type=type(error).__name__, message=str(error)
                    )
                )
            else:
                outputs.update(branch_output.files)
        context.checkpoint()
        outputs["branch-status.json"] = _encode_failures(failures)
        artifact_dir = store.publish(inputs, outputs)
        if project_legacy:
            project_default(session_dir, artifact_dir)
        if progress is not None:
            progress("done", len(branches), len(branches))
        return AnalysisRunResult(
            artifact_key=inputs.artifact_key,
            artifact_dir=artifact_dir,
            cache_hit=False,
            failures=tuple(failures),
        )


def _session_metadata(session_dir: Path) -> tuple[SessionKind, float]:
    payload = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
    return SessionKind(payload["session_type"]), float(payload["sample_rate_hz"])


def _artifact_inputs(
    recipe: AnalysisRecipe, channel_paths: tuple[Path, ...], identity: CodeIdentity
) -> ArtifactInputs:
    raw = tuple(
        NamedDigest(name=path.name, digest=hashlib.sha256(path.read_bytes()).hexdigest())
        for path in channel_paths
    )
    return ArtifactInputs(
        recipe_sha256=recipe.recipe_sha256,
        raw_inputs=raw,
        context_dependencies=(),
        profile_dependencies=(),
        calibration_dependencies=(),
        code_identity=identity,
    )


def _encode_failures(failures: list[BranchFailure]) -> bytes:
    payload = [
        {
            "branch": failure.branch,
            "error_type": failure.error_type,
            "message": failure.message,
        }
        for failure in failures
    ]
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _load_failures(artifact_dir: Path) -> tuple[BranchFailure, ...]:
    payload = json.loads((artifact_dir / "branch-status.json").read_text(encoding="utf-8"))
    return tuple(BranchFailure(**item) for item in payload)
