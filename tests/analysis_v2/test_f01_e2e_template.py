"""F01 E2E-шаблон на эталоне 500 кГц/2.4 с (todo 10, переиспользуем для Phase 2+).

Эталон: временная синтетика ``simulate_session(profile=bad, 500 кГц, 2.4 с,
seed 6022)``; CH1 — иголки без несущей 50 Гц, поэтому F01 PARTIAL
('grid_unstable', 'phase_unstable') — ожидаемо. AVAILABLE-на-эталоне требует
только analytic-синтетика (см. tests/characterization/test_f01_phase_cycle.py).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 500000.0
_DURATION_S = 2.4
_SEED = 6022
_F03_INDEX = 2
_F04_INDEX = 3
_F05_INDEX = 4
_F06_INDEX = 5
_F07_INDEX = 6
_F08_INDEX = 7
_F09_INDEX = 8
_F10_INDEX = 9
_F15_INDEX = 14
# Реализованные семейства (индекс -> объявленный ID). Один источник истины на
# проверку «семейство реально считалось» и на множество заглушек ниже.
_COMPUTED_IDS = {
    0: "f01_phase_cycle",
    1: "f02_amplitude_time_shape",
    _F03_INDEX: "f03_interharmonic_tracking",
    _F04_INDEX: "f04_multicycle_periodicity",
    _F05_INDEX: "f05_phase_conditioned_statistics",
    _F06_INDEX: "f06_modulation_trajectories",
    _F07_INDEX: "f07_comb_sideband_cepstrum",
    _F08_INDEX: "f08_transient_morphology",
    _F09_INDEX: "f09_event_ordering",
    _F10_INDEX: "f10_threshold_episode_surface",
    _F15_INDEX: "f15_interpretable_modes",
}
_COMPUTED_INDICES = frozenset(_COMPUTED_IDS)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "e2e template")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _changed_recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "e2e template")
    assert isinstance(mapping["events"], dict)
    mapping["events"]["threshold_sigma"] = 7.0
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _reference_session(root: Path) -> Path:
    session = simulate_session(
        out_dir=root / "syn-bad-seed6022",
        profile="bad",
        duration_s=_DURATION_S,
        sample_rate_hz=_FS_HZ,
        seed=_SEED,
    )
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert session.name == manifest["session_id"]
    return session


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def test_f01_e2e_reference_template_run_read_cache_rehash_raw(tmp_path: Path) -> None:
    session = _reference_session(tmp_path)
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1 = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2 = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)

    assert first.cache_hit is False
    assert first.artifact_dir.is_dir()
    assert first.failures == ()
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    assert len(loaded.bundle.families) == 18
    f01 = loaded.bundle.families[0]
    assert f01.family_id == "f01_phase_cycle"
    assert f01.status is Status.PARTIAL
    assert set(f01.reason_codes) == {"grid_unstable", "phase_unstable"}
    assert f01.signal_plane == "ch1_scope_input"
    assert f01.comparison_summary[0].name == "f1_hz"
    assert 47.5 <= float(f01.comparison_summary[0].value) <= 52.5
    # Каждое реализованное семейство обязано реально считаться: код заглушки
    # ``not_computed`` — признак пропущенного среза, поэтому его наличие здесь
    # означало бы, что seam не вызвал вычисление семейства.
    for index, family_id in _COMPUTED_IDS.items():
        family = loaded.bundle.families[index]
        assert family.family_id == family_id
        assert family.reason_codes != ("not_computed",)
    # F05 считает CH1 по циклам CH2, поэтому на эталоне она не заглушка;
    # заглушками остаётся всё, кроме одиннадцати работающих семейств.
    rest = tuple(
        family
        for index, family in enumerate(loaded.bundle.families)
        if index not in _COMPUTED_INDICES
    )
    assert rest
    assert all(family.status is Status.UNAVAILABLE for family in rest)
    assert all(family.reason_codes == ("not_computed",) for family in rest)

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir

    third = run_characterization(_changed_recipe(), session, (ch1, ch2), _FS_HZ)
    assert third.cache_hit is False
    assert third.artifact_key != first.artifact_key

    assert _raw_hashes(session) == before
