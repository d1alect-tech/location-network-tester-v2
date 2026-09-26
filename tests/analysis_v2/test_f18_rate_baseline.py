"""Базовые пины F18 на 1 и 8 МГц: сегодняшний отказ зафиксирован на неизменённом коде.

Сегмент F18 объявлен фиксированными 4096 отсчётами, поэтому шаг сетки плывёт с частотой
захвата и на любой целой МГц F18 не меряет ни одной из 15 триад. Волны 3 и 4 инвертируют
это поведение, поэтому здесь оно закреплено как есть: 1 МГц публикует UNAVAILABLE с пустыми
доменами, а 8 МГц не публикует ничего вовсе — движок поднимает ValueError по бюджету
суррогатного источника, и этот отказ уходит из характеристики неуловленным.
"""

from __future__ import annotations

import functools
import hashlib
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.analysis_v2.characterization_slices_bicoherence import _compute_f18
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.event_models import RootEvents, RootEventSettings
from lnt.characterization.f18_bundle import F18_ID, decode_f18_result
from lnt.characterization.f18_contract import DECLARED_CODES, METHOD, TRIAD_OFF_GRID
from lnt.characterization.f18_frames import SURROGATE_BYTES_PER_SAMPLE
from lnt.characterization.f18_tables import locked_declarations
from lnt.characterization.f18_triads import build_triad_grid, grid_reason_codes
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.context.json_codec import decode_object
from lnt.scope_io import NEVER_CANCELLED
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.event_models import RootTimelineItem
    from lnt.characterization.f18_result import F18Declarations
    from lnt.characterization.f18_triads import F18TriadGrid
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F18_INDEX = 17
_DECLARED_TRIADS = 15
# Стандартный профиль эталонных записей проекта — 2.4 s. На 1 МГц это 2 400 000 отсчётов,
# на частоте захвата Hantek 6022BE 8 МГц — 19 200 000.
_ONE_MHZ_HZ = 1_000_000.0
_ONE_MHZ_SAMPLES = 2_400_000
_HARDWARE_HZ = 8_000_000.0
_HARDWARE_SAMPLES = 19_200_000
# Порог длительности записи: max_work_bytes / SURROGATE_BYTES_PER_SAMPLE.
_RECORD_LENGTH_LIMIT = 8_388_608
# Оба гейта длительности поднимают ValueError, поэтому пин различает их только строкой.
_RECORD_LENGTH_MESSAGE = "F18 surrogate source exceeds the declared work budget"
# 1 МГц / 4096 = 244.140625 Гц на бин, поэтому пять баз дают ровно эти дробные позиции.
# Список 500 кГц из test_f18_e2e_reduced вдвое больше: bin = f * 4096 / fs.
_ONE_MHZ_BASE_BINS = (12.288, 20.48, 40.96, 81.92, 204.8)
# 8 МГц / 4096 = 1953.125 Гц на бин: те же пять баз, но ещё дальше от целых.
_HARDWARE_BASE_BINS = (1.536, 2.56, 5.12, 10.24, 25.6)
# Решётка exact_fft_bins = segment * gcd(bases) = 4096 * 1000 Гц.
_EXACT_BIN_LATTICE_HZ = 4_096_000
# Кадрово-согласованная трёхчастотная система: f_j = f_1 + f_2 присутствует в ch1 с
# постоянной фазой, поэтому bicoherence насыщается единицей. Шумового пола нет намеренно.
_COUPLED_TRIADS = ((3_000.0, 5_000.0, 0.7), (10_000.0, 20_000.0, -0.4))


@functools.lru_cache(maxsize=1)
def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f18 rate baseline")
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _family() -> CharacterizationFamily:
    return _recipe().families[_F18_INDEX]


def _locked() -> F18Declarations:
    return locked_declarations(_family())


