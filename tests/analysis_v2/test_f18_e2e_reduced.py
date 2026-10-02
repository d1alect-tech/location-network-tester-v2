"""F18 E2E-reduced: реальный seam, измерение по qualified span и живой каталог.

Сегмент объявлен длительностью 1 мс, поэтому segment_samples = round(0.001 * fs)
выводит шаг сетки из частоты: на 500 кГц это 500 отсчётов и ровно 1000 Hz на бин —
НОК пяти объявленных баз, так что стандартный профиль записи измеряет все 15 триад.
Корень фазы от CH2 теряет фильтровый halo, поэтому F18 меряет самый длинный
phase-qualified span: sample_count публикует всю запись, а qualified_sample_count —
измеренный span. Ожидания bicoherence выведены из фикстуры собственной реализацией
framing-математики (_derived_bicoherence): измерение идёт по phase-removed остатку,
и лестница 64-бинных фазовых средних возмущает триадные бины на сетке 1 мс.
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
from lnt.characterization.f18_triads import build_triad_grid, declared_triads, grid_reason_codes
from lnt.characterization.phase import (
    PHASE_ROOT_REASON_CODES,
    compute_phase_cycles,
    compute_phase_means,
)
from lnt.characterization.phase_model import phase_bins_impl
from lnt.characterization.phase_stats import phase_residual_impl
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
# Стандартный профиль эталонных записей проекта: 500 кГц, 2.4 s канонической записи.
# Частота ниже объявленного пути анализа 1 МГц, фактор приведения равен 1, а сегмент
# round(0.001 * 500000) = 500 даёт шаг ровно 1000 Hz — НОК пяти объявленных баз.
_STANDARD_FS_HZ = 500_000.0
_STANDARD_SAMPLES = 1_200_000
# 200 кГц: сегмент 200 отсчётов, разрешение 1000 Гц, базы на целых позициях 3/5/10/20/50,
# но сумма 50 + 50 = 100 кГц выше ограничения Найквиста 0.45 * fs = 90 кГц — отрезана
# ровно одна триада, и длина измеренного подмножества расходится с declared-доменом.
_CRASH_BAND_FS_HZ = 200_000.0
_CRASH_BAND_SAMPLES = 102_400
# 512 кГц: сегмент 512 отсчётов, решётка 512 * 1000 = 512000 делится на частоту без
# остатка — все 15 триад измеримы на решётке, не совпадающей с целыми мегагерцами.
_EXACT_GRID_FS_HZ = 512_000.0
_EXACT_GRID_SAMPLES = 168_960
# 8 кГц: clamp 0.45 * 8000 = 3600 Гц ниже минимальной суммы триад 6000 Гц, поэтому все
# 15 триад triad_above_nyquist и домены пусты. 0.33 s = 16.5 цикла 50 Гц хватает корню
# фазы и 64-бинным средним (минимум 20 отсчётов на бин).
_EMPTY_DOMAIN_FS_HZ = 8_000.0
_EMPTY_DOMAIN_SAMPLES = 2_640
# Суммы f_1 + f_2 фикстуры: 8000 = 3+5, 30000 = 10+20, 60000 = 10+50, 70000 = 20+50 кГц.
# Связанные триады записаны как индекс в порядке declared_triads -> phi, где phi —
# постоянная фаза третьей компоненты: до вычитания лестницы b2 = 1, biphase = -phi.
_COUPLED_TRIADS = ((3_000.0, 5_000.0, 0.7), (10_000.0, 20_000.0, -0.4))
_COUPLED_PHI = {1: 0.7, 10: -0.4, 11: 1.1, 13: -1.6}
# Триады, суммы которых (23, 15, 25, 55 кГц) нет вовсе в ch1: их bicoherence обязана
# оставаться на порядки ниже связанной, но не обязана быть нулём — см. _derived_bicoherence.
_ABSENT_SUM_INDICES = (3, 6, 7, 8)
# Допуски СГЛАСИЯ движка с выведенной из фикстуры аналитикой: связанные триады
# сверяются с эталоном с допуском 1e-4, свободные — 1e-3 (фактическое совпадение
# эталона с публикацией движка — не хуже 1e-14, бары не расширены и не смягчены).
_COUPLED_TOLERANCE = 1e-4
_FREE_TOLERANCE = 1e-3
# Аналитика ограничения Найквиста на сетке 1 мс: суммы триад лежат от 6000 до 100000 Гц,
# поэтому частичный замер (0 < measurable < 15) требует 6000 <= 0.45 * fs < 100000.
# Нижняя граница 14 кГц (0.45 * 14000 = 6300 >= 6000), верхняя 222 кГц
# (0.45 * 222000 = 99900 < 100000 <= 0.45 * 223000) — 209 целых килогерц.
_CRASH_BAND_RATES_HZ = tuple(range(14_000, 223_000, 1_000))


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


def _exact_bin_lattice_hz(sample_rate_hz: float) -> int:
    """Решётка exact_fft_bins на сетке 1 мс: segment * gcd(bases) Гц.

    gcd пяти объявленных баз равен 1000 Гц, поэтому решётка выводится из сегмента:
    частота лежит на решётке тогда и только тогда, когда решётка делится на неё
    нацело. У 500 кГц, 512 кГц и каждого целого МГц решётка равна самой частоте.
    """
    return segment_samples_for(sample_rate_hz) * 1_000


# Целые килогерцы, где длина measurable расходится с declared. Сегмент целого
# килогерца равен m, шаг сетки ровно 1000 Гц, поэтому все базы всегда на целых
# позициях, и частичность решается только ограничением Найквиста. Частичный замер
# требует effective_high < 100000 < 1 МГц, так что перебор до 1 МГц покрывает
# семейство целиком; выше движок приводит запись к 1 МГц целым фактором.
def _crash_band_rates() -> tuple[int, ...]:
    return tuple(
        rate
        for rate in range(8_000, 1_000_000 + 1, 1_000)
        if 0 < _measured(_grid(float(rate))) < _DECLARED_TRIADS
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
# множитель 2*pi*f*n0/fs в B сокращается, поэтому до вычитания лестницы средних
# b2 = 1 в точности, biphase = -phi.
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


def _derived_bicoherence(session: Path, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Вывести аналитический b2 и biphase фикстуры собственной framing-математикой.

    Эталон не зовёт измерительный путь F18: корень фазы и 64-бинные средние — общие
    корни всех семейств, а framing (периодическое hann-окно, hop = сегмент / 2,
    покадровое вычитание среднего) и нормированный биспектр считаются прямо в numpy.
    Измерение идёт по phase-removed остатку. Тоны фикстуры кратны 50 Гц, поэтому
    бинные средние отличны от нуля: 64-точечная лестница видит гармоническую k как
    k mod 64 и сопряжение -k mod 64 (последовательность средних вещественна), и
    вычитание заносит в остаток зеркальные изображения на гармониках
    h = +-(k mod 64) + 64m. Замкнутые формы: тон сохраняет амплитуду
    A * (1 - D(k/64)^2), изображение получает A * D(k/64) * D(h/64), где
    D(x) = sin(pi*x) / (pi*x) — ядро Дирихле усреднения по бину. Для фикстуры это
    изображения 200, 1400, 1800, 4600, 7800 Гц с амплитудами 0.066, 0.143, 0.111,
    0.043, 0.026 (сверено с rfft остатка). На сетке 1 мс (шаг 1000 Гц) они ложатся
    на дробные бины 0.2..7.8 в главном лепестке hann: связанные тоны остаются
    кадрово-когерентными в биспектре (m1 + m2 = m3, поворот фазы кадра
    2*pi*(m1 + m2 - m3)*s/segment сокращается), а изображения вращаются от кадра
    к кадру и раздувают знаменатель энергий. Отсюда b2 связанных триад честно
    ниже единицы, свободных — порядка 1e-3..3e-2, и оба ожидания обязаны
    выводиться, а не приравниваться к идеализированным 1 и 0.
    """
    recipe = _recipe()
    resources = recipe.resource_limits
    record = np.load(session / "ch1.npy", mmap_mode="r", allow_pickle=False)
    ch2 = np.load(session / "ch2.npy", mmap_mode="r", allow_pickle=False)
    phase = compute_phase_cycles(
        ch2, sample_rate_hz=sample_rate_hz, settings=recipe.phase, resources=resources
    )
    means = compute_phase_means(record, phase, settings=recipe.phase, resources=resources)
    segment = segment_samples_for(sample_rate_hz)
    hop = round(segment * (1.0 - _locked().overlap_fraction))
    # Спан выводится из корня фазы: валиден отсчёт внутри валидного цикла и валидного
    # бина средних, циклы замощают покрытие без дыр, поэтому спан — один непрерывный
    # прогон, как и выбирает qualified-путь движка.
    indices, valid = phase_bins_impl(phase, 0, int(phase.sample_count), recipe.phase.phase_bins)
    valid &= np.isfinite(np.asarray(record, dtype=np.float64)) & means.valid_bins[indices]
    positions = np.flatnonzero(valid)
    first, last = int(positions[0]), int(positions[-1])
    assert bool(np.all(valid[first : last + 1]))
    capacity = min(
        int(resources.chunk_samples),
        int(resources.hard_max_chunk_samples),
        int(resources.max_work_bytes) // 64,
    )
    parts: list[np.ndarray] = []
    for start in range(first, last + 1, capacity):
        stop = min(last + 1, start + capacity)
        chunk, chunk_valid = phase_residual_impl(
            record, phase, means, start, stop, resources=resources
        )
        assert bool(np.all(chunk_valid))
        parts.append(chunk)
    residual = np.concatenate(parts)
    window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(segment) / segment)
    triads = declared_triads(_locked().base_frequencies_hz, _locked().maximum_triads)
    bins = sorted({round(value * segment / sample_rate_hz) for triad in triads for value in triad})
    columns: dict[int, list[complex]] = {index: [] for index in bins}
    for start in range(0, residual.size - segment + 1, hop):
        frame = residual[start : start + segment]
        spectrum = np.fft.rfft((frame - frame.mean()) * window)
        for index in bins:
            columns[index].append(spectrum[index])
    gathered = {index: np.asarray(values) for index, values in columns.items()}
    bicoherence = np.zeros(len(triads), dtype=np.float64)
    biphase = np.zeros(len(triads), dtype=np.float64)
    for position, (low, high, total) in enumerate(triads):
        first_bin = gathered[round(low * segment / sample_rate_hz)]
        second_bin = gathered[round(high * segment / sample_rate_hz)]
        third_bin = gathered[round(total * segment / sample_rate_hz)]
        bispectrum = np.sum(first_bin * second_bin * np.conjugate(third_bin))
        denominator = np.sum(np.abs(first_bin * second_bin) ** 2) * np.sum(np.abs(third_bin) ** 2)
        bicoherence[position] = float(abs(bispectrum) ** 2 / denominator)
        biphase[position] = float(np.angle(bispectrum))
    return bicoherence, biphase


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


