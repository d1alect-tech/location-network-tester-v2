"""Базовые пины F18 на 1 и 8 МГц: сегмент объявлен длительностью 1 мс.

Число отсчётов сегмента выводится движком из ИЗМЕРЕННОЙ частоты, поэтому шаг сетки
больше не плывёт: на 1 МГц это round(0.001 * 10^6) = 1000 отсчётов, то есть ровно
fs/1000 = 1000 Hz — НОК пяти объявленных баз. Все 15 триад измеримы, а пять баз дают
позиции 3, 5, 10, 20 и 50. 8 МГц — частота захвата Hantek 6022BE — меряется на
объявленном пути анализа 1 МГц: запись приводится вниз ЦЕЛЫМ фактором 8, поэтому
2.4 s дают 2 400 000 отсчётов вместо 19 200 000 и перестают отказывать по бюджету
суррогатного источника. 500 кГц ниже 1 МГц, поэтому фактор равен 1 и запись
остаётся нетронутой.
"""

from __future__ import annotations

import functools
import hashlib
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.analysis_v2 import run_characterization
from lnt.analysis_v2.characterization_slices_bicoherence import _compute_f18
from lnt.characterization import OUTPUT_FILENAMES, Status, load_bundle
from lnt.characterization.event_models import (
    RootEvents,
    RootEventSettings,
    TaggedGap,
)
from lnt.characterization.f18_bundle import F18_ID
from lnt.characterization.f18_contract import (
    DECLARED_CODES,
    METHOD,
    TRIAD_OFF_GRID,
    analysis_factor_for,
    segment_samples_for,
)
from lnt.characterization.f18_frames import SURROGATE_BYTES_PER_SAMPLE
from lnt.characterization.f18_tables import locked_declarations
from lnt.characterization.f18_triads import build_triad_grid, grid_reason_codes
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.context.json_codec import decode_object
from lnt.events.models import UnqualifiedGap
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
# Порог длительности записи: max_work_bytes / SURROGATE_BYTES_PER_SAMPLE. Ниже
# объявленного пути анализа 1 МГц запись 8 МГц в него не влезала.
_RECORD_LENGTH_LIMIT = 8_388_608
# Объявленный путь анализа F18 и целочисленный фактор приведения к нему.
_ANALYSIS_HZ = 1_000_000.0
_HARDWARE_FACTOR = 8
# 1 МГц: сегмент 1000 отсчётов, шаг ровно 1000 Hz, поэтому пять баз дают целые
# позиции 3, 5, 10, 20 и 50. 8 МГц после приведения к 1 МГц: тот же шаг, те же позиции.
_ONE_MHZ_BASE_BINS = (3.0, 5.0, 10.0, 20.0, 50.0)
_HARDWARE_BASE_BINS = _ONE_MHZ_BASE_BINS
# 500 кГц: частота НИЖЕ объявленного пути анализа, поэтому фактор 1, а сегмент
# round(0.001 * 500000) = 500 отсчётов. Запись короче канонических 2.4 s: 40 000
# отсчётов дают 159 кадров при locked minimum_frames = 32, то есть полный замер.
_HALF_MHZ_HZ = 500_000.0
_HALF_MHZ_SAMPLES = 40_000
_HALF_MHZ_SEGMENT = 500
# Разрыв на частоте ЗАХВАТА проверяется на частоте анализа: 1 600 000 отсчётов 8 МГц
# дают 200 000 отсчётов 1 МГц, а разрыв (120 000, 200 000) пересчитывается в
# (15 000, 25 000) и блокируется ВКЛЮЧАТЕЛЬНО, поэтому длинный спан начинается с
# 25 001 и содержит 174 999 отсчётов — 348 кадров. Без пересчёта спан был бы
# (0, 120 000) и 239 кадров, а без разрыва вообще 399: три различимых исхода.
_GAP_SAMPLES = 1_600_000
_GAP_SPAN = (120_000, 200_000)
_GAP_RESCALED = (15_000, 25_000)
_GAP_ANALYSIS_SAMPLES = 200_000
# 348 полных кадров покрывают (348 - 1) * 500 + 1000 = 174 500 отсчётов: хвост
# спана в 499 отсчётов не даёт ещё одного кадра и в qualified support не входит.
_GAP_FRAMES = 348
_GAP_QUALIFIED = 174_500
# Решётка exact_fft_bins = segment * gcd(bases) = segment * 1000 Гц, а segment =
# round(0.001 * fs), поэтому на любом целом МГц решётка есть: 1 МГц даёт 1 000 000 Гц.
_ONE_MHZ_BIN_LATTICE_HZ = 1_000_000
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
        segment_samples=segment_samples_for(sample_rate_hz),
        sample_rate_hz=sample_rate_hz,
        analysis_low_hz=_recipe().stft.analysis_low_hz,
        analysis_high_hz=locked.analysis_high_hz,
        nyquist_fraction_max=locked.nyquist_fraction_max,
        maximum_triads=locked.maximum_triads,
    )


