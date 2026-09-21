"""F06 butterworth_hilbert_analytic_trajectory RED analytic tests (Wave 5 todo 13)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.f06_modulation import (
    METHOD,
    F06Result,
    compute_f06_modulation_trajectories,
)
from lnt.characterization.records import Status

FS_HZ = 500_000.0
CARRIER_HZ = 30_000.0
RATE_HZ = 500.0
RECORD_SAMPLES = 100_000
BAND_LOW_HZ = 10_000.0
BAND_HIGH_HZ = 50_000.0
NYQUIST_FRACTION_MAX = 0.45
FILTER_ORDER = 4
MINIMUM_SNR_DB = 10.0
MAXIMUM_COMPONENTS = 1
ENVELOPE_FLOOR = 0.01
MAXIMUM_STORED = 4096
ANALYTIC_HALO_SAMPLES = 16_384
DECLARED_CODES = frozenset(
    {"multiple_components", "low_snr", "envelope_zero", "band_invalid", "phase_aliased"}
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
    band_low_hz: float = BAND_LOW_HZ
    band_high_hz: float = BAND_HIGH_HZ
    nyquist_fraction_max: float = NYQUIST_FRACTION_MAX
    filter_order: int = FILTER_ORDER
    minimum_snr_db: float = MINIMUM_SNR_DB
    maximum_components_in_band: int = MAXIMUM_COMPONENTS
    phase_increment_max_rad: float = math.pi
    envelope_zero_fraction_of_median: float = ENVELOPE_FLOOR
    maximum_stored_samples: int = MAXIMUM_STORED
    resources: ResourceLimits = field(default_factory=_resources)


def _evaluate(samples: np.ndarray, **overrides: object) -> F06Result:
    """Вызвать движок с объявленными гейтами и точечными переопределениями теста."""
    declared = replace(_Declared(), **overrides)
    return compute_f06_modulation_trajectories(
        samples,
        sample_rate_hz=declared.sample_rate_hz,
        band_low_hz=declared.band_low_hz,
        band_high_hz=declared.band_high_hz,
        nyquist_fraction_max=declared.nyquist_fraction_max,
        filter_order=declared.filter_order,
        minimum_snr_db=declared.minimum_snr_db,
        maximum_components_in_band=declared.maximum_components_in_band,
        phase_increment_max_rad=declared.phase_increment_max_rad,
        envelope_zero_fraction_of_median=declared.envelope_zero_fraction_of_median,
        maximum_stored_samples=declared.maximum_stored_samples,
        resources=declared.resources,
    )


def _am(depth: float, rate_hz: float = RATE_HZ, sample_count: int = RECORD_SAMPLES) -> np.ndarray:
    times = np.arange(sample_count) / FS_HZ
    carrier = np.cos(2 * np.pi * CARRIER_HZ * times)
    return (1.0 + depth * np.cos(2 * np.pi * rate_hz * times)) * carrier


def _fm(
    deviation_hz: float, rate_hz: float = RATE_HZ, sample_count: int = RECORD_SAMPLES
) -> np.ndarray:
    times = np.arange(sample_count) / FS_HZ
    phase = (deviation_hz / rate_hz) * np.sin(2 * np.pi * rate_hz * times)
    return np.cos(2 * np.pi * CARRIER_HZ * times + phase)


def _stored_times(result: F06Result) -> np.ndarray:
    return result.stored_indices.astype(np.float64) / FS_HZ


def test_method_is_the_declared_recipe_method() -> None:
    assert METHOD == "butterworth_hilbert_analytic_trajectory"


def test_am_envelope_recovers_declared_depth_within_pipeline_bound() -> None:
    result = _evaluate(_am(0.5))
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.components == 1
    assert result.snr_db is not None
    assert result.snr_db >= MINIMUM_SNR_DB
    expected = 1.0 + 0.5 * np.cos(2 * np.pi * RATE_HZ * _stored_times(result))
    error = float(np.max(np.abs(result.amplitudes_v - expected)))
    assert error <= 1e-3 * float(np.max(expected))


def test_am_instantaneous_frequency_stays_at_the_carrier() -> None:
    """Допуск — относительный пол потокового конвейера, а не абсолютная константа.

    Замерено: медиана ошибки 0.05 Гц, максимум 1.03 Гц = 3.4e-5 от несущей, и максимум
    сидит у концов чанков (аналитический сигнал считается независимыми окнами).
    Отсюда 1e-4 от несущей: втрое выше измеренного и в 5000 раз ниже темпа модуляции.
    """
    result = _evaluate(_am(0.5))
    assert float(np.max(np.abs(result.frequencies_hz - CARRIER_HZ))) <= 1e-4 * CARRIER_HZ


def test_fm_trajectory_recovers_declared_deviation() -> None:
    result = _evaluate(_fm(50.0))
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    times = _stored_times(result)
    expected = CARRIER_HZ + 50.0 * np.cos(2 * np.pi * RATE_HZ * times)
    assert float(np.max(np.abs(result.frequencies_hz - expected))) <= 1.0
    swing = float((np.max(result.frequencies_hz) - np.min(result.frequencies_hz)) / 2.0)
    assert swing == pytest.approx(50.0, rel=0.02)
    assert float(np.max(np.abs(result.amplitudes_v - 1.0))) <= 1e-3
    assert bool(np.all(np.diff(result.phases_rad) > 0.0))


def test_frozen_phase_increment_gate_holds_for_a_clamped_band() -> None:
    """Полоса ниже Найквиста по построению рецепта, поэтому pi не срабатывает."""
    result = _evaluate(_fm(50.0))
    assert "phase_aliased" not in result.reason_codes


def test_declared_lower_phase_increment_threshold_trips_phase_aliased() -> None:
    result = _evaluate(_fm(50.0), phase_increment_max_rad=0.1)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("phase_aliased",)
    assert result.stored_count == 0
    assert result.amplitudes_v.size == 0


def test_two_tones_in_band_trip_multiple_components() -> None:
    """Огибающая двух тонов модулируется разностной частотой внутри несущей полосы."""
    times = np.arange(RECORD_SAMPLES) / FS_HZ
    samples = np.cos(2 * np.pi * 20_000.0 * times) + np.cos(2 * np.pi * 32_000.0 * times)
    result = _evaluate(samples)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("multiple_components",)
    assert result.components is not None
    assert result.components > MAXIMUM_COMPONENTS
    assert result.stored_count == 0
    assert result.phases_rad.size == 0


def test_overmodulated_am_trips_envelope_zero() -> None:
    """Темп 20 Гц: полосовой фильтр обязан разрешить провал огибающей (см. F06-14b).

    При темпе 500 Гц касп провала заливается разрешением фильтра (наклон d*2*pi*fm,
    умноженный на 16 мкс), поэтому объявленный пол 0.01 медианы там недостижим.
    """
    result = _evaluate(_am(1.5, rate_hz=20.0))
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("envelope_zero",)
    assert result.stored_count == 0


def test_raised_declared_snr_threshold_trips_low_snr() -> None:
    """Малый шум нужен, чтобы внутриполосная медиана была строго положительной."""
    noise = np.random.default_rng(6022).standard_normal(RECORD_SAMPLES)
    result = _evaluate(_am(0.5) + 1e-6 * noise, minimum_snr_db=500.0)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("low_snr",)
    assert result.stored_count == 0


def test_band_above_nyquist_folds_into_band_invalid() -> None:
    result = _evaluate(_am(0.5), sample_rate_hz=20_000.0)
    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("band_invalid",)
    assert result.stored_count == 0
    assert result.snr_db is None


def test_nonfinite_tail_keeps_the_largest_contiguous_span() -> None:
    samples = _am(0.5)
    samples[-20_000:] = np.nan
    result = _evaluate(samples)
    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.stop_sample <= RECORD_SAMPLES - 20_000
    assert result.start_sample >= ANALYTIC_HALO_SAMPLES
    assert result.missing_count == RECORD_SAMPLES - (result.stop_sample - result.start_sample)
    expected = 1.0 + 0.5 * np.cos(2 * np.pi * RATE_HZ * _stored_times(result))
    error = float(np.max(np.abs(result.amplitudes_v - expected)))
    assert error <= 1e-3 * float(np.max(expected))


def test_stored_selection_is_evenly_spaced_over_the_record_and_bounded() -> None:
    """Селекция якорная по записи: конец спана не известен до конца единственного прохода.

    Объявленное правило `even_floor_index` берёт кандидатов `floor(k * N / M)` по всей
    записи, поэтому позиции известны заранее и проход остаётся однократным и ограниченным.
    Кандидаты вне поддержанного спана в траекторию не попадают и попадают в `missing_count`.
    """
    result = _evaluate(_am(0.5))
    span = result.stop_sample - result.start_sample
    assert result.observation_count == span
    assert result.missing_count == RECORD_SAMPLES - span
    assert result.stored_count == result.amplitudes_v.size
    assert result.stored_indices.size == result.stored_count
    assert result.frequencies_hz.size == result.stored_count
    assert result.phases_rad.size == result.stored_count
    candidates = np.floor(np.arange(MAXIMUM_STORED) * RECORD_SAMPLES / MAXIMUM_STORED).astype(
        np.int64
    )
    inside = candidates[(candidates >= result.start_sample) & (candidates < result.stop_sample)]
    assert np.array_equal(result.stored_indices, inside)
    assert 0 < result.stored_count <= MAXIMUM_STORED
    assert set(result.reason_codes) <= DECLARED_CODES
