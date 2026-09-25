"""F17 E2E-reduced: двойной канал, отказ на сетке и аналитическое измерение.

F17 — единственное кроме F14 двухканальное семейство: seam требует оба канала и оба
набора фазовых средних. На 500 кГц declared alpha не попадают на сетку FFT
(SPEC_GAPS F17-1), поэтому семейство обязано отказать с пустыми доменами. Второй
случай сверяет две когерентности с выведенными из записи значениями, без утверждений
о калибровке, стандарте или причинности.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.acquire_validation import MAX_DUAL_RATE_MHZ, MEGA
from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.analysis_v2.characterization_slices_coherence import _compute_f17
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.characterization.f17_arrays import ARRAY_IDS, CELL_AVAILABLE_ID, SIGNIFICANT_ID
from lnt.characterization.f17_bundle import build_f17_family, decode_f17_result
from lnt.characterization.f17_contract import (
    CYCLIC_FREQUENCIES_HZ,
    CYCLIC_FREQUENCY_OFF_GRID,
    F17_ID,
    FALSE_DISCOVERY_RATE,
    METHOD,
    MINIMUM_FRAMES,
    PHASE_REFERENCE_UNAVAILABLE,
    SEGMENT_SAMPLES,
    SPEC_GAPS,
    SURROGATE_COUNT,
)
from lnt.characterization.phase import compute_phase_cycles, compute_phase_means
from lnt.characterization.records import Band
from lnt.context.json_codec import decode_object
from lnt.scope_io import NEVER_CANCELLED
from lnt.simulate import simulate_session
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.analysis_v2.types import AnalysisRunResult
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F17_INDEX = 16
_METHOD_VERSION = 1
_LINE_HZ = 50.0
_STANDARD_FS_HZ = 500_000.0
_STANDARD_DURATION_S = 2.4
# Наименьшая частота вне сетки F17 с непустой объявленной полосой: 0.45*12800 = 5760 Гц
# выше analysis_low_hz = 3000 Гц, а 102400 кратно 12800 (сдвиг 8 бинов на alpha = 50 Гц).
_EXACT_FS_HZ = 12_800.0
_EXACT_DURATION_S = 8.0
_SHORT_DURATION_S = 1.2
_CYCLES_PER_FRAME = SEGMENT_SAMPLES // round(_EXACT_FS_HZ / _LINE_HZ)
_COUPLED_ALPHA_HZ = 50.0
_COUPLED_CARRIER_HZ = 4_000.0
_COUPLED_STEP_RAD = 0.071
_ANTICHAINED_ALPHA_HZ = 150.0
_ANTICHAINED_CARRIER_HZ = 5_000.0
_ANTICHAINED_STEP_RAD = 0.5
_P_VALUE_FLOOR = 1.0 / (SURROGATE_COUNT + 1.0)
# Сдвиг когерентности между каналами на кадр STFT: два знака инкремента на mains-цикл,
# умноженные на число полных mains-циклов в одном кадре.
_FRAME_STEP_RAD = 2.0 * _ANTICHAINED_STEP_RAD * _CYCLES_PER_FRAME


def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f17 e2e reduced")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False),
        np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False),
    )


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        n: hashlib.sha256((session / n).read_bytes()).hexdigest()
        for n in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def _artifact_bytes(artifact_dir: Path) -> dict[str, bytes]:
    return {name: (artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}


def _write_session(path: Path, ch1: np.ndarray, ch2: np.ndarray) -> Path:
    write_manifest(path)
    np.save(path / "ch1.npy", ch1.astype(np.float32))
    np.save(path / "ch2.npy", ch2.astype(np.float32))
    return path


def _record(fs_hz: float, duration_s: float) -> tuple[np.ndarray, np.ndarray]:
    # Приращение фазы держится постоянным внутри mains-цикла, поэтому векторизация по
    # номеру цикла побитово совпадает с построчной генерацией. Связанная пара лежит в
    # обоих каналах с одинаковым приращением, поэтому |X1_upper| и |X2_lower|
    # постоянны по кадрам и когерентность равна 1; антифазовая пара несёт
    # противоположные приращения, поэтому её когерентность — свёртка Дирихле.
    samples = round(fs_hz * duration_s)
    cycle = round(fs_hz / _LINE_HZ)
    within = np.arange(samples, dtype=np.float64) / fs_hz
    index = np.arange(samples) // cycle
    step = (_COUPLED_STEP_RAD * index, _ANTICHAINED_STEP_RAD * index)
    half = (_COUPLED_ALPHA_HZ / 2.0, _ANTICHAINED_ALPHA_HZ / 2.0)
    carrier = (_COUPLED_CARRIER_HZ, _ANTICHAINED_CARRIER_HZ)
    lower = [2.0 * np.pi * (c - h) * within for c, h in zip(carrier, half, strict=True)]
    upper = [2.0 * np.pi * (c + h) * within for c, h in zip(carrier, half, strict=True)]
    pair = np.cos(lower[0] + step[0]) + 0.8 * np.cos(upper[0] + step[0])
    mains = 60.0 * np.sin(2.0 * np.pi * _LINE_HZ * within)
    return pair + np.cos(upper[1] + step[1]), mains + pair + np.cos(lower[1] - step[1])


def _publish_twice(
    recipe: CharacterizationRecipe,
    session: Path,
    channels: tuple[np.ndarray, np.ndarray],
    sample_rate_hz: float,
) -> tuple[AnalysisRunResult, AnalysisRunResult, LoadedCharacterization, dict[str, bytes]]:
    first = run_characterization(recipe, session, channels, sample_rate_hz)
    files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(files)
    second = run_characterization(recipe, session, channels, sample_rate_hz)
    return first, second, loaded, files


def _assert_cache_and_source(
    first: AnalysisRunResult,
    second: AnalysisRunResult,
    files: dict[str, bytes],
    session: Path,
    before: dict[str, str],
) -> None:
    assert first.cache_hit is False
    assert first.failures == ()
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == files
    assert _raw_hashes(session) == before


def _assert_identity(f17: FamilyResult, declared: CharacterizationFamily) -> None:
    assert f17.family_id == declared.id == F17_ID == "f17_cyclic_spectral_coherence"
    assert f17.method == declared.method == METHOD
    assert f17.method_version == declared.method_version == _METHOD_VERSION
    assert f17.signal_plane == "cross_channel_measured_planes"


def _assert_analytic_cells(f17: FamilyResult, loaded: LoadedCharacterization) -> None:
    # Ось и счётчики: 4 declared alpha на 884 центральные частоты с шагом 3.125 Гц;
    # hop = 2048 отсчётов, поэтому кадров (qualified - 4096) // 2048 + 1.
    arrays = loaded.arrays
    axis = arrays["f17_frequency_hz"]
    counters = {item.name: item.value for item in f17.comparison_summary}
    frames = int(counters["f17_frame_count"])
    coupled = int(np.flatnonzero(np.isclose(axis, _COUPLED_CARRIER_HZ))[0])
    antiphase = int(np.flatnonzero(np.isclose(axis, _ANTICHAINED_CARRIER_HZ))[0])

    assert len(loaded.bundle.families) == 18
    assert axis.size == 884
    assert int(counters["f17_tested_cell_count"]) == len(CYCLIC_FREQUENCIES_HZ) * axis.size
    assert bool(np.all(arrays[CELL_AVAILABLE_ID]))
    assert frames >= MINIMUM_FRAMES
    assert frames == (int(counters["f17_qualified_sample_count"]) - SEGMENT_SAMPLES) // 2048 + 1
    assert int(counters["f17_stored_cell_count"]) == int(counters["f17_significant_cell_count"])
    assert int(counters["f17_omitted_cell_count"]) == 0

    # Связанная пара alpha = 50 Гц кладёт боковые на 3 975 и 4 025 Гц, то есть в
    # bin +/- 8 от 4 000 Гц. Когерентность (mean(a*b))^2/(mean(a)*mean(b)) равна 1,
    # потому что оба модуля постоянны; отклонение даёт только float32 запись.
    alpha_c = CYCLIC_FREQUENCIES_HZ.index(_COUPLED_ALPHA_HZ)
    assert (_COUPLED_ALPHA_HZ / 2.0) / (_EXACT_FS_HZ / SEGMENT_SAMPLES) == 8
    assert arrays[CELL_AVAILABLE_ID][alpha_c, coupled] == 1
    assert float(arrays["f17_coherence"][alpha_c, coupled]) == pytest.approx(1.0, abs=1e-3)
    assert float(arrays["f17_raw_p_value"][alpha_c, coupled]) == _P_VALUE_FLOOR
    assert float(arrays["f17_bh_p_value"][alpha_c, coupled]) <= FALSE_DISCOVERY_RATE
    assert arrays[SIGNIFICANT_ID][alpha_c, coupled] == 1

    # Антифазовая пара alpha = 150 Гц кладёт боковые на 4 925 и 5 075 Гц, то есть в
    # bin +/- 24 от 5 000 Гц. Верхняя несущая CH1 и нижняя CH2 несут противоположные
    # приращения, поэтому cross-phase уезжает на 16 рад за кадр и когерентность
    # равна (sin(8*N)/(N*sin(8)))^2; потолок по MINIMUM_FRAMES — 4.43e-4.
    alpha_a = CYCLIC_FREQUENCIES_HZ.index(_ANTICHAINED_ALPHA_HZ)
    step = _FRAME_STEP_RAD
    predicted = (math.sin(step * frames / 2.0) / (frames * math.sin(step / 2.0))) ** 2
    ceiling = 1.0 / (MINIMUM_FRAMES * math.sin(step / 2.0)) ** 2

    assert (_ANTICHAINED_ALPHA_HZ / 2.0) / (_EXACT_FS_HZ / SEGMENT_SAMPLES) == 24
    assert arrays[CELL_AVAILABLE_ID][alpha_a, antiphase] == 1
    assert 0.0 < predicted < ceiling < 0.01
    # Наблюдение 1.59e-4 против связанной ячейки 1.0: разделение больше чем в 99 раз.
    assert float(arrays["f17_coherence"][alpha_a, antiphase]) < 0.01


def test_exact_grid_condition_is_the_locked_102400_divisibility() -> None:
    """Условие точной сетки — целочисленная делимость fs на 102400, а не на 204800."""
    divisor = min(CYCLIC_FREQUENCIES_HZ) * (SEGMENT_SAMPLES // 2)

    # divisor = min(alpha) * (segment_samples // 2) = 50 * 2048 при segment 4096.
    assert CYCLIC_FREQUENCIES_HZ == (50.0, 100.0, 150.0, 200.0)
    assert divisor == 102_400 == 2**12 * 5**2
    # Обе боковые несущие стоят на f +/- alpha/2, поэтому смещение в бинах равно
    # alpha / (2 * fs / 4096) и обязано быть целым и положительным.
    assert divisor % int(_STANDARD_FS_HZ) != 0
    assert int(_EXACT_FS_HZ) == divisor // 8
    assert divisor % int(_EXACT_FS_HZ) == 0
    # Захват принимает только целые 1..15 МГц, а 102400 меньше мегагерца, поэтому
    # ни одна допустимая частота захвата условию точной сетки не удовлетворяет.
    assert divisor < MEGA
    assert all(divisor % (index * MEGA) for index in range(1, MAX_DUAL_RATE_MHZ + 1))
    assert {gap[:5] for gap in SPEC_GAPS} == {"F17-1"}
    assert "divide 102400" in SPEC_GAPS[0]
    assert "cyclic_frequency_off_grid" in SPEC_GAPS[0]


def test_standard_profile_refuses_off_grid_alphas_and_publishes_empty_domains(
    tmp_path: Path,
) -> None:
    """500 кГц не делит 102400: F17 отказывает и не публикует ни одного массива."""
    session = simulate_session(
        out_dir=tmp_path / "syn-bad-500k",
        profile="bad",
        duration_s=_STANDARD_DURATION_S,
        sample_rate_hz=_STANDARD_FS_HZ,
        seed=6022,
    )
    before = _raw_hashes(session)
    recipe = _recipe()
    first, second, loaded, files = _publish_twice(recipe, session, _load(session), _STANDARD_FS_HZ)
    f17 = loaded.bundle.families[_F17_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f17, recipe.families[_F17_INDEX])
    assert f17.status is Status.UNAVAILABLE
    assert f17.reason_codes == (CYCLIC_FREQUENCY_OFF_GRID,)
    assert f17.array_refs == ()
    assert f17.table_refs == ()
    assert f17.comparison_summary == ()
    assert not any(name.startswith("f17_") for name in (*loaded.arrays, *loaded.tables))
    assert f17.support.observation_count == 0
    assert f17.window.duration_s == pytest.approx(_STANDARD_DURATION_S)
    # Шаг сетки 500000/4096 = 122.0703125 Гц; alpha/2 = 25 Гц даёт 0.2048 бина.
    step_hz = _STANDARD_FS_HZ / SEGMENT_SAMPLES
    assert (_COUPLED_ALPHA_HZ / 2.0) / step_hz == pytest.approx(0.2048)
    assert round((_COUPLED_ALPHA_HZ / 2.0) / step_hz) == 0


def test_exact_grid_rate_measures_analytic_coupled_and_antiphase_cells(tmp_path: Path) -> None:
    """12,8 кГц делит 102400: связанная ячейка единична, антифазовая близка к нулю."""
    ch1, ch2 = _record(_EXACT_FS_HZ, _EXACT_DURATION_S)
    session = _write_session(tmp_path / "syn-exact-grid", ch1, ch2)
    before = _raw_hashes(session)
    recipe = _recipe()
    first, second, loaded, files = _publish_twice(recipe, session, _load(session), _EXACT_FS_HZ)
    f17 = loaded.bundle.families[_F17_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f17, recipe.families[_F17_INDEX])
    assert f17.status is Status.AVAILABLE
    assert f17.reason_codes == ()
    assert tuple(reference.array_id for reference in f17.array_refs) == ARRAY_IDS
    _assert_analytic_cells(f17, loaded)

    restored = decode_f17_result(f17, loaded.arrays, loaded.tables)
    assert (restored.status, restored.reason_codes) == (f17.status, f17.reason_codes)
    np.testing.assert_array_equal(
        restored.cell_available, loaded.arrays[CELL_AVAILABLE_ID].astype(bool)
    )


def test_single_channel_session_refuses_f17_with_empty_domains(tmp_path: Path) -> None:
    """Сессия с одним каналом даёт отказ F17 с пустыми доменами, а не подставной массив."""
    recipe = _recipe()
    ch1, ch2 = _record(_EXACT_FS_HZ, _SHORT_DURATION_S)
    session = _write_session(tmp_path / "syn-single-channel", ch1, ch2)
    reference = np.load(session / "ch2.npy", allow_pickle=False)
    (session / "ch2.npy").unlink()
    limits = recipe.resource_limits
    phase = compute_phase_cycles(
        reference, sample_rate_hz=_EXACT_FS_HZ, settings=recipe.phase, resources=limits
    )
    means = compute_phase_means(
        ch1.astype(np.float32), phase, settings=recipe.phase, resources=limits
    )
    # Отсутствующий канал означает и отсутствие его фазовых средних, поэтому карта
    # каналов неполна при полной карте средних — этого достаточно для отказа.
    first = _compute_f17(
        {"ch1": ch1.astype(np.float32)},
        phase,
        {"ch1": means, "ch2": means},
        recipe,
        NEVER_CANCELLED,
    )

    assert first.status is Status.UNAVAILABLE
    assert first.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert (first.sample_count, first.qualified_cycle_count, first.stored_cell_count) == (0, 0, 0)
    for name in ("cyclic_frequencies_hz", "frequencies_hz", "coherence", "cell_available"):
        assert getattr(first, name).size == 0, name

    band = Band(low_hz=recipe.stft.analysis_low_hz, high_hz=recipe.stft.analysis_high_hz)
    envelope, arrays, tables = build_f17_family(
        first, recipe.families[_F17_INDEX], band, record_duration_s=_SHORT_DURATION_S
    )
    assert (arrays, tables) == ({}, {})
    assert (envelope.array_refs, envelope.table_refs, envelope.comparison_summary) == ((), (), ())
    assert envelope.support.observation_count == 0