def _grid(sample_rate_hz: float) -> F18TriadGrid:
    locked = _locked()
    return build_triad_grid(
        locked.base_frequencies_hz,
        segment_samples=locked.segment_samples,
        sample_rate_hz=sample_rate_hz,
        analysis_low_hz=_recipe().stft.analysis_low_hz,
        analysis_high_hz=locked.analysis_high_hz,
        nyquist_fraction_max=locked.nyquist_fraction_max,
        maximum_triads=locked.maximum_triads,
    )


def _measured(grid: F18TriadGrid) -> int:
    return int(np.count_nonzero(grid.measurable))


def _base_bins(sample_rate_hz: float) -> np.ndarray:
    locked = _locked()
    return np.asarray(locked.base_frequencies_hz) * locked.segment_samples / sample_rate_hz


def _coupled_record(sample_rate_hz: float, sample_count: int) -> np.ndarray:
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    record = np.zeros(sample_count, dtype=np.float64)
    for low_hz, high_hz, phi in _COUPLED_TRIADS:
        record += np.cos(2.0 * np.pi * low_hz * times)
        record += np.cos(2.0 * np.pi * high_hz * times)
        record += 0.5 * np.cos(2.0 * np.pi * (low_hz + high_hz) * times + phi)
    record += np.cos(2.0 * np.pi * 50_000.0 * times)
    record += 0.5 * np.cos(2.0 * np.pi * 60_000.0 * times + 1.1)
    record += 0.5 * np.cos(2.0 * np.pi * 70_000.0 * times - 1.6)
    return record


def _write_session(path: Path, sample_rate_hz: float, sample_count: int) -> Path:
    write_manifest(path)
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    np.save(path / "ch1.npy", _coupled_record(sample_rate_hz, sample_count).astype(np.float32))
    np.save(path / "ch2.npy", np.sin(2.0 * np.pi * 50.0 * times + 0.2).astype(np.float32))
    return path


def _load(session: Path) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False),
        np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False),
    )


