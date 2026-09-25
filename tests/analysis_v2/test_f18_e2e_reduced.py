"""F18 E2E-reduced: реальный seam, честный отказ и сохранность всех 18 семейств.

F18 объявляет 15 триад на пяти базовых частотах и требует exact FFT bins, поэтому
через seam отказ наступает на двух разных условиях. На 500 кГц — канонической
частоте эталонных записей — вся сетка вне решётки, и семья честно UNAVAILABLE с
пустыми доменами. На частотах решётки сетка измерима, но корень фазы от реального
CH2 всегда теряет фильтровый halo на обоих краях записи, поэтому источник null
негоден и F18 отказывается.

Обе причины обязаны оставаться локальными для F18. Длина измеренного подмножества
триад расходится с declared-доменом на частичной сетке, а негодный остаток фазы
не должен поднимать исключение. Любое из двух уносило весь прогон характеризации,
то есть все восемнадцать семейств, вместо одного. Тесты ниже — интеграционный
regression-пин: seam обязан завершиться и опубликовать полный каталог, а потеря
одной фазы не должна превращаться в пустой набор семейств.

Числовые выводы читаются из загруженного артефакта. Тесты не выводят калибровку,
соответствие стандарту, неопределённость GUM, физический механизм или причинность.
"""

from __future__ import annotations

import functools
import hashlib
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_bundle import F18_ID, decode_f18_result
from lnt.characterization.f18_contract import (
    DECLARED_CODES,
    METHOD,
    PHASE_REFERENCE_UNAVAILABLE,
    TRIAD_ABOVE_NYQUIST,
    TRIAD_OFF_GRID,
)
from lnt.characterization.f18_tables import locked_declarations
from lnt.characterization.f18_triads import build_triad_grid, grid_reason_codes
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.context.json_codec import decode_object
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.analysis_v2.types import AnalysisRunResult
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.f18_result import F18Declarations
    from lnt.characterization.f18_triads import F18TriadGrid
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F18_INDEX = 17
_DECLARED_TRIADS = 15
_PLACEHOLDER = "not_computed"
# Стандартный профиль эталонных записей проекта: 500 кГц, 2.4 s.
_STANDARD_FS_HZ = 500_000.0
_STANDARD_SAMPLES = 1_200_000
# 204.8 кГц: шаг 50 Hz делит все базы, Найквист 102.4 кГц выше всех компонент
# фикстуры, но сумма 50 + 50 = 100 кГц выше clamps 0.45 * fs = 92.16 кГц.
_CRASH_BAND_FS_HZ = 204_800.0
_CRASH_BAND_SAMPLES = 102_400
# 512 кГц: шаг 125 Hz, все 15 триад измеримы — единственная замеренная сетка,
# которую юнит-тесты покрывали, а seam — нет.
_EXACT_GRID_FS_HZ = 512_000.0
_EXACT_GRID_SAMPLES = 168_960
# Решётка exact_fft_bins = segment_samples * gcd(bases) = 4096 * 1000 Гц.
_EXACT_BIN_LATTICE_HZ = 4_096_000
# Связанные триады фикстуры: 3000+5000 и 10000+20000; плюс три суммы 50/60/70 кГц.
# Измерено через build_triad_grid: у 14 целых частот решётки (делителей 4096000
# от 8 кГц вверх) 0 < measurable < 15,
# то есть длина измеренного подмножества расходится с declared-доменом.
_CRASH_BAND_RATES_HZ = (
    16_000,
    16_384,
    20_480,
    25_600,
    32_000,
    32_768,
    40_960,
    51_200,
    64_000,
    81_920,
    102_400,
    128_000,
    163_840,
    204_800,
)


@functools.lru_cache(maxsize=1)
def _recipe() -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "f18 e2e reduced")
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


