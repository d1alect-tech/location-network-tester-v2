"""F07 two_window_real_cepstrum_and_sideband_symmetry RED analytic tests."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.f01_phase_cycle import F01Result
from lnt.characterization.f07_cepstrum import (
    compute_f07_comb_cepstrum,
)
from lnt.characterization.f07_result import (
    BELOW_RESOLUTION,
    DECLARED_CODES,
    HARMONIC_COMB_ONLY,
    LOG_FLOOR_UNSTABLE,
    METHOD,
    NO_DOMINANT_QUEFRENCY,
    WINDOW_DEPENDENT,
    F07Result,
)
from lnt.characterization.records import Status, Unit, validate_unit_name

FS_HZ = 50_000.0
FFT_SAMPLES = 16_384
F1_HZ = 50.0
WINDOWS = ("hann", "blackman")
LOG_FLOOR_DB = 20.0
MIN_QUEFRENCY = 2
OFFSET_BINS = (1, 2, 3, 4, 5)
SPACING_CROSSCHECK = "magnitude_spectrum_autocorrelation"
WINDOW_PEAK_TOLERANCE_BINS = 1

EXPECTED_CODES = frozenset(
    {
        "harmonic_comb_only",
        "window_dependent",
        "no_dominant_quefrency",
        "below_resolution",
        "log_floor_unstable",
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
    fft_samples: int = FFT_SAMPLES
    windows: tuple[str, ...] = WINDOWS
    log_floor_db_below_maximum: float = LOG_FLOOR_DB
    minimum_quefrency_samples: int = MIN_QUEFRENCY
    offset_bins: tuple[int, ...] = OFFSET_BINS
    spacing_crosscheck: str = SPACING_CROSSCHECK
    window_peak_tolerance_bins: int = WINDOW_PEAK_TOLERANCE_BINS
    resources: ResourceLimits = field(default_factory=_resources)


def _f01(f1_hz: float | None) -> F01Result:
    if f1_hz is None:
        return F01Result(
            status=Status.UNAVAILABLE,
            reason_codes=("grid_unstable",),
            f1_hz=None,
            c_k_v=None,
            phi_rel_k_rad=None,
            phase_resultant_k=None,
            x_template_v=None,
            window_count=12,
            evaluated_window_count=0,
        )
    return F01Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        f1_hz=f1_hz,
        c_k_v=None,
        phi_rel_k_rad=None,
        phase_resultant_k=None,
        x_template_v=None,
        window_count=12,
        evaluated_window_count=12,
    )


def _run(
    samples: np.ndarray,
    *,
    f1: float | None = F1_HZ,
    declared: _Declared | None = None,
) -> F07Result:
    d = declared or _Declared()
    return compute_f07_comb_cepstrum(
        samples,
        sample_rate_hz=d.sample_rate_hz,
        f01_result=_f01(f1),
        fft_samples=d.fft_samples,
        windows=d.windows,
        log_floor_db_below_maximum=d.log_floor_db_below_maximum,
        minimum_quefrency_samples=d.minimum_quefrency_samples,
        offset_bins=d.offset_bins,
        spacing_crosscheck=d.spacing_crosscheck,
        window_peak_tolerance_bins=d.window_peak_tolerance_bins,
        resources=d.resources,
    )


def _pulse_train(period: int) -> np.ndarray:
    """Периодическая последовательность импульсов T=period (1.0 в отсчёте, иначе 0)."""
    x = np.zeros(FFT_SAMPLES, dtype=np.float64)
    x[::period] = 1.0
    return x


def _harmonic_comb() -> np.ndarray:
    """Чистая гармоническая гребёнка сети: 50 Гц и гармоники до 500 Гц."""
    n = np.arange(FFT_SAMPLES, dtype=np.float64)
    return np.sum(
        [np.sin(2.0 * np.pi * k * F1_HZ * n / FS_HZ) for k in range(1, 11)],
        axis=0,
    )


def _two_impulse(offset: int) -> np.ndarray:
    """Два импульса на расстоянии N/2: вырожденное ниже разрешения чередование."""
    x = np.zeros(FFT_SAMPLES, dtype=np.float64)
    x[offset] = 1.0
    x[offset + FFT_SAMPLES // 2] = 1.0
    return x


def _mix(t1: int, t2: int, weight: float) -> np.ndarray:
    """Сумма двух синфазных импульсных последовательностей T1 и T2."""
    a = np.zeros(FFT_SAMPLES, dtype=np.float64)
    b = np.zeros(FFT_SAMPLES, dtype=np.float64)
    a[::t1] = 1.0
    b[::t2] = 1.0
    return a + weight * b


def _slow_am() -> np.ndarray:
    """Медленная АМ: огибающая 2 Гц ниже разрешения на несущей 5 кГц."""
    n = np.arange(FFT_SAMPLES, dtype=np.float64)
    return (1.0 + 0.5 * np.cos(2.0 * np.pi * 2.0 * n / FS_HZ)) * np.sin(
        2.0 * np.pi * 5000.0 * n / FS_HZ
    )


def _noise(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(FFT_SAMPLES)


def test_method_identifier_matches_contract() -> None:
    """Замороженный метод из контракта рецепта."""
    assert METHOD == "two_window_real_cepstrum_and_sideband_symmetry"


def test_reason_code_vocabulary_is_closed() -> None:
    """Словарь кодов закрыт и публичен, без посторонних значений."""
    assert DECLARED_CODES == (
        HARMONIC_COMB_ONLY,
        WINDOW_DEPENDENT,
        NO_DOMINANT_QUEFRENCY,
        BELOW_RESOLUTION,
        LOG_FLOOR_UNSTABLE,
    )
    assert set(DECLARED_CODES) == EXPECTED_CODES


def test_pulse_train_100_recovers_exact_period() -> None:
    """Положительное из спеки: T=100 → q=100, df=fs/T."""
    result = _run(_pulse_train(100))
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.df_hz == pytest.approx(FS_HZ / 100.0, rel=1e-12)
    assert result.q_s == pytest.approx(100.0 / FS_HZ, rel=1e-12)
    assert result.quefrency_amplitude is not None
    assert result.quefrency_amplitude > 0.0
    assert result.sym_db is not None
    assert math.isfinite(result.sym_db)
    assert (result.sample_count, result.observation_count) == (1, 1)
    assert (result.missing_count, result.stored_count) == (0, 1)


def test_pulse_train_200_recovers_exact_period() -> None:
    """Положительное из спеки: T=200 → df=fs/200."""
    result = _run(_pulse_train(200))
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.df_hz == pytest.approx(FS_HZ / 200.0, rel=1e-12)
    assert result.q_s == pytest.approx(200.0 / FS_HZ, rel=1e-12)


def test_pure_harmonic_comb_is_flagged() -> None:
    """Контроль: гармоническая гребёнка f1 → harmonic_comb_only, скаляры не публикуются."""
    result = _run(_harmonic_comb())
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (HARMONIC_COMB_ONLY,)
    assert result.df_hz is None
    assert result.q_s is None
    assert result.sym_db is None
    assert result.quefrency_amplitude is None
    assert (result.observation_count, result.stored_count) == (0, 0)
    assert result.missing_count == 1


def test_spacing_below_resolution_is_flagged() -> None:
    """Ограничение: шаг у нижней границы разрешения → below_resolution."""
    result = _run(_two_impulse(1000))
    assert result.status is Status.UNAVAILABLE
    assert BELOW_RESOLUTION in result.reason_codes


def test_window_dependent_peak_is_not_reported() -> None:
    """Окна: синфазная смесь T=103+110 даёт Hann 220 против Blackman 110."""
    result = _run(_mix(103, 110, 1.0))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (WINDOW_DEPENDENT,)
    assert result.df_hz is None


def test_log_floor_unstable_peak_is_not_reported() -> None:
    """Пол: смесь T=100+133 (w=0.8) сдвигает пик 100→133 при 40 дБ."""
    result = _run(_mix(100, 133, 0.8))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (LOG_FLOOR_UNSTABLE,)


def test_slow_modulation_has_no_dominant_quefrency() -> None:
    """Порог: огибающая ниже разрешения не даёт доминантного кепстра."""
    result = _run(_slow_am())
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (NO_DOMINANT_QUEFRENCY,)


def test_white_noise_has_no_dominant_quefrency() -> None:
    """Порог: белый шум ниже отношения пика к процентильному полу."""
    result = _run(_noise(6022))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (NO_DOMINANT_QUEFRENCY,)


def test_f1_unavailable_refuses_the_comb_path() -> None:
    """F07-3: без f1 гребёнку сети исключить нельзя, путь отказывает."""
    result = _run(_pulse_train(100), f1=None)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (HARMONIC_COMB_ONLY,)


def test_runs_are_bitwise_deterministic() -> None:
    """Два прогона побитово идентичны."""
    first = _run(_pulse_train(100))
    second = _run(_pulse_train(100))
    assert first == second
    assert first.df_hz == second.df_hz
    assert first.q_s == second.q_s
    assert first.sym_db == second.sym_db
    assert first.quefrency_amplitude == second.quefrency_amplitude


@pytest.mark.parametrize(
    ("rate", "fft"),
    [
        (float("nan"), FFT_SAMPLES),
        (float("inf"), FFT_SAMPLES),
        (0.0, FFT_SAMPLES),
        (-FS_HZ, FFT_SAMPLES),
        (FS_HZ, 0),
        (FS_HZ, -1024),
    ],
)
def test_invalid_numeric_inputs_raise_valueerror(rate: float, fft: int) -> None:
    """Невалидная частота/длина ЖПФ — ValueError, внесловарные отказы не бросают исключений."""
    declared = _Declared(sample_rate_hz=rate, fft_samples=fft)
    with pytest.raises(ValueError, match=r"sample rate|fft_samples"):
        _run(_pulse_train(100), declared=declared)


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("df_hz", Unit.HZ),
        ("q_s", Unit.S),
        ("sym_db", Unit.RATIO),
        ("quefrency_amplitude", Unit.RATIO),
    ],
)
def test_persisted_scalar_units_are_accepted(name: str, unit: Unit) -> None:
    """Единицы скаляров принимаются словарём единиц."""
    validate_unit_name(name, unit)
