"""Аналитические и инвариантные тесты движка F18 bicoherence triads."""

from __future__ import annotations

import functools
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits, StftSettings
from lnt.characterization.errors import CharacterizationError
from lnt.characterization.f18_contract import (
    ARTIFACT_LIMIT,
    CLAIM_BOUNDARY,
    DECLARED_CODES,
    IAAFT_NOT_CONVERGED,
    IAAFT_SURROGATE_COUNT,
    INSUFFICIENT_FRAMES,
    NO_SIGNIFICANT_TRIAD,
    PHASE_RANDOMIZED_SURROGATE_COUNT,
    PHASE_REFERENCE_UNAVAILABLE,
    SURROGATE_SEED,
    TRIAD_ABOVE_NYQUIST,
    TRIAD_OFF_GRID,
    ZERO_DENOMINATOR,
)
from lnt.characterization.f18_engine import compute_f18_bicoherence_triads
from lnt.characterization.f18_result import F18Declarations, F18Result
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Sequence

# 512 kHz: bin width 512000/4096 = 125 Hz, поэтому вся declared сетка 3..100 kHz
# попадает в exact FFT bins. 32 кадра — ровно locked minimum_frames, это самый
# дешёвый законный record для полного прогона 198 суррогатов.
_FS = 512_000.0
_SEGMENT = 4_096
_HOP = 2_048
_FRAMES = 32
_SAMPLES = _SEGMENT + (_FRAMES - 1) * _HOP

# Четыре объявленные квадратично связанные триады: 3000+5000, 10000+20000,
# 10000+50000 и 20000+50000. Их индексы в порядке declared_triads.
_COUPLED = {1: 0.7, 10: -0.4, 11: 1.1, 13: -1.6}
_COUPLING_INDICES = tuple(sorted(_COUPLED))


def _resources(max_surrogates: int = 199) -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=262_144,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=max_surrogates,
        deterministic_seed=SURROGATE_SEED,
    )


def _settings() -> StftSettings:
    return StftSettings(
        window="hann_periodic",
        segment_samples=_SEGMENT,
        overlap_fraction=0.5,
        detrend="constant",
        analysis_low_hz=3_000.0,
        analysis_high_hz=200_000.0,
        nyquist_fraction_max=0.45,
    )


def _phase(sample_rate_hz: float, sample_count: int) -> PhaseCycles:
    step = max(1, round(sample_rate_hz / 50.0))
    starts = np.arange(0, sample_count, step, dtype=np.float64)
    if starts.size < 2:
        starts = np.asarray([0.0, float(sample_count)], dtype=np.float64)
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