def _crash_band_rates() -> tuple[int, ...]:
    """Целые частоты решётки, где длина measurable расходится с declared."""
    return tuple(
        sorted(
            _EXACT_BIN_LATTICE_HZ // k
            for k in range(1, _EXACT_BIN_LATTICE_HZ // 8_000 + 1)
            if _EXACT_BIN_LATTICE_HZ % k == 0
            and 0 < _measured(_grid(_EXACT_BIN_LATTICE_HZ / k)) < _DECLARED_TRIADS
        )
    )


def _exact_bin_positions(sample_rate_hz: float) -> np.ndarray:
    """Аналитическая позиция объявленных баз на оси rFFT: base * segment / fs."""
    locked = _locked()
    return np.asarray(locked.base_frequencies_hz) * locked.segment_samples / sample_rate_hz


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


def _coupled_record(sample_rate_hz: float, sample_count: int) -> np.ndarray:
    """Сумма постоянно-фазовых синусоид: f_j = f_1 + f_2 у четырёх locked-триад.

    Шумового пола здесь нет намеренно: он опустил бы наблюдаемое b2 чуть ниже 1,
    а суррогат без шума насыщался бы единицей и выглядел «более связным», чем
    наблюдение. Кадровый множитель 2*pi*f*n0/fs в B сокращается, поэтому для такой
    записи b2 = 1 в точности, а biphase равен -phi.
    """
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    record = np.zeros(sample_count, dtype=np.float64)
    for low_hz, high_hz, phi in ((3_000.0, 5_000.0, 0.7), (10_000.0, 20_000.0, -0.4)):
        record += np.cos(2.0 * np.pi * low_hz * times)
        record += np.cos(2.0 * np.pi * high_hz * times)
        record += 0.5 * np.cos(2.0 * np.pi * (low_hz + high_hz) * times + phi)
    record += np.cos(2.0 * np.pi * 50_000.0 * times)
    record += 0.5 * np.cos(2.0 * np.pi * 60_000.0 * times + 1.1)
    record += 0.5 * np.cos(2.0 * np.pi * 70_000.0 * times - 1.6)
    return record


def _mains(sample_rate_hz: float, sample_count: int) -> np.ndarray:
    times = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    return np.sin(2.0 * np.pi * 50.0 * times + 0.2)


def _write_session(path: Path, sample_rate_hz: float, sample_count: int) -> Path:
    write_manifest(path)
    np.save(path / "ch1.npy", _coupled_record(sample_rate_hz, sample_count).astype(np.float32))
    np.save(path / "ch2.npy", _mains(sample_rate_hz, sample_count).astype(np.float32))
    return path


def _publish_twice(
    session: Path, sample_rate_hz: float
) -> tuple[AnalysisRunResult, AnalysisRunResult, LoadedCharacterization, dict[str, bytes]]:
    first = run_characterization(_recipe(), session, _load(session), sample_rate_hz)
    files = _artifact_bytes(first.artifact_dir)
    loaded = load_bundle(files)
    second = run_characterization(_recipe(), session, _load(session), sample_rate_hz)
    return first, second, loaded, files


def _assert_identity(f18: FamilyResult, loaded: LoadedCharacterization) -> None:
    declared = _family()
    assert f18.family_id == declared.id == F18_ID == "f18_bicoherence_triads"
    assert f18.method == declared.method == METHOD
    assert f18.method_version == declared.method_version == 1
    assert f18.signal_plane == "ch1_scope_input"
    # Каталог полон: 18 семейств, ни одного placeholder'а not_computed.
    assert len(loaded.bundle.families) == 18
    assert not [f.family_id for f in loaded.bundle.families if _PLACEHOLDER in f.reason_codes]
    assert set(f18.reason_codes) <= set(DECLARED_CODES)
    assert PHASE_ROOT_REASON_CODES.isdisjoint(f18.reason_codes)


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


def _assert_unavailable_and_empty(f18: FamilyResult, loaded: LoadedCharacterization) -> None:
    """UNAVAILABLE публикует ПУСТЫЕ домены, а не нули, и декодер их не выдумывает.

    Fill-in остаётся невозможен и на уровне движка: `validate_f18_result` внутри
    `build_f18_family` fail-closed отвергает заполненный домен у UNAVAILABLE, так
    что нули сюда не проходят даже в обход записи.
    """
    assert f18.status is Status.UNAVAILABLE
    assert f18.array_refs == ()
    assert f18.table_refs == ()
    assert f18.comparison_summary == ()
    assert not [name for name in loaded.arrays if name.startswith("f18_")]
    assert not [name for name in loaded.tables if name.startswith("f18")]
    assert f18.support.observation_count == 0
    with pytest.raises(CharacterizationError, match="no decodable domain"):
        decode_f18_result(f18, loaded.arrays, loaded.tables)


def test_standard_profile_record_refuses_f18_off_grid_with_empty_domains(tmp_path: Path) -> None:
    """500 кГц: exact_fft_bins не выполнен ни на одной базе — 15 триад не измеримы."""
    session = _write_session(tmp_path / "f18-off-grid", _STANDARD_FS_HZ, _STANDARD_SAMPLES)
    before = _raw_hashes(session)
    first, second, loaded, files = _publish_twice(session, _STANDARD_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]

    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f18, loaded)
    _assert_unavailable_and_empty(f18, loaded)
    assert f18.reason_codes == (TRIAD_OFF_GRID,)

    # Аналитика отказа: пять баз по правилу i <= j дают ровно n(n+1)/2 = 15 триад,
    # а 500000/4096 = 122.0703125 Hz ни одну базу на бин не кладёт.
    base_count = len(_locked().base_frequencies_hz)
    assert base_count * (base_count + 1) // 2 == _DECLARED_TRIADS
    grid = _grid(_STANDARD_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, 0)
    assert grid.off_grid_count == _DECLARED_TRIADS
    assert grid_reason_codes(grid) == {TRIAD_OFF_GRID}
    positions = _exact_bin_positions(_STANDARD_FS_HZ)
    assert positions.tolist() == pytest.approx([24.576, 40.96, 81.92, 163.84, 409.6], abs=1e-9)

    # F18-5: решётка segment * gcd(bases) = 2^15 * 5^3 не делится ни на одно целое
    # МГц 1..15, поэтому F18 не может измерить ни одну аппаратную запись.
    assert math.gcd(*(round(v) for v in _locked().base_frequencies_hz)) == 1_000
    assert _locked().segment_samples * 1_000 == _EXACT_BIN_LATTICE_HZ
    for megahertz in range(1, 16):
        assert _EXACT_BIN_LATTICE_HZ % (megahertz * 1_000_000) != 0


