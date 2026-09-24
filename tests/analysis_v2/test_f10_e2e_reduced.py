"""F10 E2E-reduced через реальный seam: поверхность порог × длительность × фаза.

Истина аналитическая, не из движка: поверхность обязана иметь объявленную сетку
4 порога × 5 длительностей × 64 фазовых бина = 1280 ячеек
(``docs/examples/characterization-recipe-v2.json``). Тихий профиль укладывается
в кап ``maximum_episodes=4096`` и публикуется AVAILABLE; шумный профиль
превышает кап и объявляет ``artifact_limit`` PARTIAL, а не молча отбрасывает.
Граница заявки закреплена в докстринге маппера: поверхность описывает превышение
порога на одной плоскости канала и не измеряет энергию, повреждение или источник.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, Unit, load_bundle
from lnt.context.json_codec import decode_object
from lnt.simulate import simulate_session

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 60000.0
_DURATION_S = 2.4
_SEED = 6022
_F10_INDEX = 9
_THRESHOLDS = 4
_DURATIONS = 5
_PHASE_BINS = 64
_QUANTILES = 3
_CELL = (_THRESHOLDS, _DURATIONS, _PHASE_BINS)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f10 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _session(root: Path, name: str, profile: str) -> Path:
    return simulate_session(
        out_dir=root / name,
        profile=profile,
        duration_s=_DURATION_S,
        sample_rate_hz=_FS_HZ,
        seed=_SEED,
    )


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    ch1 = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2 = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)
    return ch1, ch2


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def test_quiet_profile_publishes_full_threshold_surface(tmp_path: Path) -> None:
    session = _session(tmp_path, "syn-quiet-60k", "quiet")
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f10 = loaded.bundle.families[_F10_INDEX]

    assert first.cache_hit is False
    assert f10.family_id == "f10_threshold_episode_surface"
    assert f10.status is Status.AVAILABLE
    assert f10.reason_codes == ()
    assert f10.signal_plane == "ch1_scope_input"
    assert f10.window.kind == "record"

    # Объявленная сетка: 4 × 5 × 64 = 1280 ячеек, оси публикуются рядом.
    occupancy = loaded.arrays["f10_occupancy"]
    assert occupancy.shape == _CELL
    assert loaded.arrays["f10_threshold_sigma"].shape == (_THRESHOLDS,)
    assert loaded.arrays["f10_minimum_duration_s"].shape == (_DURATIONS,)
    assert loaded.arrays["f10_phase_bin"].shape == (_PHASE_BINS,)
    assert loaded.arrays["f10_episode_quantile_v2_s"].shape == (*_CELL, _QUANTILES)
    assert bool(np.all(occupancy >= 0.0))
    assert bool(np.all(occupancy <= 1.0))

    v2s_unit = next(r.unit for r in f10.array_refs if r.array_id == "f10_total_v2_s")
    assert v2s_unit is Unit.V2_S

    summaries = {item.name: float(item.value) for item in f10.comparison_summary}
    assert summaries["f10_full_episode_count"] > 0.0
    assert summaries["f10_omitted_episode_count"] == 0.0

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before


def test_noisy_profile_declares_artifact_limit_partial(tmp_path: Path) -> None:
    """Шумная запись превышает кап эпизодов: PARTIAL с кодом, а не молчаливый сброс."""
    session = _session(tmp_path, "syn-bad-60k", "bad")
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f10 = loaded.bundle.families[_F10_INDEX]

    assert result.cache_hit is False
    assert f10.status is Status.PARTIAL
    assert "artifact_limit" in f10.reason_codes
    summaries = {item.name: float(item.value) for item in f10.comparison_summary}
    # Кап хранения связан: полный счётчик больше сохранённого, пропуск объявлен.
    assert summaries["f10_full_episode_count"] > summaries["f10_stored_episode_count"]
    assert summaries["f10_omitted_episode_count"] > 0.0