def _means(level: float = 0.0) -> PhaseMeans:
    return PhaseMeans(
        means_v=np.full(64, level, dtype=np.float64),
        counts=np.full(64, 1_024, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _coupled_record(sample_rate_hz: float, sample_count: int) -> np.ndarray:
    """Четыре locked-фазы связанных триад; f_j = f_1 + f_2 для каждой.

    Это declared analytic fixture метода-пояснения без добавок: чистая сумма
    синусоид, у которых f_j = f_1 + f_2 и все начальные фазы постоянны. Поэтому
    кадровый множитель 2*pi*f*n0/fs сокращается в B, b2 = 1 в точности, а biphase
    равен -phi. Шумовой пол здесь не нужен и был бы вреден: он опустил бы b2
    наблюдения чуть ниже 1, и суррогат без шума, у которого b2 насыщается единицей,
    выглядел бы «более связным», чем наблюдение.
    """
    t = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    record = np.zeros(sample_count, dtype=np.float64)
    for low_hz, high_hz, phi in ((3_000.0, 5_000.0, 0.7), (10_000.0, 20_000.0, -0.4)):
        record += np.cos(2.0 * np.pi * low_hz * t)
        record += np.cos(2.0 * np.pi * high_hz * t)
        record += 0.5 * np.cos(2.0 * np.pi * (low_hz + high_hz) * t + phi)
    record += np.cos(2.0 * np.pi * 50_000.0 * t)
    record += 0.5 * np.cos(2.0 * np.pi * 60_000.0 * t + 1.1)
    record += 0.5 * np.cos(2.0 * np.pi * 70_000.0 * t - 1.6)
    return record


@functools.lru_cache(maxsize=1)
def _coupled_runs() -> tuple[F18Result, F18Result]:
    """Два полных locked прогона: аналитика и bit-identical determinism."""
    samples = _coupled_record(_FS, _SAMPLES)
    phase = _phase(_FS, _SAMPLES)
    declarations = F18Declarations.locked()
    runs = tuple(
        compute_f18_bicoherence_triads(
            samples,
            phase,
            _means(),
            declarations,
            settings=_settings(),
            resources=_resources(),
        )
        for _ in range(2)
    )
    return runs[0], runs[1]


def _arrays(result: F18Result) -> Sequence[np.ndarray]:
    return (
        result.triad_low_hz,
        result.triad_high_hz,
        result.triad_sum_hz,
        result.bicoherence_squared,
        result.biphase_rad,
        result.phase_randomized_p_value,
        result.iaaft_p_value,
        result.dual_null_p_value,
        result.adjusted_p_value,
        result.frame_support,
    )


def test_locked_bicoherence_is_one_and_biphase_is_minus_phi_for_coupled_triads() -> None:
    """Для on-grid f1+f2 кадровые фазы сокращаются, B = N*c*e^{-i phi}, b2 = 1."""
    result, _ = _coupled_runs()
    coupled = np.asarray(_COUPLING_INDICES, dtype=np.int64)

    # Чистая сумма постоянно-фазовых синусоид на exact bins: b2 = 1 в точности,
    # biphase = arg(B) = -phi; единственная погрешность — округление float64.
    assert result.bicoherence_squared[coupled] == pytest.approx(1.0, abs=1e-9)
    expected_biphase = -np.asarray([_COUPLED[index] for index in _COUPLING_INDICES])
    assert result.biphase_rad[coupled] == pytest.approx(expected_biphase, abs=1e-9)
    assert result.triad_sum_hz[coupled].tolist() == [8_000.0, 30_000.0, 60_000.0, 70_000.0]
    assert bool(np.all(result.bicoherence_squared >= 0.0))
    assert bool(np.all(result.bicoherence_squared <= 1.0))


def test_coupled_triads_reach_the_add_one_floor_under_both_nulls() -> None:
    """0 превышений в каждой из 198 null => p = 1/100 и dual = max = 0.01."""
    result, _ = _coupled_runs()
    coupled = np.asarray(_COUPLING_INDICES, dtype=np.int64)

    assert result.phase_randomized_p_value[coupled].tolist() == [0.01] * 4
    assert result.iaaft_p_value[coupled].tolist() == [0.01] * 4
    assert result.dual_null_p_value[coupled].tolist() == [0.01] * 4
    assert bool(np.all(result.adjusted_p_value[coupled] <= 0.05))
    assert result.significant[coupled].tolist() == [True] * 4
    assert result.iaaft_converged_count == IAAFT_SURROGATE_COUNT


def test_dual_null_p_value_is_the_maximum_of_the_two_reported_p_values() -> None:
    """Locked maximum_add_one_p_value проверяется на всём объявленном домене."""
    result, _ = _coupled_runs()

    assert np.array_equal(
        result.dual_null_p_value,
        np.maximum(result.phase_randomized_p_value, result.iaaft_p_value),
        equal_nan=True,
    )
    assert bool(np.all(result.dual_null_p_value[(result.dual_null_p_value >= 0.01)] >= 0.01))


def test_coupled_run_measures_the_locked_frame_and_triad_domains() -> None:
    """32 кадра покрывают ровно 67584 отсчёта, сетка даёт все 15 триад."""
    result, _ = _coupled_runs()

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.frame_count == 32
    assert result.qualified_sample_count == _SAMPLES
    assert result.sample_count == _SAMPLES
    assert result.declared_triad_count == 15
    assert result.measurable_triad_count == 15
    assert bool(np.all(result.triad_available))
    assert result.frame_support.tolist() == [32] * 15
    assert int(result.significant.sum()) >= 4


def test_two_runs_on_the_same_input_are_bit_identical() -> None:
    """Declared seed даёт побайтово одинаковые массивы и учёт на двух прогонах."""
    first, second = _coupled_runs()

    assert first.status is second.status
    assert first.reason_codes == second.reason_codes
    assert first.declared_triad_count == second.declared_triad_count
    assert first.iaaft_converged_count == second.iaaft_converged_count
    for left, right in zip(_arrays(first), _arrays(second), strict=True):
        assert np.array_equal(left, right, equal_nan=True)


def test_uncoupled_triads_of_the_coupled_record_keep_the_declared_domain() -> None:
    """Свободные пары базовой сетки остаются в [0,1] и не обходят BH-решение."""
    result, _ = _coupled_runs()
    free = np.asarray([index for index in range(15) if index not in _COUPLED], dtype=np.int64)

    assert bool(np.all(result.bicoherence_squared[free] >= 0.0))
    assert bool(np.all(result.bicoherence_squared[free] <= 1.0))
    assert bool(np.all(result.dual_null_p_value[free] >= 0.01))
    assert int(result.significant.sum()) >= 4


def test_off_grid_capture_rate_is_unavailable_with_every_domain_empty() -> None:
    """48 MHz: шаг 11718.75 Hz, ни одна declared частота не exact bin."""
    samples = _coupled_record(48_000_000.0, _SAMPLES)

    result = compute_f18_bicoherence_triads(
        samples,
        _phase(48_000_000.0, _SAMPLES),
        _means(),
        F18Declarations.locked(),
        settings=_settings(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (TRIAD_OFF_GRID,)
    assert result.sample_count == _SAMPLES
    assert result.qualified_sample_count == 0
    assert result.frame_count == 0
    assert result.declared_triad_count == 0
    assert result.iaaft_converged_count == 0
    for array in _arrays(result):
        assert array.size == 0


def test_nyquist_clamp_reports_above_nyquist_before_off_grid() -> None:
    """100 kHz record: clamp 45 kHz, часть сумм объявлена above_nyquist."""
    result = compute_f18_bicoherence_triads(
        _coupled_record(100_000.0, _SAMPLES),
        _phase(100_000.0, _SAMPLES),
        _means(),
        F18Declarations.locked(),
        settings=replace(_settings(), analysis_low_hz=0.0),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (TRIAD_ABOVE_NYQUIST, TRIAD_OFF_GRID)
    assert result.declared_triad_count == 0


def test_thirty_one_frames_is_insufficient_and_publishes_no_domain() -> None:
    """31 кадр на один меньше locked minimum_frames = declared insufficient."""
    sample_count = _SEGMENT + 30 * _HOP

    result = compute_f18_bicoherence_triads(
        _coupled_record(_FS, sample_count),
        _phase(_FS, sample_count),
        _means(),
        F18Declarations.locked(),
        settings=_settings(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (INSUFFICIENT_FRAMES,)
    assert result.frame_count == 0
    assert result.qualified_sample_count == 0
    for array in _arrays(result):
        assert array.size == 0


def test_zero_residual_is_unavailable_with_zero_denominator() -> None:
    """Нулевой phase-residual не подменяется масштабом: declared zero_denominator."""
    result = compute_f18_bicoherence_triads(
        np.ones(_SAMPLES, dtype=np.float64),
        _phase(_FS, _SAMPLES),
        _means(level=1.0),
        F18Declarations.locked(),
        settings=_settings(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (ZERO_DENOMINATOR,)
    assert result.declared_triad_count == 0
    for array in _arrays(result):
        assert array.size == 0


@pytest.mark.parametrize("code", sorted(PHASE_ROOT_REASON_CODES))
def test_phase_root_codes_normalize_to_the_declared_f18_vocabulary(code: str) -> None:
    """Upstream phase-root code всегда становится phase_reference_unavailable."""
    phase = replace(_phase(_FS, _SAMPLES), status=Status.UNAVAILABLE, reason_code=code)

    result = compute_f18_bicoherence_triads(
        _coupled_record(_FS, _SAMPLES),
        phase,
        _means(),
        F18Declarations.locked(),
        settings=_settings(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert result.bicoherence_squared.size == 0
    assert result.dual_null_p_value.size == 0


def test_result_validator_rejects_unknown_codes_and_filled_unavailable_domains() -> None:
    """F18Result fail-closed проверяет vocabulary, пустые домены и built-инварианты."""
    unavailable = compute_f18_bicoherence_triads(
        _coupled_record(48_000_000.0, _SAMPLES),
        _phase(48_000_000.0, _SAMPLES),
        _means(),
        F18Declarations.locked(),
        settings=_settings(),
        resources=_resources(),
    )

    with pytest.raises(CharacterizationError):
        replace(unavailable, reason_codes=("invented",))
    with pytest.raises(CharacterizationError):
        replace(unavailable, bicoherence_squared=np.zeros(15, dtype=np.float64))
    with pytest.raises(CharacterizationError):
        replace(unavailable, reason_codes=())


def test_built_result_validator_is_not_looser_than_the_declared_minimum_frames() -> None:
    """Построенный результат обязан иметь >= minimum_frames и полный support."""
    result, _ = _coupled_runs()

    with pytest.raises(CharacterizationError):
        replace(result, frame_count=31, frame_support=np.full(15, 31, dtype=np.int64))
    with pytest.raises(CharacterizationError):
        replace(result, qualified_sample_count=result.qualified_sample_count - 1)
    with pytest.raises(CharacterizationError):
        replace(result, triad_available=np.zeros(15, dtype=np.bool_))
    with pytest.raises(CharacterizationError):
        replace(result, iaaft_converged_count=98)
    with pytest.raises(CharacterizationError):
        replace(result, bicoherence_squared=result.bicoherence_squared * 1.5)


@functools.lru_cache(maxsize=1)
def _noise_run() -> F18Result:
    """Один полный locked прогон на seeded noise: declared no_significant_triad."""
    noise = np.random.default_rng(SURROGATE_SEED).standard_normal(_SAMPLES)
    return compute_f18_bicoherence_triads(
        noise,
        _phase(_FS, _SAMPLES),
        _means(),
        F18Declarations.locked(),
        settings=_settings(),
        resources=_resources(),
    )


def test_no_significant_triad_code_is_published_as_an_explicit_state() -> None:
    """Seeded noise не даёт ни одной BH-значимой триады под обеими declared null."""
    result = _noise_run()

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (NO_SIGNIFICANT_TRIAD,)
    assert result.iaaft_converged_count == IAAFT_SURROGATE_COUNT
    assert result.declared_triad_count == 15
    assert bool(np.all(result.triad_available))
    assert not bool(np.any(result.significant))
    assert bool(np.all(np.isnan(result.biphase_rad)))
    # Ни одна триада не прошла BH: adjusted p строго выше q=0.05 для всех 15.
    assert bool(np.all(result.adjusted_p_value > 0.05))


def test_declarations_reject_any_alternate_recipe_surface() -> None:
    """Нельзя silently сменить surrogate count, seed, tolerance или правило триад."""
    for field, value in (
        ("phase_randomized_surrogate_count", 98),
        ("iaaft_surrogate_count", 98),
        ("iaaft_iterations", 99),
        ("surrogate_seed", 6021),
        ("false_discovery_rate", 0.1),
        ("triad_rule", "all_pairs"),
        ("dual_null_p_value", "minimum_add_one_p_value"),
    ):
        with pytest.raises(ValueError, match="locked recipe"):
            replace(F18Declarations.locked(), **{field: value})


def test_engine_validates_channel_phase_and_resource_contracts() -> None:
    """Finite channel, phase grid, resource caps и STFT band — trust boundary."""
    declarations = F18Declarations.locked()
    with pytest.raises(ValueError, match="finite"):
        compute_f18_bicoherence_triads(
            np.full(_SAMPLES, np.nan, dtype=np.float64),
            _phase(_FS, _SAMPLES),
            _means(),
            declarations,
            settings=_settings(),
            resources=_resources(),
        )
    with pytest.raises(ValueError, match="sample grid"):
        compute_f18_bicoherence_triads(
            _coupled_record(_FS, _SAMPLES),
            replace(_phase(_FS, _SAMPLES), sample_count=_SAMPLES - 1),
            _means(),
            declarations,
            settings=_settings(),
            resources=_resources(),
        )
    with pytest.raises(ValueError, match="surrogate"):
        compute_f18_bicoherence_triads(
            _coupled_record(_FS, _SAMPLES),
            _phase(_FS, _SAMPLES),
            _means(),
            declarations,
            settings=_settings(),
            resources=_resources(max_surrogates=PHASE_RANDOMIZED_SURROGATE_COUNT - 1),
        )
    with pytest.raises(ValueError, match="band"):
        compute_f18_bicoherence_triads(
            _coupled_record(_FS, _SAMPLES),
            _phase(_FS, _SAMPLES),
            _means(),
            declarations,
            settings=replace(_settings(), analysis_low_hz=10_000.0),
            resources=_resources(),
        )


def test_checkpoint_cancellation_propagates_by_identity() -> None:
    """Cancellation между surrogate passes не превращается в QC code."""
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as raised:
        compute_f18_bicoherence_triads(
            _coupled_record(_FS, _SAMPLES),
            _phase(_FS, _SAMPLES),
            _means(),
            F18Declarations.locked(),
            settings=_settings(),
            resources=_resources(),
            checkpoint=cancel,
        )

    assert raised.value is error


def test_claim_boundary_and_reason_vocabulary_cover_the_whole_family() -> None:
    """Claim boundary запрещает физический механизм, а словарь закрыт восемью кодами."""
    assert len(DECLARED_CODES) == 8
    assert len(set(DECLARED_CODES)) == 8
    assert IAAFT_NOT_CONVERGED in DECLARED_CODES
    assert ARTIFACT_LIMIT in DECLARED_CODES
    assert "physical mechanism" in CLAIM_BOUNDARY
    assert "coupling path" in CLAIM_BOUNDARY
