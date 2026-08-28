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
from lnt.apd import apd_preset
from lnt.audio_panel import audio_panel_preset
from lnt.burst import burst_preset
from lnt.errors import InputError
from lnt.harmonics import harmonics_preset
from lnt.notching import notching_preset
from lnt.power_quality import power_quality_preset
from lnt.scope_io import NEVER_CANCELLED, CancellationToken
from lnt.trends import trends_preset

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
_DIGEST_CHUNK_BYTES: Final = 1024 * 1024
_DISPATCH: Final = {
    SessionKind.MEASUREMENT: (
        "psd",
        "spectrogram",
        "events",
        "features",
        "correction",
        "audio_panel",
    ),
    SessionKind.SELF_NOISE: ("psd", "spectrogram", "events", "features"),
    SessionKind.LINE_QUALITY: ("line_quality",),
    SessionKind.CM_DM: ("cm_dm",),
    SessionKind.POWER_QUALITY: ("power_quality",),
    SessionKind.NOTCHING: ("notching",),
    SessionKind.HARMONICS: ("harmonics",),
    SessionKind.BURST: ("burst",),
    SessionKind.APD: ("apd",),
    SessionKind.TRENDS: ("trends",),
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
        inputs = _artifact_inputs(recipe, channel_paths, self._code_identity, kind)
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
    raw_kind = payload["session_type"]
    try:
        kind = SessionKind(raw_kind)
    except ValueError as error:
        raise InputError(f"неизвестный для анализа тип сессии: {raw_kind!r}") from error
    return kind, float(payload["sample_rate_hz"])


def _sha256_file(path: Path) -> str:
    """Стриминговый SHA-256 файла порциями по 1 МиБ; значение как у read_bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_DIGEST_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_inputs(
    recipe: AnalysisRecipe,
    channel_paths: tuple[Path, ...],
    identity: CodeIdentity,
    kind: SessionKind | None = None,
) -> ArtifactInputs:
    raw = tuple(NamedDigest(name=path.name, digest=_sha256_file(path)) for path in channel_paths)
    context: tuple[NamedDigest, ...] = ()
    if kind is SessionKind.POWER_QUALITY:
        context = (_power_quality_dependency(),)
    elif kind is SessionKind.MEASUREMENT:
        context = (_audio_panel_dependency(),)
    elif kind is SessionKind.NOTCHING:
        context = (_notching_dependency(),)
    elif kind is SessionKind.HARMONICS:
        context = (_harmonics_dependency(),)
    elif kind is SessionKind.BURST:
        context = (_burst_dependency(),)
    elif kind is SessionKind.APD:
        context = (_apd_dependency(),)
    elif kind is SessionKind.TRENDS:
        context = (_trends_dependency(),)
    return ArtifactInputs(
        recipe_sha256=recipe.recipe_sha256,
        raw_inputs=raw,
        context_dependencies=context,
        profile_dependencies=(),
        calibration_dependencies=(),
        code_identity=identity,
    )


def _audio_panel_dependency() -> NamedDigest:
    settings = audio_panel_preset("audio_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return NamedDigest(name="audio_panel_settings.json", digest=digest)


def _power_quality_dependency() -> NamedDigest:
    settings = power_quality_preset("itic_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return NamedDigest(name="power_quality_settings.json", digest=digest)


def _notching_dependency() -> NamedDigest:
    settings = notching_preset("notching_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return NamedDigest(name="notching_settings.json", digest=digest)


def _apd_dependency() -> NamedDigest:
    settings = apd_preset("apd_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return NamedDigest(name="apd_settings.json", digest=digest)


def _burst_dependency() -> NamedDigest:
    settings = burst_preset("burst_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return NamedDigest(name="burst_settings.json", digest=digest)


def _trends_dependency() -> NamedDigest:
    settings = trends_preset("trends_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return NamedDigest(name="trends_settings.json", digest=digest)


def _harmonics_dependency() -> NamedDigest:
    settings = harmonics_preset("harmonics_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return NamedDigest(name="harmonics_settings.json", digest=digest)


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
