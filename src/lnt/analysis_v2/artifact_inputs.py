"""Settings-hash context for analysis-v2 artifact cache keys."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path  # noqa: TC003 - runtime artifact paths
from typing import TYPE_CHECKING, Final

from lnt.analysis_store import AnalysisRecipe, ArtifactInputs, CodeIdentity, NamedDigest
from lnt.apd import apd_preset
from lnt.audio_panel import audio_panel_preset
from lnt.burst import burst_preset
from lnt.harmonics import harmonics_preset
from lnt.notching import notching_preset
from lnt.power_quality import power_quality_preset
from lnt.trends import trends_preset

from .types import SessionKind

if TYPE_CHECKING:
    from collections.abc import Mapping

_DIGEST_CHUNK_BYTES: Final = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Стриминговый SHA-256 файла порциями по 1 МиБ; значение как у read_bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_DIGEST_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_inputs(
    recipe: AnalysisRecipe,
    channel_paths: tuple[Path, ...],
    identity: CodeIdentity,
    kind: SessionKind | None = None,
) -> ArtifactInputs:
    """Build cache inputs: raw channel digests plus kind-specific settings hashes."""
    raw = tuple(NamedDigest(name=path.name, digest=sha256_file(path)) for path in channel_paths)
    context: tuple[NamedDigest, ...] = ()
    if kind is SessionKind.POWER_QUALITY:
        context = (_power_quality_dependency(),)
    elif kind is SessionKind.MEASUREMENT:
        context = (
            _audio_panel_dependency(),
            _harmonics_dependency(),
            _notching_dependency(),
            _apd_dependency(),
            _burst_dependency(),
            _trends_dependency(),
        )
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


def _settings_digest(name: str, payload: Mapping[str, object]) -> NamedDigest:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return NamedDigest(name=name, digest=digest)


def _audio_panel_dependency() -> NamedDigest:
    return _settings_digest(
        "audio_panel_settings.json", audio_panel_preset("audio_default").to_dict()
    )


def _power_quality_dependency() -> NamedDigest:
    return _settings_digest(
        "power_quality_settings.json", power_quality_preset("itic_default").to_dict()
    )


def _notching_dependency() -> NamedDigest:
    return _settings_digest("notching_settings.json", notching_preset("notching_default").to_dict())


def _apd_dependency() -> NamedDigest:
    return _settings_digest("apd_settings.json", apd_preset("apd_default").to_dict())


def _burst_dependency() -> NamedDigest:
    return _settings_digest("burst_settings.json", burst_preset("burst_default").to_dict())


def _trends_dependency() -> NamedDigest:
    return _settings_digest("trends_settings.json", trends_preset("trends_default").to_dict())


def _harmonics_dependency() -> NamedDigest:
    return _settings_digest(
        "harmonics_settings.json", harmonics_preset("harmonics_default").to_dict()
    )