def _measured(grid: F18TriadGrid) -> int:
    return int(np.count_nonzero(grid.measurable))


def _base_bins(sample_rate_hz: float) -> np.ndarray:
    segment = segment_samples_for(sample_rate_hz)
    return np.asarray(_locked().base_frequencies_hz) * segment / sample_rate_hz


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


def _domain(loaded: LoadedCharacterization, name: str) -> np.ndarray:
    return np.asarray(loaded.arrays[f"f18_{name}"])


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


# Семья меряет: полный declared-домен и все измеримые триады доступны, а masked
# absence переживает finite-only кодек ровным нулём под validity mask.
def _assert_measured(f18: FamilyResult, loaded: LoadedCharacterization, record: int) -> None:
    assert f18.status is not Status.UNAVAILABLE
    assert f18.support.sample_count == record
    assert 0 < f18.n <= record
    assert f18.support.observation_count == f18.n
    assert f18.support.missing_count == record - f18.n
    assert {reference.shape for reference in f18.array_refs} == {(_DECLARED_TRIADS,)}
    available = _domain(loaded, "triad_available").astype(bool)
    measurable = {item.name: item.value for item in f18.comparison_summary}[
        "f18_measurable_triad_count"
    ]
    assert int(np.count_nonzero(available)) == measurable
    assert bool(np.all(_domain(loaded, "bicoherence_squared")[~available] == 0.0))
    assert bool(np.all(_domain(loaded, "dual_null_p_value")[~available] == 0.0))


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
# записи срабатывает раньше любого чтения инвентаря. Опциональный gap — на частоте
# ЗАХВАТА: replay пересобирает разрывы из замыкания над полной сеткой, поэтому индексы
# в нём всегда полноразмерные, как и в боевом пути.
def _inventory(
    sample_rate_hz: float, sample_count: int, gap: tuple[int, int] | None = None
) -> RootEvents:
    def replay(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        if gap is None:
            return iter(())
        start, stop = gap
        return iter(
            (
                TaggedGap(
                    kind="gap",
                    gap=UnqualifiedGap(
                        start_sample=start,
                        end_sample=stop,
                        start_time_s=start / sample_rate_hz,
                        end_time_s=stop / sample_rate_hz,
                    ),
                ),
            )
        )

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
        gap_count=0 if gap is None else 1,
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=replay,
    )


