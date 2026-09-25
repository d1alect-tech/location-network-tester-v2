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
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.analysis_v2.types import Float32Array
    from lnt.context.json_codec import JsonValue

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 8000.0
_F03_INDEX = 2
_F04_INDEX = 3
_F05_INDEX = 4
_F06_INDEX = 5
_F07_INDEX = 6
_F08_INDEX = 7
_F09_INDEX = 8
_F10_INDEX = 9
_F11_INDEX = 10
_F13_INDEX = 12
_F14_INDEX = 13
_F15_INDEX = 14
_F16_INDEX = 15
_COMPUTED_INDICES = frozenset(
    {
        0,
        1,
        _F03_INDEX,
        _F04_INDEX,
        _F05_INDEX,
        _F06_INDEX,
        _F07_INDEX,
        _F08_INDEX,
        _F09_INDEX,
        _F10_INDEX,
        _F11_INDEX,
        _F13_INDEX,
        _F14_INDEX,
        _F15_INDEX,
        _F16_INDEX,
    }
)


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


def _session(path: Path, *, duration_s: float = 2.4) -> Path:
    # resolve_clipping reads only channel meta, source and telemetry from the
    # manifest, so the shared fixture's declared sample_count need not match the
    # arrays written here.
    write_manifest(path)
    n = round(_FS_HZ * duration_s)
    t = np.arange(n, dtype=np.float64) / _FS_HZ
    signal = (6.0 * np.sin(2.0 * np.pi * 50.0 * t + 0.4)).astype(np.float32)
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


def _measured_only_recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    assert isinstance(mapping, dict)
    mapping["channels"] = ["ch2", "ch1"]
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


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
    f05 = loaded.bundle.families[_F05_INDEX]
    assert f05.family_id == "f05_phase_conditioned_statistics"
    # F05 считается по циклам CH2, поэтому заглушками остаются только
    # семейства, которые ещё не реализованы.
    assert f05.reason_codes != ("not_computed",)
    f06 = loaded.bundle.families[_F06_INDEX]
    assert f06.family_id == "f06_modulation_trajectories"
    assert f06.reason_codes != ("not_computed",)
    f03 = loaded.bundle.families[_F03_INDEX]
    assert f03.family_id == "f03_interharmonic_tracking"
    assert f03.reason_codes != ("not_computed",)
    f04 = loaded.bundle.families[_F04_INDEX]
    assert f04.family_id == "f04_multicycle_periodicity"
    assert f04.reason_codes != ("not_computed",)
    f07 = loaded.bundle.families[_F07_INDEX]
    assert f07.family_id == "f07_comb_sideband_cepstrum"
    assert f07.reason_codes != ("not_computed",)
    f08 = loaded.bundle.families[_F08_INDEX]
    assert f08.family_id == "f08_transient_morphology"
    assert f08.reason_codes != ("not_computed",)
    f09 = loaded.bundle.families[_F09_INDEX]
    assert f09.family_id == "f09_event_ordering"
    assert f09.reason_codes != ("not_computed",)
    f10 = loaded.bundle.families[_F10_INDEX]
    assert f10.family_id == "f10_threshold_episode_surface"
    assert f10.reason_codes != ("not_computed",)
    f11 = loaded.bundle.families[_F11_INDEX]
    assert f11.family_id == "f11_conditional_distributions"
    assert f11.reason_codes != ("not_computed",)
    f13 = loaded.bundle.families[_F13_INDEX]
    assert f13.family_id == "f13_band_envelope_coactivity"
    assert f13.reason_codes != ("not_computed",)
    f14 = loaded.bundle.families[_F14_INDEX]
    assert f14.family_id == "f14_cross_channel_event_association"
    assert f14.reason_codes != ("not_computed",)
    f16 = loaded.bundle.families[_F16_INDEX]
    assert f16.family_id == "f16_multiscale_memory"
    assert f16.reason_codes != ("not_computed",)
    placeholder = tuple(
        family
        for index, family in enumerate(loaded.bundle.families)
        if index not in _COMPUTED_INDICES
    )
    assert len(placeholder) == 3
    assert all(family.status is Status.UNAVAILABLE for family in placeholder)
    assert all(family.reason_codes == ("not_computed",) for family in placeholder)


def test_seam_publishes_f02_beside_f01(tmp_path: Path) -> None:
    session = _session(tmp_path / "session")

    result = run_characterization(
        _recipe(), session, _load(session), _FS_HZ, code_identity=_identity("test")
    )

    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f02 = loaded.bundle.families[1]
    assert f02.family_id == "f02_amplitude_time_shape"
    # A clean sine delimits no root event, so the baseline the method requires
    # does not exist for any event: declared code, never a fabricated (a, tau).
    assert f02.status is Status.UNAVAILABLE
    assert f02.reason_codes == ("baseline_unavailable",)
    assert f02.array_refs == ()
    assert loaded.bundle.families[2].reason_codes != ("not_computed",)


def test_seam_reports_f02_template_unavailable_when_f01_is_unavailable(tmp_path: Path) -> None:
    # 1.0 s at 8 kHz gives 5 complete 0.2 s windows, below the 12-window minimum.
    session = _session(tmp_path / "session", duration_s=1.0)

    result = run_characterization(
        _recipe(), session, _load(session), _FS_HZ, code_identity=_identity("test")
    )

    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    assert loaded.bundle.families[0].reason_codes == ("window_too_short",)
    f02 = loaded.bundle.families[1]
    assert f02.status is Status.UNAVAILABLE
    assert f02.reason_codes == ("template_unavailable",)


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


def test_second_declared_channel_selects_measured_plane(tmp_path: Path) -> None:
    session = _session(tmp_path / "session")
    recipe = _measured_only_recipe()
    assert recipe.channels == ("ch2", "ch1")
    assert recipe.phase.reference_channel == "ch2"
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch2, ch1), _FS_HZ)

    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    assert loaded.bundle.families[0].signal_plane == "ch1_scope_input"


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
