"""F18 E2E-reduced: реальный seam, измерение по qualified span и живой каталог.

F18 требует exact FFT bins, поэтому на 500 кГц вся сетка вне решётки и семья UNAVAILABLE
с пустыми доменами. На частотах решётки сетка измерима, а корень фазы от CH2 теряет
фильтровый halo, поэтому F18 меряет самый длинный phase-qualified span: sample_count
публикует всю запись, а qualified_sample_count — измеренный span.
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
    NO_SIGNIFICANT_TRIAD,
    TRIAD_ABOVE_NYQUIST,
    TRIAD_OFF_GRID,
    segment_samples_for,
)
from lnt.characterization.f18_tables import locked_declarations
from lnt.characterization.f18_triads import build_triad_grid, grid_reason_codes
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.context.json_codec import decode_object
from tests.test_ui_sessions import write_manifest

if TYPE_CHECKING:
    from lnt.analysis_store.characterization_family import CharacterizationFamily
    from lnt.characterization.bundle_codec import LoadedCharacterization
    from lnt.characterization.f18_result import F18Declarations
    from lnt.characterization.f18_triads import F18TriadGrid
    from lnt.characterization.models import FamilyResult

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_F18_INDEX = 17
_DECLARED_TRIADS = 15
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
# Суммы f_1 + f_2 фикстуры: 8000 = 3+5, 30000 = 10+20, 60000 = 10+50, 70000 = 20+50 кГц.
# Связанные триады записаны как индекс в порядке declared_triads -> phi, где phi —
# постоянная фаза третьей компоненты, поэтому b2 = 1, а biphase = -phi.
_COUPLED_TRIADS = ((3_000.0, 5_000.0, 0.7), (10_000.0, 20_000.0, -0.4))
_COUPLED_PHI = {1: 0.7, 10: -0.4, 11: 1.1, 13: -1.6}
# Триады, суммы которых (23, 15, 25, 55 кГц) нет вовсе в ch1: bicoherence честно
# близка к нулю, тогда как у связанных триад она насыщается единицей.
_ABSENT_SUM_INDICES = (3, 6, 7, 8)
# Кадрово-согласованная трёхчастотная система даёт b2 = 1 в точности, поэтому у
# связанных триад допуск 1e-4, а у свободных 1e-3 отделяет их на три порядка.
_COUPLED_TOLERANCE = 1e-4
_FREE_TOLERANCE = 1e-3
# Измерено через build_triad_grid: у 14 целых частот решётки (делителей 4096000
# от 8 кГц вверх) 0 < measurable < 15, то есть длина измеренного подмножества триад
# расходится с declared-доменом, и расхождение публикуется как masked absence.
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
        segment_samples=segment_samples_for(sample_rate_hz),
        sample_rate_hz=sample_rate_hz,
        analysis_low_hz=_recipe().stft.analysis_low_hz,
        analysis_high_hz=locked.analysis_high_hz,
        nyquist_fraction_max=locked.nyquist_fraction_max,
        maximum_triads=locked.maximum_triads,
    )


def _measured(grid: F18TriadGrid) -> int:
    return int(np.count_nonzero(grid.measurable))


# Целые частоты решётки, где длина measurable расходится с declared.
def _crash_band_rates() -> tuple[int, ...]:
    return tuple(
        sorted(
            _EXACT_BIN_LATTICE_HZ // k
            for k in range(1, _EXACT_BIN_LATTICE_HZ // 8_000 + 1)
            if _EXACT_BIN_LATTICE_HZ % k == 0
            and 0 < _measured(_grid(_EXACT_BIN_LATTICE_HZ / k)) < _DECLARED_TRIADS
        )
    )


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


def _domain(loaded: LoadedCharacterization, name: str) -> np.ndarray:
    return np.asarray(loaded.arrays[f"f18_{name}"])


# Шумового пола здесь нет намеренно: он опустил бы наблюдаемое b2 чуть ниже 1, а суррогат
# без шума насыщался бы единицей и выглядел «более связным», чем наблюдение. Кадровый
# множитель 2*pi*f*n0/fs в B сокращается, поэтому b2 = 1 в точности, biphase = -phi.
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
# fail-closed отвергает заполненный домен у UNAVAILABLE, так что нули сюда не проходят
# даже в обход записи.
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


# Семья меряет: полный declared-домен и все измеримые триады доступны.
def _assert_measured(f18: FamilyResult, loaded: LoadedCharacterization, record: int) -> None:
    assert f18.status is not Status.UNAVAILABLE
    assert f18.support.sample_count == record
    assert 0 < f18.n <= record
    assert f18.support.observation_count == f18.n
    assert f18.support.missing_count == record - f18.n
    # Домены не урезаны: длина измеренного подмножества расходится с declared, поэтому
    # публикуется declared-домен с masked absence, а не пересечение масок.
    assert {reference.shape for reference in f18.array_refs} == {(_DECLARED_TRIADS,)}
    available = _domain(loaded, "triad_available").astype(bool)
    measurable = {i.name: i.value for i in f18.comparison_summary}["f18_measurable_triad_count"]
    assert int(np.count_nonzero(available)) == measurable
    # Persisted masked absence — ровный ноль под validity mask, а не NaN: NaN не
    # переживает finite-only кодек, и движок публикует NaN в engine-форме.
    assert bool(np.all(_domain(loaded, "bicoherence_squared")[~available] == 0.0))
    assert bool(np.all(_domain(loaded, "dual_null_p_value")[~available] == 0.0))


def test_standard_profile_record_refuses_f18_off_grid_with_empty_domains(tmp_path: Path) -> None:
    """500 кГц: exact_fft_bins не выполнен ни на одной базе — 15 триад не измеримы."""
    session = _write_session(tmp_path / "f18-off-grid", _STANDARD_FS_HZ, _STANDARD_SAMPLES)
    loaded = _publish_twice(session, _STANDARD_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_unavailable_and_empty(f18, loaded)
    assert f18.reason_codes == (TRIAD_OFF_GRID,)

    # Аналитика отказа: пять баз по правилу i <= j дают ровно n(n+1)/2 = 15 триад,
    # а 500000/4096 = 122.0703125 Hz ни одну базу на бин не кладёт.
    locked = _locked()
    assert len(locked.base_frequencies_hz) * 6 // 2 == _DECLARED_TRIADS
    grid = _grid(_STANDARD_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, 0)
    assert grid.off_grid_count == _DECLARED_TRIADS
    assert grid_reason_codes(grid) == {TRIAD_OFF_GRID}
    positions = (
        np.asarray(locked.base_frequencies_hz)
        * segment_samples_for(_STANDARD_FS_HZ)
        / _STANDARD_FS_HZ
    )
    assert positions.tolist() == pytest.approx([24.576, 40.96, 81.92, 163.84, 409.6], abs=1e-9)

    # F18-5: решётка segment * gcd(bases) = 2^15 * 5^3 не делится ни на одно целое
    # МГц 1..15, поэтому F18 не может измерить ни одну аппаратную запись.
    assert math.gcd(*(round(v) for v in locked.base_frequencies_hz)) == 1_000
    assert segment_samples_for(_STANDARD_FS_HZ) * 1_000 == _STANDARD_FS_HZ
    for megahertz in range(1, 16):
        assert _EXACT_BIN_LATTICE_HZ % (megahertz * 1_000_000) != 0


def test_crash_band_rate_measures_the_measurable_subset_over_the_qualified_span(
    tmp_path: Path,
) -> None:
    """204.8 кГц: 14 триад из 15 измерены, 100 кГц отрезана clamps, seam жив."""
    session = _write_session(tmp_path / "f18-crash", _CRASH_BAND_FS_HZ, _CRASH_BAND_SAMPLES)
    loaded = _publish_twice(session, _CRASH_BAND_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_measured(f18, loaded, _CRASH_BAND_SAMPLES)

    # Причина сетки не теряется отказом: triad_above_nyquist остаётся в vocabulary
    # семейства, а phase_reference_unavailable больше не появляется вовсе.
    assert f18.reason_codes == (TRIAD_ABOVE_NYQUIST,)
    # Корень прежнего дефекта: длина измеренного подмножества 14 расходится с
    # declared-доменом 15, поэтому пересечение масок падало, а scatter — нет.
    assert _crash_band_rates() == _CRASH_BAND_RATES_HZ
    grid = _grid(_CRASH_BAND_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, 14)
    assert grid.off_grid_count == 0
    assert grid.above_nyquist_count == 1
    assert grid_reason_codes(grid) == {TRIAD_ABOVE_NYQUIST}
    assert grid.effective_high_hz == pytest.approx(0.45 * _CRASH_BAND_FS_HZ)
    # Недоступна ровно отрезанная триада 50 + 50 = 100 кГц, а не случайный поднабор.
    assert _domain(loaded, "triad_available").astype(bool).tolist() == [True] * 14 + [False]
    assert _domain(loaded, "triad_sum_hz").tolist()[14] == 100_000.0
    # Аналитика связанных триад: b2 насыщена единицей, поэтому BH даёт значимость и
    # biphase публикуется. Фикстура без шумового пола — b2 = 1 в точности.
    coupled = list(_COUPLED_PHI)
    biphase = _domain(loaded, "biphase_rad")
    significant = _domain(loaded, "significant").astype(bool)
    assert _domain(loaded, "bicoherence_squared")[coupled] == pytest.approx(1.0, abs=1e-9)
    # Biphase публикуется ровно для BH-значимых триад, иначе masked absence, поэтому
    # -phi проверяется там, где BH-решение состоялось: 10+50 кГц через dual null не прошла.
    assert np.array_equal(_domain(loaded, "biphase_valid").astype(bool), significant)
    accepted = {index: phi for index, phi in _COUPLED_PHI.items() if significant[index]}
    assert list(accepted) == [1, 10, 13]
    for index, phi in accepted.items():
        assert biphase[index] == pytest.approx(-phi, abs=5e-3)


def test_exact_grid_rate_measures_every_declared_triad_at_the_coupled_truth(
    tmp_path: Path,
) -> None:
    """512 кГц: все 15 триад измеримы, связанные насыщают, свободные близки к нулю."""
    session = _write_session(tmp_path / "f18-grid", _EXACT_GRID_FS_HZ, _EXACT_GRID_SAMPLES)
    loaded = _publish_twice(session, _EXACT_GRID_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_measured(f18, loaded, _EXACT_GRID_SAMPLES)

    assert f18.reason_codes == (NO_SIGNIFICANT_TRIAD,)
    grid = _grid(_EXACT_GRID_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, _DECLARED_TRIADS)
    assert not grid_reason_codes(grid)
    assert _EXACT_BIN_LATTICE_HZ % int(_EXACT_GRID_FS_HZ) == 0
    # Аналитика фикстуры: у связанных триад f_j = f_1 + f_2 присутствует в ch1 с
    # постоянной фазой, поэтому bicoherence насыщает единицу, а у триад с
    # отсутствующей суммой её нет, и bicoherence честно близка к нулю.
    bicoherence = _domain(loaded, "bicoherence_squared")
    absent = list(_ABSENT_SUM_INDICES)
    assert bicoherence[list(_COUPLED_PHI)] == pytest.approx(1.0, abs=_COUPLED_TOLERANCE)
    assert bool(np.all(bicoherence[absent] < _FREE_TOLERANCE))
    assert _domain(loaded, "triad_sum_hz")[absent].tolist() == [23e3, 15e3, 25e3, 55e3]
    # Все тона фикстуры кратны 50 Гц, то есть кадрово-согласованны с корнем фазы,
    # поэтому суррогаты насыщаются так же, как наблюдение: dual null не имеет
    # разрешения при насыщении, и триада насыщения честно названа незначимой (F18-4).
    # Biphase поэтому структурно отсутствует, а не выдумана нулём.
    significant = _domain(loaded, "significant").astype(bool)
    assert not bool(np.any(significant))
    assert not bool(np.any(_domain(loaded, "biphase_valid").astype(bool)))
    assert bool(np.all(_domain(loaded, "biphase_rad") == 0.0))
    assert bool(np.all(_domain(loaded, "dual_null_p_value") >= 0.01))