def test_crash_band_rate_keeps_the_seam_alive_and_reports_both_causes(tmp_path: Path) -> None:
    """204.8 кГц: regression-пин обеих правок — длина declared и обрезанный корень фазы."""
    session = _write_session(tmp_path / "f18-crash", _CRASH_BAND_FS_HZ, _CRASH_BAND_SAMPLES)
    before = _raw_hashes(session)

    # Корень первого дефекта: длина измеренного подмножества 14 расходится с
    # declared-доменом 15, поэтому пересечение масок падало, а scatter — нет.
    assert _crash_band_rates() == _CRASH_BAND_RATES_HZ
    grid = _grid(_CRASH_BAND_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, 14)
    assert grid.off_grid_count == 0
    assert grid.above_nyquist_count == 1
    assert grid_reason_codes(grid) == {TRIAD_ABOVE_NYQUIST}
    assert grid.effective_high_hz == pytest.approx(0.45 * _CRASH_BAND_FS_HZ)

    first, second, loaded, files = _publish_twice(session, _CRASH_BAND_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f18, loaded)
    _assert_unavailable_and_empty(f18, loaded)
    # Причина сетки не теряется отказом: PHASE_REFERENCE_UNAVAILABLE добавлен, а не
    # подменён, поэтому triad_above_nyquist остаётся в vocabulary семейства.
    assert f18.reason_codes == (PHASE_REFERENCE_UNAVAILABLE, TRIAD_ABOVE_NYQUIST)


def test_exact_grid_rate_reports_phase_loss_without_losing_the_seam(tmp_path: Path) -> None:
    """512 кГц: сетка полностью измерима, поэтому единственная причина — обрезанная фаза."""
    session = _write_session(tmp_path / "f18-grid", _EXACT_GRID_FS_HZ, _EXACT_GRID_SAMPLES)
    before = _raw_hashes(session)

    grid = _grid(_EXACT_GRID_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, _DECLARED_TRIADS)
    assert not grid_reason_codes(grid)
    assert _EXACT_BIN_LATTICE_HZ % int(_EXACT_GRID_FS_HZ) == 0

    first, second, loaded, files = _publish_twice(session, _EXACT_GRID_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_cache_and_source(first, second, files, session, before)
    _assert_identity(f18, loaded)
    _assert_unavailable_and_empty(f18, loaded)
    assert f18.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
