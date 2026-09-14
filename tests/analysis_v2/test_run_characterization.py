"""Characterization seam: publish, cache-hit, recipe-change, version-bump, cancel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, CodeIdentity, parse_analysis_recipe
from lnt.analysis_v2 import AnalysisCancelledError, run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.context.json_codec import decode_object
from lnt.scope_io import CancellationToken

if TYPE_CHECKING:
    from lnt.analysis_v2.types import Float32Array
    from lnt.context.json_codec import JsonValue

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 8000.0


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _changed_recipe(field: str, value: JsonValue) -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    assert isinstance(mapping["events"], dict)
    mapping["events"][field] = value
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _session(path: Path) -> Path:
    n = round(_FS_HZ * 2.4)
    t = np.arange(n, dtype=np.float64) / _FS_HZ
    signal = (6.0 * np.sin(2.0 * np.pi * 50.0 * t + 0.4)).astype(np.float32)
    path.mkdir()
    np.save(path / "ch1.npy", signal)
    np.save(path / "ch2.npy", signal)
    return path


def _identity(tag: str) -> CodeIdentity:
    return CodeIdentity(lnt=tag, numpy=np.__version__, scipy="test")


def _load(session: Path) -> tuple[Float32Array, ...]:
    ch1: Float32Array = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2: Float32Array = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)
    return (ch1, ch2)


def _code_identity(manifest_dir: Path) -> str:
    payload = json.loads((manifest_dir / "analysis-manifest.json").read_text(encoding="utf-8"))
    assert isinstance(payload["inputs"]["code_identity"], str)
    return payload["inputs"]["code_identity"]


def test_publishes_bundle_with_manifest_code_identity(tmp_path: Path) -> None:
    session = _session(tmp_path / "session")
    identity = _identity("test")

    result = run_characterization(
        _recipe(), session, _load(session), _FS_HZ, code_identity=identity
    )

    assert result.cache_hit is False
    assert result.artifact_dir.is_dir()
    assert result.failures == ()
    assert _code_identity(result.artifact_dir) == identity.identity_string
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    assert loaded.bundle.families[0].status is Status.AVAILABLE
    unavailable = loaded.bundle.families[1:]
    assert unavailable
    assert all(family.status is Status.UNAVAILABLE for family in unavailable)
    assert all(family.reason_codes == ("not_computed",) for family in unavailable)


def test_identical_rerun_is_cache_hit_without_recompute(tmp_path: Path) -> None:
    session = _session(tmp_path / "session")
    recipe = _recipe()
    first = run_characterization(
        recipe, session, _load(session), _FS_HZ, code_identity=_identity("test")
    )
    keys_before = sorted(path.name for path in (session / "analyses").iterdir())

    second = run_characterization(
        recipe, session, _load(session), _FS_HZ, code_identity=_identity("test")
    )

    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert sorted(path.name for path in (session / "analyses").iterdir()) == keys_before


def test_recipe_change_gives_new_artifact_key(tmp_path: Path) -> None:
    session = _session(tmp_path / "session")

    first = run_characterization(_recipe(), session, _load(session), _FS_HZ)
    second = run_characterization(
        _changed_recipe("threshold_sigma", 7.0), session, _load(session), _FS_HZ
    )

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert second.artifact_key != first.artifact_key
    assert second.artifact_dir != first.artifact_dir


def test_version_bump_gives_new_artifact_key(tmp_path: Path) -> None:
    session = _session(tmp_path / "session")
    recipe = _recipe()

    first = run_characterization(
        recipe, session, _load(session), _FS_HZ, code_identity=_identity("test-1")
    )
    second = run_characterization(
        recipe, session, _load(session), _FS_HZ, code_identity=_identity("test-2")
    )

    assert second.artifact_key != first.artifact_key
    assert _code_identity(second.artifact_dir) == _identity("test-2").identity_string


def test_cancellation_publishes_nothing(tmp_path: Path) -> None:
    session = _session(tmp_path / "session")

    with pytest.raises(AnalysisCancelledError):
        run_characterization(
            _recipe(),
            session,
            _load(session),
            _FS_HZ,
            CancellationToken(is_cancelled=lambda: True),
        )

    assert not (session / "analyses").exists() or not tuple(
        (session / "analyses").glob("*.partial-*")
    )