def test_one_megahertz_canonical_record_measures_every_triad_on_the_exact_bin_lattice(
    tmp_path: Path,
) -> None:
    """1 МГц: сегмент 1000 отсчётов даёт шаг 1000 Hz — все 15 триад измеримы."""
    session = _write_session(tmp_path / "f18-1mhz-on-grid", _ONE_MHZ_HZ, _ONE_MHZ_SAMPLES)
    loaded = _publish_twice(session, _ONE_MHZ_HZ)
    f18 = loaded.bundle.families[_F18_INDEX]
    _assert_identity(f18, loaded)
    _assert_measured(f18, loaded, _ONE_MHZ_SAMPLES)

    # Причина triad_off_grid на решётке недостижима: все базы измеримы, поэтому её
    # нет и среди опубликованных кодов семьи.
    assert TRIAD_OFF_GRID not in f18.reason_codes

    # Аналитика измерения: пять баз по правилу i <= j дают ровно n(n+1)/2 = 15 триад,
    # а 1 000 000 / 1000 = ровно 1000 Hz на бин, поэтому пять бас ложатся на целые
    # позиции 3, 5, 10, 20 и 50.
    locked = _locked()
    assert locked.segment_duration_s == 0.001
    assert segment_samples_for(_ONE_MHZ_HZ) == 1_000
    assert len(locked.base_frequencies_hz) * 6 // 2 == _DECLARED_TRIADS
    grid = _grid(_ONE_MHZ_HZ)
    assert (grid.declared_count, _measured(grid)) == (_DECLARED_TRIADS, _DECLARED_TRIADS)
    assert grid.off_grid_count == 0
    assert grid.above_nyquist_count == 0
    assert not grid_reason_codes(grid)

    # F18-5 после починки: решётка segment * gcd(bases) = segment * 1000 Гц равна самой
    # частоте на каждом целом МГц 1..15, поэтому объявленные базы стоят на решётке на
    # ЛЮБОЙ поддерживаемой аппаратной частоте захвата, а не только на 1 МГц.
    assert math.gcd(*(round(value) for value in locked.base_frequencies_hz)) == 1_000
    assert segment_samples_for(_ONE_MHZ_HZ) * 1_000 == _ONE_MHZ_BIN_LATTICE_HZ
    for megahertz in range(1, 16):
        rate = float(megahertz) * 1_000_000.0
        assert segment_samples_for(rate) * 1_000 == rate

    # Позиции пяти баз на сетке из 1000 отсчётов: bin = f * 1000 / fs. Сравнение
    # точное, а не приближённое: аналитика и расчёт дают один и тот же double.
    positions = _base_bins(_ONE_MHZ_HZ)
    assert np.array_equal(positions, np.asarray(_ONE_MHZ_BASE_BINS))
    assert np.array_equal(np.rint(positions), positions)

    # Все числа артефакта конечны, то есть NaN в опубликованные домены не проходит.
    floats = [array for array in loaded.arrays.values() if np.issubdtype(array.dtype, np.floating)]
    assert all(bool(np.all(np.isfinite(array))) for array in floats)


def test_hardware_rate_measures_on_the_decimated_one_megahertz_analysis_path() -> None:
    """8 МГц: фактор 8 снимает отказ по длине, запись меряется на 1 МГц."""
    limits = _recipe().resource_limits
    # Арифметика порога как истина, а не согласие движка с самим собой.
    assert limits.max_work_bytes // SURROGATE_BYTES_PER_SAMPLE == _RECORD_LENGTH_LIMIT
    assert round(2.4 * _HARDWARE_HZ) == _HARDWARE_SAMPLES
    assert _HARDWARE_SAMPLES > _RECORD_LENGTH_LIMIT
    assert _ONE_MHZ_SAMPLES < _RECORD_LENGTH_LIMIT
    # Объявленное правило приведения: целый фактор 8 и ровно 1 МГц после него.
    assert analysis_factor_for(_HARDWARE_HZ) == _HARDWARE_FACTOR
    assert _HARDWARE_HZ / _HARDWARE_FACTOR == _ANALYSIS_HZ
    assert _HARDWARE_SAMPLES // _HARDWARE_FACTOR == 2_400_000 < _RECORD_LENGTH_LIMIT
    # Сегмент выводится на ИЗМЕРЕННОЙ частоте анализа, а не на частоте захвата.
    assert segment_samples_for(_HARDWARE_HZ) == 8_000
    assert segment_samples_for(_ANALYSIS_HZ) == 1_000 <= limits.hard_max_chunk_samples

    record = _coupled_record(_HARDWARE_HZ, _HARDWARE_SAMPLES).astype(np.float32)
    result = _compute_f18(
        record,
        _phase_cycles(_HARDWARE_HZ, _HARDWARE_SAMPLES),
        _phase_means(),
        _inventory(_HARDWARE_HZ, _HARDWARE_SAMPLES),
        _recipe(),
        NEVER_CANCELLED,
    )

    # Отказа по длине записи больше нет, а sample_count равен ПРИВЕДЕННОМУ числу
    # отсчётов: validate_f18_inputs требует phase.sample_count == values.size, поэтому
    # равенство доказывается самим фактом успешного измерения, а не кодом выхода.
    assert result.status is not Status.UNAVAILABLE
    assert result.sample_count == 2_400_000
    assert result.analysis_rate_hz == _ANALYSIS_HZ
    assert result.segment_samples == 1_000 == segment_samples_for(_ANALYSIS_HZ)

    # Полоса объявлена, а не предположена: клип 0.45 * частоты анализа не срезает
    # последнюю сумму триады 50 + 50 = 100 кГц, поэтому все 15 триад доступны.
    locked = _locked()
    assert min(locked.analysis_high_hz, 0.45 * result.analysis_rate_hz) >= 100_000.0
    assert bool(result.triad_available.all())
    assert result.measurable_triad_count == _DECLARED_TRIADS
    assert result.off_grid_triad_count == 0
    assert result.above_nyquist_triad_count == 0
    assert float(result.triad_sum_hz.max()) == 100_000.0

    # Решётка после приведения совпадает с решёткой 1 МГц: шаг 1000 Hz и те же позиции.
    assert _measured(_grid(_ANALYSIS_HZ)) == _DECLARED_TRIADS
    assert not grid_reason_codes(_grid(_ANALYSIS_HZ))
    hardware_positions = _base_bins(_ANALYSIS_HZ)
    assert np.array_equal(hardware_positions, np.asarray(_HARDWARE_BASE_BINS))
    assert np.array_equal(np.rint(hardware_positions), hardware_positions)


