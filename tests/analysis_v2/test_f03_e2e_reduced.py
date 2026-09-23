"""F03 E2E-reduced через реальный seam: тон 125 Гц обязан дать трек, чистый 50 Гц — отказ.

Истина аналитическая, не из движка: сеть 50 Гц даёт F01 оценку f1, на её сетке
тон 0.5 В на 125 Гц это ровно k=25 (бин f1/10 = 5 Гц), RMS 0.5/sqrt(2);
гармоника-чистый сигнал не содержит IHG-энергии, поэтому треков нет
и семейство UNAVAILABLE ``peak_not_observed``.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, Unit, load_bundle
from lnt.context.json_codec import decode_object
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_FS_HZ = 8000.0
_DURATION_S = 2.4
_WINDOWS = 12
_TONE_HZ = 125.0
_TONE_V = 0.5
_F03_INDEX = 2
_RECORD_SAMPLES = round(_FS_HZ * _DURATION_S)
_TRACK_IDS = (
    "f03_f_hz",
    "f03_a_v",
    "f03_df_hz",
    "f03_t_life_s",
    "f03_windows_observed",
    "f03_windows_missing",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f03 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _session(path: Path, measured: np.ndarray) -> Path:
    """Пишет сессию: измеренный канал задаёт тест, CH2 остаётся чистой опорой 50 Гц."""
    write_manifest(path)
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    np.save(path / "ch1.npy", measured.astype(np.float32))
    np.save(path / "ch2.npy", (6.0 * np.sin(2.0 * np.pi * 50.0 * times)).astype(np.float32))
    return path


def _tone_record() -> np.ndarray:
    """Сеть держит оценку f1, тон ровно на узле сетки: 125 Гц это k=25 при бине 5 Гц."""
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    return 6.0 * np.sin(2.0 * np.pi * 50.0 * times) + _TONE_V * np.sin(
        2.0 * np.pi * _TONE_HZ * times
    )


def _mains_record() -> np.ndarray:
    """Гармоника-чистый сигнал: вся энергия в бинах гармоник, IHG-бины пустые."""
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    return 6.0 * np.sin(2.0 * np.pi * 50.0 * times)


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    ch1 = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2 = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)
    return ch1, ch2


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def _summaries(family: FamilyResult) -> dict[str, float]:
    return {item.name: float(item.value) for item in family.comparison_summary}


def test_tone_record_publishes_track_matching_the_declared_grid(tmp_path: Path) -> None:
    session = _session(tmp_path / "syn-tone-125", _tone_record())
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f03 = loaded.bundle.families[_F03_INDEX]

    assert first.cache_hit is False
    assert f03.family_id == "f03_interharmonic_tracking"
    assert f03.status is Status.AVAILABLE
    assert f03.reason_codes == ()
    assert {reference.array_id for reference in f03.array_refs} == set(_TRACK_IDS)
    assert f03.signal_plane == "ch1_scope_input"
    assert f03.units == (Unit.HZ, Unit.V, Unit.S, Unit.COUNT)
    assert f03.window.kind == "fixed"
    assert f03.window.duration_s == pytest.approx(0.2)

    arrays = loaded.arrays
    assert arrays["f03_f_hz"].shape == arrays["f03_a_v"].shape
    count = int(arrays["f03_f_hz"].size)
    assert count >= 1
    # Сеансовый путь это float32: детерминированные квантовые шпоры тоже
    # ассоциируются в треки (см. evidence task-14), поэтому аналитическая истина
    # проверяется совпадением объявленного тона, а не единственным треком.
    best = int(np.argmin(np.abs(arrays["f03_f_hz"] - _TONE_HZ)))
    assert abs(float(arrays["f03_f_hz"][best]) - _TONE_HZ) <= 2.5
    expected_rms = _TONE_V / math.sqrt(2.0)
    assert abs(float(arrays["f03_a_v"][best]) - expected_rms) <= 0.01 * expected_rms
    assert int(arrays["f03_windows_observed"][best]) == _WINDOWS
    assert int(arrays["f03_windows_missing"][best]) == 0
    assert float(arrays["f03_df_hz"][best]) >= 0.0
    assert arrays["f03_t_life_s"][best] == pytest.approx(_DURATION_S)

    summaries = _summaries(f03)
    assert summaries["f03_track_count"] == float(count)
    assert summaries["f03_omitted_track_count"] == 0.0

    support = f03.support
    assert support.start_s == 0.0
    assert support.end_s == pytest.approx(_DURATION_S)
    assert support.duration_s == pytest.approx(support.end_s - support.start_s)
    assert support.stored_count == support.observation_count == count

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before


def test_harmonic_clean_record_publishes_the_declared_refusal_without_arrays(
    tmp_path: Path,
) -> None:
    """Без IHG-энергии треков нет: отказ объявленным кодом, без выдуманных треков."""
    session = _session(tmp_path / "syn-mains-only", _mains_record())
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f03 = loaded.bundle.families[_F03_INDEX]

    assert result.cache_hit is False
    assert f03.status is Status.UNAVAILABLE
    assert f03.reason_codes == ("peak_not_observed",)
    assert f03.array_refs == ()
    assert f03.comparison_summary == ()
    assert f03.support.observation_count == 0
    assert not any(name.startswith("f03_") for name in loaded.arrays)
