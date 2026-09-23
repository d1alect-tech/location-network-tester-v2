"""F07 E2E-reduced через реальный seam: гребёнка T=100 даёт df, сеть даёт отказ.

Истина аналитическая, не из движка: импульсная гребёнка с периодом T=100
отсчётов обязана дать кепстральный пик на q*=T, то есть шаг df = fs/T = 80 Гц
и q_s = T/fs = 0.0125 с (спека F07:352-354, 377-379). Сеть в измеренном канале
нужна только чтобы F01 оценил f1 (F07-3): без f1 гребёнку сети не отличить.
Чистая гармоническая гребёнка сети — это гребёнка сети, а не новая модуляция,
поэтому объявлен код ``harmonic_comb_only`` (спека F07:367-368, 381-382).

Замеренная граница: при уровне сети 3e-3 В пик модуляции ещё доминирует, при
8e-3 В он уже сдвигается между окнами Hann и Blackman (``window_dependent``).
Это не подгонка, а измеренный запас узкой полосы, в которой гребёнка сети не
забирает доминанту кепстра.
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
_FS_HZ = 8000.0
_DURATION_S = 2.4
_RECORD_SAMPLES = round(_FS_HZ * _DURATION_S)
_F07_INDEX = 6
_TRAIN_PERIOD = 100
_TRAIN_AMPLITUDE = 3.0
_WEAK_MAINS_V = 3e-3
_STRONG_MAINS_V = 6.0
_CARRIER_HZ = 50.0
_SCALAR_IDS = (
    "f07_df_hz",
    "f07_sym_db",
    "f07_q_s",
    "f07_quefrency_amplitude",
    "f07_carrier_bin",
)


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f07 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _times() -> np.ndarray:
    return np.arange(_RECORD_SAMPLES, dtype=np.float64) / _FS_HZ


def _session(path: Path, measured: np.ndarray) -> Path:
    """Пишет сессию: измеренный канал задаёт тест, CH2 остаётся чистой опорой 50 Гц."""
    write_manifest(path)
    times = _times()
    np.save(path / "ch1.npy", measured.astype(np.float32))
    np.save(
        path / "ch2.npy",
        (_STRONG_MAINS_V * np.sin(2.0 * np.pi * _CARRIER_HZ * times)).astype(np.float32),
    )
    return path


def _comb_record(mains_v: float) -> np.ndarray:
    """Импульсная гребёнка T=100 поверх сети объявленного уровня."""
    signal = mains_v * np.sin(2.0 * np.pi * _CARRIER_HZ * _times())
    signal[::_TRAIN_PERIOD] += _TRAIN_AMPLITUDE
    return signal


def _mains_comb_record() -> np.ndarray:
    """Чистая гармоническая гребёнка сети 50..500 Гц: модуляции здесь нет."""
    times = _times()
    return np.sum(
        [np.sin(2.0 * np.pi * order * _CARRIER_HZ * times) for order in range(1, 11)],
        axis=0,
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


def _summaries(family: FamilyResult) -> dict[str, float]:
    return {item.name: float(item.value) for item in family.comparison_summary}


def test_comb_record_publishes_quefrency_matching_the_declared_spacing(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path / "syn-comb-100", _comb_record(_WEAK_MAINS_V))
    before = _raw_hashes(session)
    recipe = _recipe()
    ch1, ch2 = _load(session)

    first = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (first.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f07 = loaded.bundle.families[_F07_INDEX]

    assert first.cache_hit is False
    assert f07.family_id == "f07_comb_sideband_cepstrum"
    assert f07.status is Status.AVAILABLE
    assert f07.reason_codes == ()
    # Семейство скалярное: массивов нет, величины едут сводками сравнения.
    assert f07.array_refs == ()
    assert f07.signal_plane == "ch1_scope_input"
    assert f07.units == (Unit.HZ, Unit.RATIO, Unit.S, Unit.COUNT)
    assert f07.window.kind == "fixed"
    assert f07.window.duration_s == pytest.approx(16384 / _FS_HZ)
    assert not any(name.startswith("f07_") for name in loaded.arrays)

    summaries = _summaries(f07)
    expected_q_s = _TRAIN_PERIOD / _FS_HZ
    expected_df = _FS_HZ / _TRAIN_PERIOD
    assert set(summaries) == set(_SCALAR_IDS)
    assert summaries["f07_q_s"] == pytest.approx(expected_q_s, rel=1e-9)
    assert summaries["f07_df_hz"] == pytest.approx(expected_df, rel=1e-9)
    # df = 1 / q_s: две публикации обязаны быть согласованы между собой.
    assert summaries["f07_df_hz"] == pytest.approx(1.0 / summaries["f07_q_s"], rel=1e-9)
    assert summaries["f07_quefrency_amplitude"] > 0.0
    assert summaries["f07_carrier_bin"] >= 1.0

    second = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert _raw_hashes(session) == before


def test_mains_comb_record_is_refused_as_the_mains_comb_itself(tmp_path: Path) -> None:
    """Сеть сама образует гребёнку: объявленный отказ, а не выдуманная модуляция."""
    session = _session(tmp_path / "syn-mains-comb", _mains_comb_record())
    recipe = _recipe()
    ch1, ch2 = _load(session)

    result = run_characterization(recipe, session, (ch1, ch2), _FS_HZ)
    files = {name: (result.artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}
    loaded = load_bundle(files)
    f07 = loaded.bundle.families[_F07_INDEX]

    assert result.cache_hit is False
    assert f07.status is Status.UNAVAILABLE
    assert f07.reason_codes == ("harmonic_comb_only",)
    assert f07.comparison_summary == ()
    assert f07.array_refs == ()
    assert f07.support.observation_count == 0
    assert not any(name.startswith("f07_") for name in loaded.arrays)
