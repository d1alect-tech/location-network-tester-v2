"""F05 E2E-reduced через реальный seam: аналитика меандра, cache, raw-хеши.

Истина здесь не выведена из движка: цикл это 50 Гц меандр со скважностью
50 %, поэтому первая половина фазовых бинов обязана лечь на верхнюю полку,
а вторая — на нижнюю. Это проверяет всю цепочку CH2-циклы → бины → моменты.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.context.json_codec import decode_object
from tests.test_ui_sessions import write_manifest

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 8000.0
_DURATION_S = 2.4
_SEED = 6022
_F05_INDEX = 4
_BINS = 64
_MINIMUM_SUPPORT_PER_BIN = 20


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f05 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _pulse_session(path: Path) -> Path:
    """CH2 это чистый 50 Гц синус (опора фазы), CH1 — меандр той же фазы.

    Меандр начинается ровно в t = 0, как и синус, поэтому истина известна:
    одна смена полки за цикл.
    """
    write_manifest(path)
    n = round(_FS_HZ * _DURATION_S)
    period = round(_FS_HZ / 50.0)
    rng = np.random.default_rng(_SEED)
    t = np.arange(n, dtype=np.float64) / _FS_HZ
    offset = np.arange(n) % period
    square = np.where(offset < period // 2, 1.0, 0.0)
    np.save(path / "ch1.npy", (rng.standard_normal(n) * 0.01 + square).astype(np.float32))
    np.save(path / "ch2.npy", (6.0 * np.sin(2.0 * np.pi * 50.0 * t)).astype(np.float32))
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


def test_pulse_train_phase_bins_recover_the_known_square(tmp_path: Path) -> None:
    session = _pulse_session(tmp_path / "syn-pulse")
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f05 = loaded.bundle.families[_F05_INDEX]

    assert first.cache_hit is False
    assert f05.family_id == "f05_phase_conditioned_statistics"
    assert f05.status is Status.AVAILABLE
    assert f05.reason_codes == ()
    assert {reference.array_id for reference in f05.array_refs} == {
        "f05_mu_v",
        "f05_sigma2_v2",
        "f05_ms_v2",
        "f05_p_event",
        "f05_n_b",
    }
    assert f05.signal_plane == "ch1_scope_input"

    means = loaded.arrays["f05_mu_v"]
    assert means.shape == (_BINS,)
    # Истина: меандр 50 % даёт ровно одну смену полки за цикл, и она обязана
    # лечь на середину цикла: бины 0..31 это верхняя полка, 32..63 нижняя.
    falling = np.flatnonzero(means < 0.5)
    assert falling.size > 0
    boundary = int(falling[0])
    assert 31 <= boundary <= 33
    # Бин у самой границы смешанный, поэтому из сверки исключён.
    assert float(np.min(means[: boundary - 1])) == pytest.approx(1.0, abs=0.05)
    assert float(np.max(means[boundary + 1 :])) == pytest.approx(0.0, abs=0.05)

    probabilities = loaded.arrays["f05_p_event"]
    assert float(np.min(probabilities)) >= 0.0
    assert float(np.max(probabilities)) <= 1.0
    counts = loaded.arrays["f05_n_b"]
    assert int(np.min(counts)) >= _MINIMUM_SUPPORT_PER_BIN
    assert f05.support.sample_count == _BINS
    assert f05.support.observation_count == _BINS
    assert f05.support.missing_count == 0

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before
