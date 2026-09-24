"""F15 E2E-reduced через реальный seam: четыре детерминированные моды.

Профиль ``bad`` даёт 1 200 000 отсчётов при 500 кГц: окно 0,02 с занимает
ровно 10 000 отсчётов, поэтому полная сетка содержит ``120`` окон. Рецепт F15
задаёт четыре медиоиды и восемь блоков стабильности; проверяются именно эти
закрытые истины, а не согласие движка с самим собой. Тихий профиль не может
стандартизировать признаки с нулевой MAD и обязан опубликовать отказ
``feature_scale_zero`` без выдуманных меток.
"""

from __future__ import annotations

import hashlib
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
_F15_INDEX = 14
_F15_ID = "f15_interpretable_modes"
_F15_METHOD = "deterministic_pam_fixed_k_medoids"
_F15_METHOD_VERSION = 1
_WINDOW_S = 0.02
_WINDOW_SAMPLES = 10_000
_COMPLETE_WINDOWS = 120
_ARRAY_IDS = {
    "f15_feature_medians",
    "f15_feature_mads",
    "f15_standardized_features",
    "f15_window_indices",
    "f15_medoid_indices",
    "f15_medoid_features",
    "f15_medoid_rms_v",
    "f15_labels",
    "f15_dwell_labels",
    "f15_dwell_durations_s",
    "f15_transition_counts",
    "f15_transition_probabilities",
    "f15_stability_ari",
}


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f15 e2e reduced")
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


def _artifact_bytes(artifact_dir: Path) -> dict[str, bytes]:
    return {name: (artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}


def test_bad_profile_publishes_four_modes_and_stability_truth(tmp_path: Path) -> None:
    """Плотный профиль вычисляет четыре моды; F10 сначала публикует MAD-масштаб."""
    session = _session(tmp_path, "syn-bad-500k", "bad")
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    first_files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(first_files)
    f15 = loaded.bundle.families[_F15_INDEX]
    declared = recipe.families[_F15_INDEX]

    assert first.cache_hit is False
    assert f15.family_id == declared.id == _F15_ID
    assert f15.method == declared.method == _F15_METHOD
    assert f15.method_version == declared.method_version == _F15_METHOD_VERSION
    assert f15.status is Status.AVAILABLE
    assert f15.reason_codes == ()
    assert f15.signal_plane == "ch1_scope_input"
    assert f15.window.kind == "fixed"
    assert f15.window.duration_s == _WINDOW_S
    assert f15.window.overlap_fraction == 0.0
    assert f15.support.sample_count == _COMPLETE_WINDOWS
    assert f15.support.observation_count == f15.n
    assert {reference.array_id for reference in f15.array_refs} == _ARRAY_IDS

    # 500 kHz * 0,02 s = 10 000 отсчётов; 1 200 000 / 10 000 = 120 окон.
    assert round(_FS_HZ * _WINDOW_S) == _WINDOW_SAMPLES
    assert round(_FS_HZ * _DURATION_S) // _WINDOW_SAMPLES == _COMPLETE_WINDOWS

    labels = loaded.arrays["f15_labels"]
    medoid_indices = loaded.arrays["f15_medoid_indices"]
    assert medoid_indices.shape == (4,)
    assert set(np.unique(labels).tolist()) == {0, 1, 2, 3}
    assert bool(np.all(np.isin(labels, np.arange(4))))

    counts = loaded.arrays["f15_transition_counts"]
    probabilities = loaded.arrays["f15_transition_probabilities"]
    row_totals = counts.sum(axis=1)
    active = row_totals > 0
    assert counts.shape == (4, 4)
    assert probabilities.shape == (4, 4)
    assert int(counts.sum()) == labels.size - 1
    assert bool(np.allclose(probabilities[active].sum(axis=1), 1.0, rtol=0.0, atol=1e-12))
    assert bool(
        np.allclose(
            probabilities[active], counts[active] / row_totals[active, None], rtol=0.0, atol=1e-12
        )
    )
    # Восемь блоков объявлены рецептом; блок не исчезает без stability-кода.
    assert "stability_block_too_short" not in f15.reason_codes
    assert loaded.arrays["f15_stability_ari"].shape == (8,)

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == first_files
    assert _raw_hashes(session) == before


def test_quiet_profile_declares_zero_feature_scale(tmp_path: Path) -> None:
    """Тихая запись имеет нулевую MAD-оценку: режим отказа, не нулевые моды."""
    session = _session(tmp_path, "syn-quiet-500k", "quiet")
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    loaded = load_bundle(_artifact_bytes(result.artifact_dir))
    f15 = loaded.bundle.families[_F15_INDEX]
    declared = recipe.families[_F15_INDEX]

    assert result.cache_hit is False
    assert f15.family_id == declared.id == _F15_ID
    assert f15.method == declared.method == _F15_METHOD
    assert f15.method_version == declared.method_version == _F15_METHOD_VERSION
    assert f15.status is Status.UNAVAILABLE
    assert f15.reason_codes == ("feature_scale_zero",)
    assert f15.array_refs == ()
    assert f15.table_refs == ()
    assert f15.comparison_summary == ()
    assert not any(name.startswith("f15_") for name in loaded.arrays)
