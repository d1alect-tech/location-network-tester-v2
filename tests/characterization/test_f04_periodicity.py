"""F04 overlapping_allan_deviation_and_cycle_autocorrelation RED analytic tests."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, replace

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.f04_periodicity import (
    METHOD,
    F04Result,
    compute_f04_multicycle_periodicity,
)
from lnt.characterization.f06_modulation import F06Result
from lnt.characterization.phase_model import PhaseCycles
from lnt.characterization.records import Status

FS_HZ = 8000.0
LINE_HZ = 50.0
CARRIER_HZ = 30_000.0
DECLARED_FACTORS = (1, 2, 4, 8, 16, 32)
DECLARED_LAGS = tuple(range(1, 33))
MINIMUM_CYCLES = 100
CARRIER_MINIMUM_SNR_DB = 10.0
MAXIMUM_FRACTION = 1.0 / 3.0
MAXIMUM_STORED = 4096
WHITE_FM_SIGMA = 2e-4
WHITE_FM_CYCLES = 240
WHITE_FM_SEED = 6022
DECLARED_CODES = frozenset(
    {
        "record_too_short_for_tau",
        "carrier_unavailable",
        "phase_unwrap_failed",
        "not_enough_samples",
        "grid_unstable",
    }
)


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=262_144,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4096,
        max_surrogates=19,
        deterministic_seed=6022,
    )


@dataclass(frozen=True, slots=True)
class _Declared:
    """Объявленные гейты рецепта в одном месте; тест переопределяет по одному."""

    sample_rate_hz: float = FS_HZ
    line_frequency_hz: float = LINE_HZ
    averaging_factors: tuple[int, ...] = DECLARED_FACTORS
    maximum_averaging_fraction_of_record: float = MAXIMUM_FRACTION
    minimum_cycles: int = MINIMUM_CYCLES
    carrier_minimum_snr_db: float = CARRIER_MINIMUM_SNR_DB
    autocorrelation_lags_cycles: tuple[int, ...] = DECLARED_LAGS
    resources: ResourceLimits = field(default_factory=_resources)


def _phase_from_durations(durations_s: np.ndarray, fs: float = FS_HZ) -> PhaseCycles:
    starts = np.concatenate(([0.0], np.cumsum(durations_s[:-1]) * fs))
    ends = starts + durations_s * fs
    total = round(float(np.sum(durations_s)) * fs)
    return PhaseCycles(
        sample_rate_hz=fs,
        sample_count=total,
        cycle_start_samples=starts.astype(np.float64),
        cycle_end_samples=ends.astype(np.float64),
        cycle_valid=np.ones(durations_s.size, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _stable_f06(
    record_samples: int,
    *,
    frequency_hz: float = CARRIER_HZ,
    snr_db: float | None = 40.0,
    stored: int = MAXIMUM_STORED,
) -> F06Result:
    indices = np.floor(np.arange(stored) * record_samples / stored).astype(np.int64)
    return F06Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        stored_indices=indices,
        amplitudes_v=np.ones(stored, dtype=np.float64),
        phases_rad=2.0 * np.pi * frequency_hz * indices.astype(np.float64) / FS_HZ,
        frequencies_hz=np.full(stored, frequency_hz, dtype=np.float64),
        start_sample=0,
        stop_sample=record_samples,
        observation_count=record_samples,
        missing_count=0,
        stored_count=stored,
        snr_db=snr_db,
        components=1,
    )


def _unavailable_f06(record_samples: int) -> F06Result:
    empty = np.empty(0, dtype=np.float64)
    return F06Result(
        status=Status.UNAVAILABLE,
        reason_codes=("multiple_components",),
        stored_indices=np.empty(0, dtype=np.int64),
        amplitudes_v=empty,
        phases_rad=empty.copy(),
        frequencies_hz=empty.copy(),
        start_sample=0,
        stop_sample=0,
        observation_count=0,
        missing_count=record_samples,
        stored_count=0,
        snr_db=None,
        components=2,
    )


def _evaluate(
    phase: PhaseCycles,
    f06: F06Result,
    record_samples: int,
    **overrides: object,
) -> F04Result:
    declared = replace(_Declared(), **overrides)
    samples = np.zeros(record_samples, dtype=np.float64)
    carrier = np.zeros(record_samples, dtype=np.float64)
    return compute_f04_multicycle_periodicity(
        samples,
        sample_rate_hz=declared.sample_rate_hz,
        phase=phase,
        carrier=carrier,
        f06_result=f06,
        line_frequency_hz=declared.line_frequency_hz,
        averaging_factors=declared.averaging_factors,
        maximum_averaging_fraction_of_record=declared.maximum_averaging_fraction_of_record,
        minimum_cycles=declared.minimum_cycles,
        carrier_minimum_snr_db=declared.carrier_minimum_snr_db,
        autocorrelation_lags_cycles=declared.autocorrelation_lags_cycles,
        resources=declared.resources,
    )


def _white_fm_durations(
    cycles: int = WHITE_FM_CYCLES, sigma: float = WHITE_FM_SIGMA
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(WHITE_FM_SEED)
    y = rng.standard_normal(cycles) * sigma
    durations = 1.0 / (LINE_HZ * (1.0 + y))
    return durations, y


def test_method_is_the_declared_recipe_method() -> None:
    assert METHOD == "overlapping_allan_deviation_and_cycle_autocorrelation"


def test_white_fm_recovers_the_declared_adev_level() -> None:
    """Уровень ADEV(m=1) равен сигме белого ЧМ: E[AVAR]=sigma^2, ADEV=sigma.

    Допуск 20% относительных: при N=240 оценка AVAR имеет ~N степеней свободы,
    её относительный разброс sqrt(2/N)~9%; 20% это двойной запас на перекрытие
    и детерминированный сид 6022, а не подгонка под выход движка.
    """
    durations, _ = _white_fm_durations()
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    assert result.status is Status.AVAILABLE
    assert result.adev_mains is not None
    assert result.tau_s.size == len(DECLARED_FACTORS)
    assert result.adev_mains[0] == pytest.approx(WHITE_FM_SIGMA, rel=0.20)


def test_white_fm_slope_is_tau_minus_half() -> None:
    """Белый ЧМ: AVAR(m)=sigma^2/m, наклон log-log равен -0.5.

    Допуск +-0.10 на наклон по m=1..8: перекрывающиеся оценки коррелированы,
    но отношение ADEV(4)/ADEV(1) обязано быть 1/2; 15% на отношение покрывает
    выборочный разброс N=240 с запасом вдвое и следует из замкнутой формы выше.
    """
    durations, _ = _white_fm_durations()
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    assert result.adev_mains is not None
    ratio = float(result.adev_mains[2] / result.adev_mains[0])
    assert ratio == pytest.approx(0.5, rel=0.15)
    slope = float(np.polyfit(np.log(result.tau_s[:3]), np.log(result.adev_mains[:3]), 1)[0])
    assert slope == pytest.approx(-0.5, abs=0.10)


def test_stable_tone_gives_zero_adev() -> None:
    """Постоянные длительности дают y=const, все разности ADEV тождественно нулевые.

    Допуск 1e-12 абсолютный: чистая арифметика float64 над одинаковыми значениями,
    на шесть порядков ниже минимального белого уровня 2e-4 и на три порядка ниже
    eps-накопления за 240 циклов.
    """
    durations = np.full(MINIMUM_CYCLES + 20, 1.0 / LINE_HZ)
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    assert result.status is Status.AVAILABLE
    assert result.adev_mains is not None
    assert result.adev_carrier is not None
    assert float(np.max(np.abs(result.adev_mains))) <= 1e-12
    assert float(np.max(np.abs(result.adev_carrier))) <= 1e-12


def test_stable_tone_shows_no_period_two_band() -> None:
    """Дисперсия нулевая: нормированная ACF не определена, движок публикует нули.

    Допуск 1e-12: метод не выдумывает мультициклическую структуру из ничего;
    любой пик |ACF|>1e-9 на стабильном тоне был бы фабрикацией периода.
    """
    durations = np.full(MINIMUM_CYCLES + 20, 1.0 / LINE_HZ)
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    assert result.cycle_acf.size == len(DECLARED_LAGS)
    assert float(np.max(np.abs(result.cycle_acf))) <= 1e-12


def test_tau_beyond_third_of_record_is_not_fabricated() -> None:
    """m > floor(N/3) и floor(N/m) < 3 не публикуются; код объявлен, сетка ужата.

    N=12, m из {1,2,4,8,16,32}: допустимы 1,2,4 (4<=floor(12/3)=4 и 12//4=3);
    8,16,32 отрезаны обеими сторонами гейта. Проверка точная, без допусков.
    """
    durations = np.full(12, 1.0 / LINE_HZ)
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count, minimum_cycles=5)
    assert result.status is Status.PARTIAL
    assert "record_too_short_for_tau" in result.reason_codes
    assert list(result.tau_s) == [pytest.approx(v) for v in (1 / LINE_HZ * m for m in (1, 2, 4))]
    assert result.adev_mains is not None
    assert result.adev_mains.size == 3


def test_99_cycles_is_not_enough_samples() -> None:
    durations = np.full(99, 1.0 / LINE_HZ)
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("not_enough_samples",)
    assert result.adev_mains is None
    assert result.adev_carrier is None


def test_carrier_unavailable_keeps_mains_path() -> None:
    """Отказ F06 снимает только путь (a): сеть жива, отношение не публикуется."""
    durations, _ = _white_fm_durations()
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _unavailable_f06(phase.sample_count), phase.sample_count)
    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("carrier_unavailable",)
    assert result.adev_mains is not None
    assert result.adev_carrier is None
    assert result.carrier_to_mains_ratio is None
    assert result.phase_slip_cycles is not None


def test_low_snr_carrier_is_unavailable() -> None:
    durations = np.full(MINIMUM_CYCLES + 20, 1.0 / LINE_HZ)
    phase = _phase_from_durations(durations)
    weak = _stable_f06(phase.sample_count, snr_db=5.0)
    result = _evaluate(phase, weak, phase.sample_count)
    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("carrier_unavailable",)
    assert result.adev_carrier is None
    assert result.adev_mains is not None


def test_hole_in_stored_samples_trips_phase_unwrap_failed() -> None:
    """Цикл сети без хранимых отсчётов F06: путь (a) не строится, интерполяции нет.

    Границы целые по построению: cumsum от 1/50 в float64 даёт ошибку ~1e-9
    отсчёта, и окно движка floor/ceil тогда цепляет краевой индекс соседнего
    цикла — дыра обязана быть точной, а не приблизительной.
    """
    cycles = MINIMUM_CYCLES + 20
    step = int(FS_HZ / LINE_HZ)
    starts = np.arange(cycles, dtype=np.float64) * float(step)
    phase = PhaseCycles(
        sample_rate_hz=FS_HZ,
        sample_count=cycles * step,
        cycle_start_samples=starts,
        cycle_end_samples=starts + float(step),
        cycle_valid=np.ones(cycles, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
    record = phase.sample_count
    full = _stable_f06(record)
    hole_lo = 50 * step
    hole_hi = 51 * step
    keep = (full.stored_indices < hole_lo) | (full.stored_indices >= hole_hi)
    holed = replace(
        full,
        stored_indices=full.stored_indices[keep],
        amplitudes_v=full.amplitudes_v[keep],
        phases_rad=full.phases_rad[keep],
        frequencies_hz=full.frequencies_hz[keep],
        stored_count=int(np.count_nonzero(keep)),
    )
    result = _evaluate(phase, holed, record)
    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("phase_unwrap_failed",)
    assert result.adev_carrier is None
    assert result.adev_mains is not None


def test_period_two_structure_visible_in_acf_at_declared_lag() -> None:
    """Чередование +-a даёт замкнутую форму ACF: rho(1)=-1, rho(2)=+1.

    Допуск 0.05 абсолютный: при N=120 оценка нормированной ACF сходится к
    замкнутой форме с ошибкой O(1/N)~0.008; 0.05 это шестикратный запас,
    следующий из прямого подсчёта сумм, а не из выхода движка.
    """
    amplitude = 1e-3
    cycles = MINIMUM_CYCLES + 20
    signs = np.where(np.arange(cycles) % 2 == 0, 1.0, -1.0)
    durations = (1.0 / LINE_HZ) * (1.0 + amplitude * signs)
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    lags = list(result.acf_lag_cycles)
    assert 1 in lags
    assert 2 in lags
    rho1 = float(result.cycle_acf[lags.index(1)])
    rho2 = float(result.cycle_acf[lags.index(2)])
    assert rho1 == pytest.approx(-1.0, abs=0.05)
    assert rho2 == pytest.approx(1.0, abs=0.05)


def test_reason_codes_are_closed_vocabulary() -> None:
    durations = np.full(MINIMUM_CYCLES + 20, 1.0 / LINE_HZ)
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    assert set(result.reason_codes) <= DECLARED_CODES


def test_result_is_frozen() -> None:
    durations = np.full(MINIMUM_CYCLES + 20, 1.0 / LINE_HZ)
    phase = _phase_from_durations(durations)
    result = _evaluate(phase, _stable_f06(phase.sample_count), phase.sample_count)
    with pytest.raises(dataclasses.FrozenInstanceError):
        F04Result.__setattr__(result, "status", Status.UNAVAILABLE)