def test_standard_profile_record_measures_every_triad_on_the_one_millisecond_grid(
    tmp_path: Path,
) -> None:
    """500 кГц: сегмент 500 отсчётов даёт шаг ровно 1000 Hz — все 15 триад измеримы."""
    session = _write_session(tmp_path / "f18-standard", _STANDARD_FS_HZ, _STANDARD_SAMPLES)
    loaded = _publish_twice(session, _STANDARD_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_measured(f18, loaded, _STANDARD_SAMPLES)

    # Единственная причина — no_significant_triad: измерение полное, но dual null
    # не разрешает насыщенные триады (F18-4), и честный отчёт называет их незначимыми.
    assert f18.reason_codes == (NO_SIGNIFICANT_TRIAD,)
    # Аналитика решётки: пять баз по правилу i <= j дают ровно n(n+1)/2 = 15 триад,
    # сегмент round(0.001 * 500000) = 500, шаг 500000 / 500 = 1000 Hz = НОК баз.
    locked = _locked()
    assert len(locked.base_frequencies_hz) * 6 // 2 == _DECLARED_TRIADS
    grid = _grid(_STANDARD_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, _DECLARED_TRIADS)
    assert grid.off_grid_count == 0
    assert not grid_reason_codes(grid)
    positions = (
        np.asarray(locked.base_frequencies_hz)
        * segment_samples_for(_STANDARD_FS_HZ)
        / _STANDARD_FS_HZ
    )
    assert positions.tolist() == [3.0, 5.0, 10.0, 20.0, 50.0]
    # F18-5 после объявления длительности: gcd баз 1000, решётка segment * 1000 равна
    # самой частоте, поэтому 500 кГц ниже пути анализа проходит без приведения.
    assert math.gcd(*(round(value) for value in locked.base_frequencies_hz)) == 1_000
    assert segment_samples_for(_STANDARD_FS_HZ) * 1_000 == _STANDARD_FS_HZ
    assert _exact_bin_lattice_hz(_STANDARD_FS_HZ) % int(_STANDARD_FS_HZ) == 0

    # Измерение сверяется с аналитикой, выведенной из фикстуры: см. _derived_bicoherence.
    bicoherence = _domain(loaded, "bicoherence_squared")
    derived, _ = _derived_bicoherence(session, _STANDARD_FS_HZ)
    coupled = list(_COUPLED_PHI)
    absent = list(_ABSENT_SUM_INDICES)
    assert bicoherence[coupled] == pytest.approx(derived[coupled], abs=_COUPLED_TOLERANCE)
    assert bicoherence[absent] == pytest.approx(derived[absent], abs=_FREE_TOLERANCE)
    # Разделение связанных и свободных триад сохраняется: утечка лестницы средних
    # держит свободные ниже 0.04, а связанные выше 0.99.
    assert bool(np.all(bicoherence[coupled] > 0.99))
    assert bool(np.all(bicoherence[absent] < 0.04))


def test_crash_band_rate_measures_the_measurable_subset_over_the_qualified_span(
    tmp_path: Path,
) -> None:
    """200 кГц: 14 триад из 15 измерены, 100 кГц отрезана clamps, seam жив."""
    session = _write_session(tmp_path / "f18-crash", _CRASH_BAND_FS_HZ, _CRASH_BAND_SAMPLES)
    loaded = _publish_twice(session, _CRASH_BAND_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_measured(f18, loaded, _CRASH_BAND_SAMPLES)

    # Причины сетки не теряются измерением: triad_above_nyquist остаётся в vocabulary
    # семейства, а насыщенные триады честно названы незначимыми (F18-4).
    assert f18.reason_codes == (NO_SIGNIFICANT_TRIAD, TRIAD_ABOVE_NYQUIST)
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
    available = _domain(loaded, "triad_available").astype(bool)
    assert available.tolist() == [True] * 14 + [False]
    assert _domain(loaded, "triad_sum_hz").tolist()[14] == 100_000.0
    # Дискриминант новой сетки: 204.8 кГц остаётся целиком вне решётки 1 мс
    # (round(0.001 * 204800) = 205, 3000 Гц попадает в бин 3.0029), поэтому тест
    # различает частоты, а не принимает любую.
    off_grid = _grid(204_800.0)
    assert (off_grid.declared_count, _measured(off_grid)) == (_DECLARED_TRIADS, 0)
    assert off_grid.off_grid_count == 14
    assert off_grid.above_nyquist_count == 1
    assert grid_reason_codes(off_grid) == {TRIAD_ABOVE_NYQUIST, TRIAD_OFF_GRID}
    # Измерение сверяется с аналитикой, выведенной из фикстуры.
    bicoherence = _domain(loaded, "bicoherence_squared")
    derived, _ = _derived_bicoherence(session, _CRASH_BAND_FS_HZ)
    coupled = list(_COUPLED_PHI)
    absent = list(_ABSENT_SUM_INDICES)
    assert bicoherence[coupled] == pytest.approx(derived[coupled], abs=_COUPLED_TOLERANCE)
    assert bicoherence[absent] == pytest.approx(derived[absent], abs=_FREE_TOLERANCE)
    # Biphase публикуется ровно для BH-значимых триад, иначе masked absence.
    # Связанные триады не насыщены в точности (утечка лестницы средних), суррогаты
    # dual null измеряют ту же утечку, поэтому значимых триад нет вовсе.
    significant = _domain(loaded, "significant").astype(bool)
    assert not bool(np.any(significant))
    assert np.array_equal(_domain(loaded, "biphase_valid").astype(bool), significant)
    assert bool(np.all(_domain(loaded, "biphase_rad") == 0.0))
    assert bool(np.all(_domain(loaded, "dual_null_p_value")[available] >= 0.01))


def test_exact_grid_rate_measures_every_declared_triad_at_the_coupled_truth(
    tmp_path: Path,
) -> None:
    """512 кГц: все 15 триад измеримы, связанные меряют выведенную истину фикстуры."""
    session = _write_session(tmp_path / "f18-grid", _EXACT_GRID_FS_HZ, _EXACT_GRID_SAMPLES)
    loaded = _publish_twice(session, _EXACT_GRID_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_measured(f18, loaded, _EXACT_GRID_SAMPLES)

    assert f18.reason_codes == (NO_SIGNIFICANT_TRIAD,)
    grid = _grid(_EXACT_GRID_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, _DECLARED_TRIADS)
    assert not grid_reason_codes(grid)
    # Решётка 1 мс на 512 кГц: 512 * 1000 = 512000 делится на частоту без остатка.
    assert _exact_bin_lattice_hz(_EXACT_GRID_FS_HZ) == 512_000
    assert _exact_bin_lattice_hz(_EXACT_GRID_FS_HZ) % int(_EXACT_GRID_FS_HZ) == 0
    # Аналитика фикстуры: у связанных триад f_j = f_1 + f_2 присутствует в ch1 с
    # постоянной фазой, у триад с отсутствующей суммой её нет. Обе группы сверяются
    # с выводом из фикстуры, а не с идеализированными 1 и 0: лестница 64-бинных
    # фазовых средних возмущает триадные бины (см. _derived_bicoherence).
    bicoherence = _domain(loaded, "bicoherence_squared")
    derived, biphase_derived = _derived_bicoherence(session, _EXACT_GRID_FS_HZ)
    coupled = list(_COUPLED_PHI)
    absent = list(_ABSENT_SUM_INDICES)
    assert bicoherence[coupled] == pytest.approx(derived[coupled], abs=_COUPLED_TOLERANCE)
    assert bicoherence[absent] == pytest.approx(derived[absent], abs=_FREE_TOLERANCE)
    assert _domain(loaded, "triad_sum_hz")[absent].tolist() == [23e3, 15e3, 25e3, 55e3]
    # Разделение связанных и свободных триад сохраняется: утечка лестницы средних
    # держит свободные ниже 0.04, а связанные выше 0.99.
    assert bool(np.all(bicoherence[coupled] > 0.99))
    assert bool(np.all(bicoherence[absent] < 0.04))
    # Biphase аналитики: угол выведенного биспектра связанной триады равен -phi
    # с точностью до возмущения утечкой лестницы (измерено |отклонение| <= 0.006).
    # Публикация движка маскирует biphase по значимости, поэтому аналитика живёт здесь.
    for index, phi in _COUPLED_PHI.items():
        assert biphase_derived[index] == pytest.approx(-phi, abs=1e-2)
    # Все тоны фикстуры кратны 50 Гц, то есть кадрово-согласованны с корнем фазы,
    # поэтому суррогаты измеряют ту же утечку, что и наблюдение: dual null не имеет
    # разрешения при насыщении, и триада насыщения честно названа незначимой (F18-4).
    # Biphase поэтому структурно отсутствует, а не выдумана нулём.
    significant = _domain(loaded, "significant").astype(bool)
    assert not bool(np.any(significant))
    assert not bool(np.any(_domain(loaded, "biphase_valid").astype(bool)))
    assert bool(np.all(_domain(loaded, "biphase_rad") == 0.0))
    assert bool(np.all(_domain(loaded, "dual_null_p_value") >= 0.01))


def test_empty_domain_rate_stays_unavailable_above_nyquist(tmp_path: Path) -> None:
    """8 кГц: clamp 0.45 * fs = 3600 Гц ниже минимальной суммы 6000 Гц — домены пусты."""
    session = _write_session(tmp_path / "f18-empty", _EMPTY_DOMAIN_FS_HZ, _EMPTY_DOMAIN_SAMPLES)
    loaded = _publish_twice(session, _EMPTY_DOMAIN_FS_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_unavailable_and_empty(f18, loaded)
    assert f18.reason_codes == (TRIAD_ABOVE_NYQUIST,)

    # Аналитика отказа: сегмент 8 отсчётов даёт шаг 1000 Гц и базы на целых позициях,
    # но 0.45 * 8000 = 3600 Гц ниже минимальной суммы триад 6000 Гц — все 15 срезаны.
    grid = _grid(_EMPTY_DOMAIN_FS_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, 0)
    assert grid.above_nyquist_count == _DECLARED_TRIADS
    assert grid.off_grid_count == 0
    assert grid_reason_codes(grid) == {TRIAD_ABOVE_NYQUIST}
    assert grid.effective_high_hz == pytest.approx(0.45 * _EMPTY_DOMAIN_FS_HZ)
    assert 0.45 * _EMPTY_DOMAIN_FS_HZ < 6_000.0


def test_integer_megahertz_rates_land_on_the_one_millisecond_lattice() -> None:
    """Каждое целое МГц 1..15 лежит на решётке 1 мс: сегмент 1000k, шаг 1000 Гц."""
    for megahertz in range(1, 16):
        # Арифметика решётки: ячейка решётки 1 мс равна round(0.001 * 1 МГц) * 1000 = 1 МГц,
        # каждое целое МГц делится на неё нацело, сегмент равен k * 1000 отсчётов, а
        # решётка segment * 1000 совпадает с самой частотой — без остатка.
        assert megahertz * 1_000_000 % (round(0.001 * 1_000_000.0) * 1_000) == 0
        rate = float(megahertz) * 1_000_000.0
        assert segment_samples_for(rate) == megahertz * 1_000
        assert _exact_bin_lattice_hz(rate) % int(rate) == 0
        # Производственный помощник сетки согласен: все 15 триад измеримы на каждом
        # целом МГц — F18 измерим на любой аппаратной частоте захвата (F18-5).
        grid = _grid(rate)
        assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, _DECLARED_TRIADS)
        assert not grid_reason_codes(grid)