def test_below_analysis_rate_record_keeps_factor_one_and_the_derived_segment() -> None:
    """500 кГц: частота ниже объявленного пути, фактор 1 и запись не тронута."""
    assert analysis_factor_for(_HALF_MHZ_HZ) == 1
    assert _HALF_MHZ_HZ < _ANALYSIS_HZ
    assert round(0.001 * _HALF_MHZ_HZ) == _HALF_MHZ_SEGMENT
    # Канонические 2.4 s на 500 кГц — те же 1 200 000 отсчётов без приведения.
    assert round(2.4 * _HALF_MHZ_HZ) == 1_200_000

    record = _coupled_record(_HALF_MHZ_HZ, _HALF_MHZ_SAMPLES).astype(np.float32)
    result = _compute_f18(
        record,
        _phase_cycles(_HALF_MHZ_HZ, _HALF_MHZ_SAMPLES),
        _phase_means(),
        _inventory(_HALF_MHZ_HZ, _HALF_MHZ_SAMPLES),
        _recipe(),
        NEVER_CANCELLED,
    )

    assert result.status is not Status.UNAVAILABLE
    # Фактор 1 — тождественный путь: частота записи и отсчёты не изменились.
    assert result.analysis_rate_hz == _HALF_MHZ_HZ
    assert result.sample_count == _HALF_MHZ_SAMPLES
    assert result.segment_samples == _HALF_MHZ_SEGMENT
    assert bool(result.triad_available.all())
    assert float(result.triad_sum_hz.max()) == 100_000.0


def test_replayed_gap_indices_are_rescaled_onto_the_analysis_grid() -> None:
    """Разрыв полноразмерного replay пересчитывается целочисленно, инвентарь цел.

    RootEvents.replay пересобирает разрывы из замыкания над ПОЛНОЙ частотой захвата,
    поэтому делить поля инвентаря бесполезно, а gap_count сверяется на равенство.
    Пин различим: пересчитанный разрыв даёт 349 кадров, непересчитанный — 239, а
    запись без разрыва — 399.
    """
    assert _GAP_SPAN[0] // _HARDWARE_FACTOR == _GAP_RESCALED[0]
    assert _GAP_SPAN[1] // _HARDWARE_FACTOR == _GAP_RESCALED[1]
    record = _coupled_record(_HARDWARE_HZ, _GAP_SAMPLES).astype(np.float32)
    inventory = _inventory(_HARDWARE_HZ, _GAP_SAMPLES, _GAP_SPAN)

    result = _compute_f18(
        record,
        _phase_cycles(_HARDWARE_HZ, _GAP_SAMPLES),
        _phase_means(),
        inventory,
        _recipe(),
        NEVER_CANCELLED,
    )

    assert result.status is not Status.UNAVAILABLE
    assert result.sample_count == _GAP_ANALYSIS_SAMPLES == _GAP_SAMPLES // _HARDWARE_FACTOR
    assert result.frame_count == _GAP_FRAMES
    assert (
        result.qualified_sample_count
        == _GAP_QUALIFIED
        == (
            (_GAP_FRAMES - 1) * (segment_samples_for(_ANALYSIS_HZ) // 2)
            + segment_samples_for(_ANALYSIS_HZ)
        )
    )
    # Инвентарь не тронут: ни частота, ни длина, ни gap_count не переписаны движком.
    assert inventory.sample_count == _GAP_SAMPLES
    assert inventory.sample_rate_hz == _HARDWARE_HZ
    assert inventory.gap_count == 1