def _raw_hashes(session: Path) -> dict[str, str]:
    return {
        name: hashlib.sha256((session / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "ch2.npy", "manifest.json")
    }


def _artifact_bytes(artifact_dir: Path) -> dict[str, bytes]:
    return {name: (artifact_dir / name).read_bytes() for name in OUTPUT_FILENAMES}


def _publish_twice(session: Path, sample_rate_hz: float) -> LoadedCharacterization:
    """Прогнать реальный seam дважды: кэш, артефакт и сырьё обязаны совпасть."""
    before = _raw_hashes(session)
    first = run_characterization(_recipe(), session, _load(session), sample_rate_hz)
    files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(files)
    second = run_characterization(_recipe(), session, _load(session), sample_rate_hz)
    assert first.cache_hit is False
    assert first.failures == ()
    assert second.cache_hit is True
    assert second.artifact_key == first.artifact_key
    assert second.artifact_dir == first.artifact_dir
    assert _artifact_bytes(second.artifact_dir) == files
    assert _raw_hashes(session) == before
    return loaded


def _assert_identity(f18: FamilyResult, loaded: LoadedCharacterization) -> None:
    declared = _family()
    assert f18.family_id == declared.id == F18_ID == "f18_bicoherence_triads"
    assert f18.method == declared.method == METHOD
    assert f18.method_version == declared.method_version == 1
    assert f18.signal_plane == "ch1_scope_input"
    # Каталог полон: 18 семейств, ни одного placeholder'а not_computed.
    assert len(loaded.bundle.families) == 18
    assert not [f.family_id for f in loaded.bundle.families if "not_computed" in f.reason_codes]
    assert set(f18.reason_codes) <= set(DECLARED_CODES)
    assert PHASE_ROOT_REASON_CODES.isdisjoint(f18.reason_codes)


# UNAVAILABLE публикует ПУСТЫЕ домены, а не нули, и декодер их не выдумывает. Fill-in
# остаётся невозможен и на уровне движка: validate_f18_result внутри build_f18_family
# fail-closed отвергает заполненный домен у UNAVAILABLE.
def _assert_unavailable_and_empty(f18: FamilyResult, loaded: LoadedCharacterization) -> None:
    assert f18.status is Status.UNAVAILABLE
    assert f18.array_refs == ()
    assert f18.table_refs == ()
    assert f18.comparison_summary == ()
    assert not [name for name in loaded.arrays if name.startswith("f18_")]
    assert not [name for name in loaded.tables if name.startswith("f18")]
    assert f18.support.observation_count == 0
    with pytest.raises(CharacterizationError, match="no decodable domain"):
        decode_f18_result(f18, loaded.arrays, loaded.tables)


def _phase_cycles(sample_rate_hz: float, sample_count: int) -> PhaseCycles:
    """Мерный корень фазы: 50 Гц на каждом цикле, без halo фильтра."""
    step = max(1, round(sample_rate_hz / 50.0))
    starts = np.arange(0, sample_count, step, dtype=np.float64)
    ends = np.append(starts[1:], float(sample_count))
    return PhaseCycles(
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        cycle_start_samples=starts,
        cycle_end_samples=ends,
        cycle_valid=np.ones(ends.size, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _phase_means() -> PhaseMeans:
    return PhaseMeans(
        means_v=np.zeros(64, dtype=np.float64),
        counts=np.full(64, 1_024, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


# Пустой измеренный инвентарь: F18 считает gaps, а не сами события, и гейт длительности
# записи срабатывает раньше любого чтения инвентаря.
def _inventory(sample_rate_hz: float, sample_count: int) -> RootEvents:
    def replay(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        return iter(())

    settings = RootEventSettings(
        recipe_sha256="test",
        detector="existing_event_inventory",
        noise_window_samples=2_048,
        noise_step_samples=1_024,
        minimum_noise_samples=1_024,
        threshold_sigma=5.0,
        max_gap_samples=4,
        minimum_event_samples=1,
        minimum_snr_db=10.0,
        minimum_snr_ratio=3.9810717055349722,
        dead_time_s=0.001,
        dead_time_samples=10,
        chunk_samples=4_096,
        fft_max_samples=1_048_576,
        clipping_low_v=None,
        clipping_high_v=None,
        clipping_reason_code="not_applicable",
        dead_time_handling="exclude_intervals",
        gap_handling="exclude_crossing_intervals",
    )
    return RootEvents(
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        events=(),
        gaps=(),
        exclusions=(),
        candidate_count=0,
        snr_rejected_count=0,
        accepted_count=0,
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=0,
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=replay,
    )


def test_one_megahertz_canonical_record_refuses_f18_off_grid_with_empty_domains(
    tmp_path: Path,
) -> None:
    """1 МГц: exact_fft_bins не выполнен ни на одной базе — 15 триад не измеримы."""
    session = _write_session(tmp_path / "f18-1mhz-off-grid", _ONE_MHZ_HZ, _ONE_MHZ_SAMPLES)
    loaded = _publish_twice(session, _ONE_MHZ_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_unavailable_and_empty(f18, loaded)
    assert f18.reason_codes == (TRIAD_OFF_GRID,)

    # Аналитика отказа: пять баз по правилу i <= j дают ровно n(n+1)/2 = 15 триад,
    # а 1 000 000 / 4096 = 244.140625 Гц ни одну базу на бин не кладёт.
    locked = _locked()
    assert locked.segment_samples == 4_096
    assert len(locked.base_frequencies_hz) * 6 // 2 == _DECLARED_TRIADS
    grid = _grid(_ONE_MHZ_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, 0)
    assert grid.off_grid_count == _DECLARED_TRIADS
    assert grid.above_nyquist_count == 0
    assert grid_reason_codes(grid) == {TRIAD_OFF_GRID}

    # F18-5: решётка segment * gcd(bases) = 2^15 * 5^3 Гц не делится ни на одно целое
    # МГц 1..15, поэтому F18 не меряет ни одну аппаратную запись.
    assert math.gcd(*(round(value) for value in locked.base_frequencies_hz)) == 1_000
    assert locked.segment_samples * 1_000 == _EXACT_BIN_LATTICE_HZ
    for megahertz in range(1, 16):
        assert _EXACT_BIN_LATTICE_HZ % (megahertz * 1_000_000) != 0

    # Позиции пяти баз на сетке из 4096 отсчётов: bin = f * 4096 / fs. Сравнение точное,
    # а не приближённое: аналитика и расчёт дают один и тот же double.
    positions = _base_bins(_ONE_MHZ_HZ)
    assert np.array_equal(positions, np.asarray(_ONE_MHZ_BASE_BINS))
    assert not np.array_equal(np.rint(positions), positions)

    # Домены пусты и не замаскированы, потому что не опубликованы вовсе: у UNAVAILABLE нет
    # ни одного f18-массива и ни одной f18-таблицы, поэтому masked absence нечего публиковать.
    # Все числа артефакта конечны, то есть NaN в опубликованные домены не проходит.
    floats = [array for array in loaded.arrays.values() if np.issubdtype(array.dtype, np.floating)]
    assert all(bool(np.all(np.isfinite(array))) for array in floats)


def test_hardware_rate_canonical_record_refuses_f18_on_the_record_length_budget() -> None:
    """8 МГц: 19 200 000 отсчётов не влезают в бюджет суррогатного источника."""
    limits = _recipe().resource_limits
    # Арифметика порога как истина, а не согласие движка с самим собой.
    assert limits.max_work_bytes // SURROGATE_BYTES_PER_SAMPLE == _RECORD_LENGTH_LIMIT
    assert round(2.4 * _HARDWARE_HZ) == _HARDWARE_SAMPLES
    assert _HARDWARE_SAMPLES > _RECORD_LENGTH_LIMIT
    assert _ONE_MHZ_SAMPLES < _RECORD_LENGTH_LIMIT
    # Сегментный гейт не может быть причиной: 4096 отсчётов намного ниже потолка, поэтому
    # отказ приходит именно от размера записи, а не от размера сегмента.
    assert _locked().segment_samples <= limits.hard_max_chunk_samples

    record = _coupled_record(_HARDWARE_HZ, _HARDWARE_SAMPLES).astype(np.float32)
    # Строка отказа зафиксирована дословно: она снята с живого прогона, а не выведена из
    # чтения кода, и уходит наружу необработанной, поэтому семейство не публикуется вовсе.
    with pytest.raises(ValueError, match=re.escape(_RECORD_LENGTH_MESSAGE)) as refusal:
        _compute_f18(
            record,
            _phase_cycles(_HARDWARE_HZ, _HARDWARE_SAMPLES),
            _phase_means(),
            _inventory(_HARDWARE_HZ, _HARDWARE_SAMPLES),
            _recipe(),
            NEVER_CANCELLED,
        )
    assert str(refusal.value) == _RECORD_LENGTH_MESSAGE

    # Отказ приходит раньше сетки и до всякого framing: без гейта длительности 8 МГц тоже
    # вне решётки, поэтому triad_off_grid на 8 МГц сегодня недостижим — гейт длительности
    # перекрывает его, а не дополняет, и измерить 8 МГц нельзя ни при каком сегменте.
    assert _measured(_grid(_HARDWARE_HZ)) == 0
    assert grid_reason_codes(_grid(_HARDWARE_HZ)) == {TRIAD_OFF_GRID}
    hardware_positions = _base_bins(_HARDWARE_HZ)
    assert np.array_equal(hardware_positions, np.asarray(_HARDWARE_BASE_BINS))
    assert not np.array_equal(np.rint(hardware_positions), hardware_positions)
