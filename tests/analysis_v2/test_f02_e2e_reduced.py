"""F02 E2E-reduced через реальный seam: codes/values пути, cache, raw-хеши, S4."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, CharacterizationBundle, Status, load_bundle
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session
from tests.test_ui_sessions import write_manifest

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_REFERENCE_FS_HZ = 500000.0
_REFERENCE_DURATION_S = 2.4
_REFERENCE_SEED = 6022
_PULSE_FS_HZ = 8000.0
_F02_INDEX = 1
_F05_INDEX = 4
_F06_INDEX = 5


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _changed_recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "e2e reduced")
    assert isinstance(mapping["events"], dict)
    mapping["events"]["threshold_sigma"] = 7.0
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _reference_session(root: Path) -> Path:
    session = simulate_session(
        out_dir=root / "syn-bad-seed6022",
        profile="bad",
        duration_s=_REFERENCE_DURATION_S,
        sample_rate_hz=_REFERENCE_FS_HZ,
        seed=_REFERENCE_SEED,
    )
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert session.name == manifest["session_id"]
    return session


def _pulse_session(path: Path) -> Path:
    """50 Гц импульсная periodic-волна: шаблон цикла совпадает с разметкой детектора."""
    write_manifest(path)
    n = round(_PULSE_FS_HZ * 2.4)
    period = round(_PULSE_FS_HZ / 50.0)
    rng = np.random.default_rng(6022)
    phase = np.arange(n) % period
    signal = rng.standard_normal(n) * 0.01 + np.where(phase < period // 2, 1.0, 0.0)
    array = signal.astype(np.float32)
    np.save(path / "ch1.npy", array)
    np.save(path / "ch2.npy", array)
    return path


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    ch1 = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2 = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)
    return ch1, ch2


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def _bundle(artifact_dir: Path) -> CharacterizationBundle:
    files = {name: (artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    return load_bundle(files).bundle


def test_reference_session_publishes_f02_with_cache_and_stable_raw(tmp_path: Path) -> None:
    session = _reference_session(tmp_path)
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _REFERENCE_FS_HZ)
    bundle = _bundle(first.artifact_dir)
    f02 = bundle.families[_F02_INDEX]

    assert first.cache_hit is False
    assert f02.family_id == "f02_amplitude_time_shape"
    # Измеренное поведение эталона: PARTIAL с подобранными значениями, не codes-only.
    assert f02.status is Status.PARTIAL
    assert f02.reason_codes != ("not_computed",)
    assert {reference.array_id for reference in f02.array_refs} == {
        "f02_a",
        "f02_tau_s",
        "f02_rho",
        "f02_e_res_v2_s",
    }
    assert f02.comparison_summary[0].name == "f02_event_count"
    assert f02.comparison_summary[0].value > 0
    f05 = bundle.families[_F05_INDEX]
    assert f05.family_id == "f05_phase_conditioned_statistics"
    assert f05.reason_codes != ("not_computed",)
    f06 = bundle.families[_F06_INDEX]
    assert f06.family_id == "f06_modulation_trajectories"
    assert f06.reason_codes != ("not_computed",)
    rest = tuple(
        family
        for index, family in enumerate(bundle.families)
        if index not in {0, _F02_INDEX, _F05_INDEX, _F06_INDEX}
    )
    assert rest
    assert all(family.status is Status.UNAVAILABLE for family in rest)
    assert all(family.reason_codes == ("not_computed",) for family in rest)

    second = run_characterization(recipe, session, (ch1, ch2), _REFERENCE_FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key

    third = run_characterization(_changed_recipe(), session, (ch1, ch2), _REFERENCE_FS_HZ)
    assert third.cache_hit is False
    assert third.artifact_key != first.artifact_key

    assert _raw_hashes(session) == before


def test_analytic_pulse_train_yields_available_f02_values(tmp_path: Path) -> None:
    session = _pulse_session(tmp_path / "syn-pulse")
    ch1, ch2 = _load(session)

    result = run_characterization(_recipe(), session, (ch1, ch2), _PULSE_FS_HZ)
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f02 = loaded.bundle.families[_F02_INDEX]

    assert f02.status is Status.AVAILABLE
    assert f02.reason_codes == ()
    assert f02.comparison_summary[0].value > 0
    gains = loaded.arrays["f02_a"]
    assert gains.size > 0
    # Импульсная волна: усиление относительно собственного шаблона близко к единице.
    # Медиана, а не среднее: события на краях записи подбираются по урезанному
    # спану и утягивают среднее вниз (измерено 0.866 при медиане 0.999).
    assert float(np.median(gains)) == pytest.approx(1.0, abs=0.05)
    assert float(np.max(loaded.arrays["f02_rho"])) < 0.25


def test_f01_family_unchanged_by_f02_slice_s4(tmp_path: Path) -> None:
    session = _reference_session(tmp_path)
    ch1, ch2 = _load(session)

    result = run_characterization(_recipe(), session, (ch1, ch2), _REFERENCE_FS_HZ)
    bundle = _bundle(result.artifact_dir)
    f01 = bundle.families[0]

    assert f01.family_id == "f01_phase_cycle"
    assert f01.status is Status.PARTIAL
    assert set(f01.reason_codes) == {"grid_unstable", "phase_unstable"}
    assert f01.comparison_summary[0].name == "f1_hz"
    assert 47.5 <= float(f01.comparison_summary[0].value) <= 52.5
