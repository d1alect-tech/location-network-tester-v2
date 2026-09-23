"""F04 E2E-reduced через реальный seam: AM-несущая даёт ADEV/АКФ, два тона — PARTIAL.

Истина аналитическая, не из движка: несущая 30 кГц при сети 50 Гц даёт
отношение 600; чистая сеть даёт почти постоянные длительности циклов, поэтому
АКФ конечна (нули при нулевой дисперсии по решению движка), а слип мал.
Два тона в полосе роняют F06 (``multiple_components``) — путь (a) снимается
кодом ``carrier_unavailable``, путь (b) публикуется.
"""

from __future__ import annotations

import hashlib
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
_FS_HZ = 500_000.0
_DURATION_S = 2.4
_CARRIER_HZ = 30_000.0
_RATE_HZ = 500.0
_DEPTH = 0.5
_NOISE_V = 1e-4
_SEED = 6022
_F04_INDEX = 3
_RECORD_SAMPLES = round(_FS_HZ * _DURATION_S)
_TAU_S = tuple(0.02 * factor for factor in (1, 2, 4, 8, 16, 32))
_LAGS = tuple(range(1, 33))
_ARRAY_IDS = (
    "f04_tau_s",
    "f04_adev_mains",
    "f04_adev_carrier",
    "f04_acf_lag_cycles",
    "f04_cycle_acf",
)
_TONE_LOW_HZ = 20_000.0
_TONE_HIGH_HZ = 32_000.0


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f04 e2e reduced")
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


def _am_record() -> np.ndarray:
    """AM: огибающая 1 + m*cos(2*pi*fm*t) на несущей 30 кГц плюс слабый белый шум."""
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    envelope = 1.0 + _DEPTH * np.cos(2.0 * np.pi * _RATE_HZ * times)
    noise = np.random.default_rng(_SEED).standard_normal(_RECORD_SAMPLES) * _NOISE_V
    return envelope * np.cos(2.0 * np.pi * _CARRIER_HZ * times) + noise


def _two_tone_record() -> np.ndarray:
    """Два тона в полосе: условие Бедросяна нарушено, F06 отказывает с declared code."""
    times = np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ
    return np.cos(2.0 * np.pi * _TONE_LOW_HZ * times) + np.cos(2.0 * np.pi * _TONE_HIGH_HZ * times)


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


def test_am_record_publishes_adev_and_acf_matching_the_declared_ratios(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path / "syn-am-seed6022", _am_record())
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f04 = loaded.bundle.families[_F04_INDEX]

    assert first.cache_hit is False
    assert f04.family_id == "f04_multicycle_periodicity"
    assert f04.status is Status.AVAILABLE
    assert f04.reason_codes == ()
    assert {reference.array_id for reference in f04.array_refs} == set(_ARRAY_IDS)
    assert f04.signal_plane == "ch1_scope_input"
    assert f04.units == (Unit.S, Unit.RATIO, Unit.COUNT)
    assert f04.window.kind == "record"
    assert f04.window.duration_s == pytest.approx(_DURATION_S)

    arrays = loaded.arrays
    assert arrays["f04_tau_s"].shape == (6,)
    assert list(arrays["f04_tau_s"]) == pytest.approx(list(_TAU_S))
    assert arrays["f04_adev_mains"].shape == (6,)
    assert arrays["f04_adev_carrier"].shape == (6,)
    assert list(arrays["f04_acf_lag_cycles"]) == list(_LAGS)
    assert arrays["f04_cycle_acf"].shape == (32,)
    for name in _ARRAY_IDS:
        assert bool(np.all(np.isfinite(arrays[name])))
    # Нормировка АКФ описательной статистикой: Коши-Шварц держит единицу.
    assert float(np.max(np.abs(arrays["f04_cycle_acf"]))) <= 1.0 + 1e-9

    summaries = _summaries(f04)
    assert abs(summaries["f04_carrier_to_mains_ratio"] - 600.0) / 600.0 <= 1e-3
    assert summaries["f04_phase_slip_cycles"] < 0.01

    support = f04.support
    assert support.duration_s == pytest.approx(support.end_s - support.start_s)
    assert support.stored_count == support.observation_count
    assert support.observation_count >= 100

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before


def test_two_tone_record_keeps_mains_path_while_carrier_is_refused(
    tmp_path: Path,
) -> None:
    """Путь (a) снят кодом, путь (b) опубликован: PARTIAL без массива несущей."""
    session = _session(tmp_path / "syn-two-tone", _two_tone_record())
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f04 = loaded.bundle.families[_F04_INDEX]

    assert result.cache_hit is False
    assert f04.status is Status.PARTIAL
    assert f04.reason_codes == ("carrier_unavailable",)
    assert "f04_adev_carrier" not in loaded.arrays
    assert "f04_adev_mains" in loaded.arrays
    assert {reference.array_id for reference in f04.array_refs} == set(_ARRAY_IDS) - {
        "f04_adev_carrier"
    }
    summaries = _summaries(f04)
    assert "f04_phase_slip_cycles" in summaries
    assert "f04_carrier_to_mains_ratio" not in summaries
