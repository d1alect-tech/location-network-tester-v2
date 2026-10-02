"""Аналитические тесты F18: триады, bicoherence, IAAFT и dual-null."""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from lnt.characterization.f18_contract import (
    ANALYSIS_HIGH_HZ,
    ARTIFACT_LIMIT,
    BASE_FREQUENCIES_HZ,
    BICOHERENCE_NAME,
    BIPHASE_NAME,
    CAUSCHY_SCHWARZ_SLACK,
    CLAIM_BOUNDARY,
    DECLARED_CODES,
    DUAL_NULL_COMBINATION,
    EXACT_BIN_RELATIVE_TOLERANCE,
    F18_ID,
    F18_INDEX,
    FALSE_DISCOVERY_RATE,
    FREQUENCY_MAPPING,
    IAAFT_ITERATIONS,
    IAAFT_NOT_CONVERGED,
    IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE,
    IAAFT_SURROGATE_COUNT,
    INSUFFICIENT_FRAMES,
    MAXIMUM_TRIADS,
    METHOD,
    MINIMUM_FRAMES,
    MULTIPLE_TESTING,
    NYQUIST_FRACTION_MAX,
    OVERLAP_FRACTION,
    PHASE_BINS,
    PHASE_RANDOMIZED_SURROGATE_COUNT,
    SEGMENT_DURATION_S,
    SPEC_GAPS,
    SURROGATE_EXCEEDANCE,
    SURROGATE_SEED,
    TRIAD_ABOVE_NYQUIST,
    TRIAD_OFF_GRID,
    TRIAD_RULE,
    WINDOW,
    ZERO_DENOMINATOR,
    segment_samples_for,
)
from lnt.characterization.f18_math import triad_bicoherence
from lnt.characterization.f18_result import F18Declarations
from lnt.characterization.f18_significance import (
    add_one_p_value,
    benjamini_hochberg,
    dual_null_p_value,
)
from lnt.characterization.f18_surrogate import (
    F18ZeroResidualError,
    iaaft_rank_remap,
    iaaft_surrogate,
    phase_randomized_surrogate,
)
from lnt.characterization.f18_triads import F18TriadGrid, build_triad_grid, declared_triads
from lnt.characterization.records import Unit, validate_unit_name

# Шаг решётки exact_fft_bins = fs / round(0.001 * fs): при объявленной длительности
# 1 мс он равен 1000 Hz — НОК базовых частот — на каждой частоте, чей миллисекундный
# сегмент делит fs нацело. _ON_GRID_FS = 1 024 000 даёт сегмент 1024 и шаг ровно 1000 Hz.
_ON_GRID_FS = 1_024_000.0
# 819.2 кГц: сегмент 819, шаг 1000.2442 Hz, поэтому 3000 Hz даёт бин 2.99927 и ни одна
# из пятнадцати declared триад не попадает в решётку.
_OFF_GRID_FS = 819_200.0
_DECLARED_FIELDS = frozenset(
    {
        "phase_bins",
        "segment_duration_s",
        "window",
        "overlap_fraction",
        "base_frequencies_hz",
        "triad_rule",
        "analysis_high_hz",
        "nyquist_fraction_max",
        "frequency_mapping",
        "maximum_triads",
        "phase_randomized_surrogate_count",
        "iaaft_surrogate_count",
        "iaaft_iterations",
        "iaaft_relative_rms_magnitude_tolerance",
        "surrogate_seed",
        "dual_null_p_value",
        "multiple_testing",
        "false_discovery_rate",
        "minimum_frames",
    }
)


def _grid(
    *,
    sample_rate_hz: float = _ON_GRID_FS,
    analysis_high_hz: float = ANALYSIS_HIGH_HZ,
    maximum_triads: int = MAXIMUM_TRIADS,
    base: tuple[float, ...] = BASE_FREQUENCIES_HZ,
    analysis_low_hz: float = 3000.0,
) -> F18TriadGrid:
    return build_triad_grid(
        base,
        segment_samples=segment_samples_for(sample_rate_hz),
        sample_rate_hz=sample_rate_hz,
        analysis_low_hz=analysis_low_hz,
        analysis_high_hz=analysis_high_hz,
        nyquist_fraction_max=NYQUIST_FRACTION_MAX,
        maximum_triads=maximum_triads,
    )


def test_locked_contract_recipe_and_claim_boundary_are_frozen() -> None:
    """Каждое locked recipe value F18 совпадает с источниками и не переопределено."""
    assert F18_ID == "f18_bicoherence_triads"
    assert F18_INDEX == 17
    assert METHOD == "declared_normalized_bicoherence_dual_surrogate"
    assert PHASE_BINS == 64
    assert SEGMENT_DURATION_S == 0.001
    assert WINDOW == "hann_periodic"
    assert OVERLAP_FRACTION == 0.5
    assert BASE_FREQUENCIES_HZ == (3000.0, 5000.0, 10000.0, 20000.0, 50000.0)
    assert TRIAD_RULE == "all_valid_unordered_base_frequency_pairs"
    assert ANALYSIS_HIGH_HZ == 200000.0
    assert NYQUIST_FRACTION_MAX == 0.45
    assert FREQUENCY_MAPPING == "exact_fft_bins"
    assert MAXIMUM_TRIADS == 4096
    assert PHASE_RANDOMIZED_SURROGATE_COUNT == 99
    assert IAAFT_SURROGATE_COUNT == 99
    assert IAAFT_ITERATIONS == 2
    assert IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE == 1e-6
    assert SURROGATE_SEED == 6022
    assert MULTIPLE_TESTING == "benjamini_hochberg"
    assert FALSE_DISCOVERY_RATE == 0.05
    assert MINIMUM_FRAMES == 32
    assert DECLARED_CODES == (
        "phase_reference_unavailable",
        "insufficient_frames",
        "triad_off_grid",
        "triad_above_nyquist",
        "zero_denominator",
        "iaaft_not_converged",
        "no_significant_triad",
        "artifact_limit",
    )
    assert (TRIAD_OFF_GRID, TRIAD_ABOVE_NYQUIST, ZERO_DENOMINATOR) == (
        "triad_off_grid",
        "triad_above_nyquist",
        "zero_denominator",
    )
    assert (INSUFFICIENT_FRAMES, IAAFT_NOT_CONVERGED, ARTIFACT_LIMIT) == (
        "insufficient_frames",
        "iaaft_not_converged",
        "artifact_limit",
    )
    assert SURROGATE_EXCEEDANCE == "surrogate_bicoherence_squared_strictly_above_observed"
    assert DUAL_NULL_COMBINATION == "maximum_of_two_add_one_p_values"
    assert "no calibration" in CLAIM_BOUNDARY
    assert "IEC 61000-4-30 compliance" in CLAIM_BOUNDARY
    assert "GUM-conformant" in CLAIM_BOUNDARY
    assert "unavailable is never fabricated" in CLAIM_BOUNDARY
    assert "phase-coupling" in CLAIM_BOUNDARY
    assert "causation" in CLAIM_BOUNDARY
    assert {gap[:5] for gap in SPEC_GAPS} == {
        "F18-1",
        "F18-2",
        "F18-3",
        "F18-4",
        "F18-5",
        "F18-6",
    }


def test_f18_declares_the_segment_as_a_duration_and_the_engine_derives_the_samples() -> None:
    """Сегмент объявлен длительностью; recipe не может нести частотозависимое число."""
    # Полный declared surface: переименование ровно одного поля, ничего не добавлено.
    assert {field.name for field in dataclasses.fields(F18Declarations)} == _DECLARED_FIELDS


def test_declared_duration_derives_the_sample_count_at_every_nominal_rate() -> None:
    """Отсчёты — функция частоты: 1 мс даёт ровно fs/1000 на каждом целом кГц."""
    duration_s = F18Declarations.locked().segment_duration_s

    assert duration_s == SEGMENT_DURATION_S
    assert segment_samples_for(1_000_000.0) == 1_000
    assert segment_samples_for(500_000.0) == 500
    assert segment_samples_for(512_000.0) == 512
    assert segment_samples_for(8_000_000.0) == 8_000
    # Округление объявленной длительности, а не усечение: 204 800 Гц даёт 205 отсчётов.
    assert segment_samples_for(204_800.0) == 205


def test_triad_rule_enumerates_every_unordered_base_pair_without_all_pairs() -> None:
    """Ровно 15 триад из 5 базовых частот: пары f1<=f2, а не полный перебор."""
    triads = declared_triads(BASE_FREQUENCIES_HZ, MAXIMUM_TRIADS)

    assert len(triads) == 15
    assert triads[1] == (3000.0, 5000.0, 8000.0)
    assert triads[10] == (10000.0, 20000.0, 30000.0)
    assert triads[11] == (10000.0, 50000.0, 60000.0)
    assert triads[13] == (20000.0, 50000.0, 70000.0)
    assert all(low <= high for low, high, _ in triads)
    declared = set(BASE_FREQUENCIES_HZ)
    assert all(low in declared and high in declared for low, high, _ in triads)
    assert all(math.isclose(total, low + high, abs_tol=0.0) for low, high, total in triads)
    assert len(set(triads)) == 15


def test_exact_fft_bins_are_accepted_only_on_the_declared_capture_rates() -> None:
    """819.2 кГц даёт бин 2.99927 и объявлен off_grid; 1.024 МГц меряет все 15."""
    on_grid = _grid()
    off_grid = _grid(sample_rate_hz=_OFF_GRID_FS)

    assert bool(np.all(on_grid.measurable))
    assert on_grid.off_grid_count == 0
    assert on_grid.above_nyquist_count == 0
    assert on_grid.declared_count == 15
    # 3000 Hz / 1000.2442 Hz = 2.99927 — ни одна частота сетки не попадает в бин.
    assert off_grid.off_grid_count == 15
    assert int(np.count_nonzero(off_grid.measurable)) == 0
    assert math.isclose(on_grid.effective_high_hz, 200_000.0)
    assert EXACT_BIN_RELATIVE_TOLERANCE < 1e-6


def test_nyquist_clamp_is_applied_before_the_exact_bin_rule() -> None:
    """Сумма выше clamp — declared above_nyquist, даже когда бин был бы exact."""
    grid = _grid(sample_rate_hz=1_024_000.0, analysis_high_hz=25_000.0)

    assert math.isclose(grid.effective_high_hz, 25_000.0)
    assert grid.above_nyquist_count == 7
    assert grid.off_grid_count == 0
    assert int(np.count_nonzero(grid.measurable)) == 8
    # Суммы <= 25 kHz: 6, 8, 13, 23, 10, 15, 25, 20 кГц — triads 0,1,2,3,5,6,7,9.
    assert np.flatnonzero(grid.measurable).tolist() == [0, 1, 2, 3, 5, 6, 7, 9]


def test_maximum_triads_is_a_count_cap_that_reports_instead_of_hiding() -> None:
    """Кап режет ЧИСЛО триад и всегда говорит об отброшенном declared content."""
    base = tuple(float(1_000 * step) for step in range(1, 13))
    grid = _grid(sample_rate_hz=4_096_000.0, maximum_triads=10, base=base, analysis_low_hz=0.0)

    assert len(declared_triads(base, 10)) == 10
    assert len(declared_triads(base, 4_096)) == 78
    assert grid.declared_count == 10
    assert grid.dropped_count == 68
    assert grid.low_hz.size == 10
    assert grid.off_grid_count == 0


def test_single_frame_bicoherence_is_exactly_one_and_its_phase_is_argument() -> None:
    """Один кадр: B = a*b*conj(c), |B|² = |a b|²|c|², поэтому b2 = 1 в точности."""
    coefficients = np.asarray([[2.0 + 0.0j], [3.0 + 0.0j], [1.0 + 1.0j]], dtype=np.complex128)

    measured = triad_bicoherence(coefficients, np.asarray([[0, 1, 2]], dtype=np.int64))

    assert float(measured.bicoherence_squared[0]) == 1.0
    # arg((2)(3)conj(1+i)) = -pi/4
    assert float(np.angle(measured.bispectrum[0])) == pytest.approx(-math.pi / 4.0, abs=1e-12)
    assert float(measured.denominator[0]) == pytest.approx(72.0)


def test_cauchy_schwarz_bounds_every_hand_built_bicoherence_inside_zero_one() -> None:
    """|B|² <= sum|ab|² * sum|c|² всегда, поэтому объявленный домен — [0, 1]."""
    rng = np.random.default_rng(SURROGATE_SEED)
    coefficients = rng.standard_normal((6, 32)) + 1j * rng.standard_normal((6, 32))
    rows = np.asarray([[0, 1, 2], [3, 4, 5], [1, 1, 3]], dtype=np.int64)

    measured = triad_bicoherence(coefficients, rows)

    squared = np.abs(measured.bispectrum) ** 2
    assert bool(np.all(squared <= measured.denominator * (1.0 + CAUSCHY_SCHWARZ_SLACK)))
    assert bool(np.all(measured.bicoherence_squared >= 0.0))
    assert bool(np.all(measured.bicoherence_squared <= 1.0))


def test_mirror_frame_phases_give_exactly_one_over_nine_bicoherence() -> None:
    """Три кадра с фазами 0, ±pi/4: B = 1 + 2cos(pi) = -1, den = 3*3 = 9, b2 = 1/9."""
    phases = np.asarray([0.0, math.pi / 4.0, -math.pi / 4.0])
    coefficients = np.asarray(
        [np.exp(1j * phases), np.exp(2j * phases), np.exp(-1j * phases)], dtype=np.complex128
    )

    measured = triad_bicoherence(coefficients, np.asarray([[0, 1, 2]], dtype=np.int64))

    assert abs(complex(measured.bispectrum[0])) == pytest.approx(1.0, abs=1e-12)
    assert float(measured.denominator[0]) == pytest.approx(9.0)
    assert float(measured.bicoherence_squared[0]) == pytest.approx(1.0 / 9.0, abs=1e-15)


def test_independent_frame_phases_have_mean_bicoherence_one_over_frames() -> None:
    """E[b2] = 1/M при независимых фазах; проверяем по 200 seed-репликам."""
    frames = 32
    replicates = 200
    rng = np.random.default_rng(SURROGATE_SEED)
    values = np.empty(replicates, dtype=np.float64)
    for index in range(replicates):
        phases = rng.uniform(0.0, 2.0 * math.pi, size=frames)
        coefficients = np.asarray(
            [np.exp(1j * phases), np.exp(2j * phases), np.exp(-1j * phases)], dtype=np.complex128
        )
        measured = triad_bicoherence(coefficients, np.asarray([[0, 1, 2]], dtype=np.int64))
        values[index] = measured.bicoherence_squared[0]

    # |B|² = |sum e^{4i phi}| — случайное блуждание из M единичных шагов.
    # E[|B|²] = M и E[|B|⁴] = 2M² - M, поэтому
    #   Var(|B|²) = (2M² - M) - M² = M(M - 1),
    # а не M(2M - 1): четвёртый момент сам по себе дисперсией не является.
    # den = M² точно (все модули единичные), значит E[b2] = 1/M и
    #   sigma[b2] = sqrt(M(M-1))/M² = sqrt(M-1)/M^(3/2),
    # а среднее по R репликам имеет ошибку sigma/sqrt(R).
    expected = 1.0 / frames
    sigma = math.sqrt(frames - 1) / frames**1.5
    assert abs(float(values.mean()) - expected) <= 3.0 * sigma / math.sqrt(replicates)
    # Максимум по репликам 5-сигма границей не ограничить: |B|² скошено
    # (P(|B|² > x) ~ exp(-x/M)), поэтому здесь только точный объявленный
    # домен b2 <= 1 из неравенства Коши–Буняковского.
    assert float(values.max()) <= 1.0


def test_iaaft_preserves_both_the_amplitude_multiset_and_the_fourier_magnitudes() -> None:
    """Rank remap сохраняет амплитуды, magnitude replacement — спектр; оба точны."""
    residual = np.random.default_rng(11).standard_normal(4_096)
    residual[100] += 25.0

    surrogate, error = iaaft_surrogate(
        residual,
        rng=np.random.default_rng([SURROGATE_SEED, 1]),
        iterations=IAAFT_ITERATIONS,
        tolerance=IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE,
    )

    # Rank remap — declared amplitude step: он кладёт observed значения на позиции,
    # отсортированные по |y|, поэтому набор значений совпадает побитово.
    assert np.array_equal(np.sort(iaaft_rank_remap(surrogate, residual)), np.sort(residual))
    # Последний declared шаг итерации — magnitude replacement, поэтому выданный
    # суррогат несёт observed спектр: это и проверяет declared tolerance.
    observed = np.abs(np.fft.rfft(residual))
    assert np.allclose(np.abs(np.fft.rfft(surrogate)), observed, rtol=1e-9, atol=1e-9)
    assert error <= IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE


def test_iaaft_and_phase_randomized_nulls_are_deterministic_from_the_declared_seed() -> None:
    """Один declared seed, два явных потока, ноль глобального numpy random state."""
    residual = np.random.default_rng(12).standard_normal(2_048)
    options: dict[str, int | float] = {"iterations": 3, "tolerance": 1e-6}

    first = phase_randomized_surrogate(residual, rng=np.random.default_rng([SURROGATE_SEED, 0]))
    again = phase_randomized_surrogate(residual, rng=np.random.default_rng([SURROGATE_SEED, 0]))
    other = phase_randomized_surrogate(residual, rng=np.random.default_rng([SURROGATE_SEED, 1]))
    iaaft_first, _ = iaaft_surrogate(
        residual,
        rng=np.random.default_rng([SURROGATE_SEED, 1]),
        iterations=int(options["iterations"]),
        tolerance=float(options["tolerance"]),
    )
    iaaft_again, _ = iaaft_surrogate(
        residual,
        rng=np.random.default_rng([SURROGATE_SEED, 1]),
        iterations=int(options["iterations"]),
        tolerance=float(options["tolerance"]),
    )

    assert np.array_equal(first, again)
    assert not np.array_equal(first, other)
    assert np.array_equal(iaaft_first, iaaft_again)
    # Оба null сохраняют record FFT magnitudes: в том числе DC и Nyquist, которые у
    # вещественного сигнала вещественны и не несут случайной фазы.
    assert np.allclose(np.abs(np.fft.rfft(first)), np.abs(np.fft.rfft(residual)))
    assert not np.array_equal(first, residual)


def test_iaaft_rejects_a_zero_residual_instead_of_fabricating_a_spectrum() -> None:
    """Нулевой остаток не имеет спектра для IAAFT и обязан быть явным отказом."""
    with pytest.raises(F18ZeroResidualError):
        iaaft_surrogate(
            np.zeros(1_024, dtype=np.float64),
            rng=np.random.default_rng([SURROGATE_SEED, 1]),
            iterations=IAAFT_ITERATIONS,
            tolerance=IAAFT_RELATIVE_RMS_MAGNITUDE_TOLERANCE,
        )


def test_dual_null_p_value_is_the_maximum_of_two_add_one_p_values() -> None:
    """(1+k)/100 для каждой null; dual = max — ровно locked maximum_add_one_p_value."""
    phase_p = add_one_p_value(
        np.asarray([0, 5, 40, 99], dtype=np.int64), PHASE_RANDOMIZED_SURROGATE_COUNT
    )
    iaaft_p = add_one_p_value(np.asarray([0, 2, 40, 3], dtype=np.int64), IAAFT_SURROGATE_COUNT)
    dual = dual_null_p_value(phase_p, iaaft_p)

    assert phase_p.tolist() == [0.01, 0.06, 0.41, 1.0]
    assert iaaft_p.tolist() == [0.01, 0.03, 0.41, 0.04]
    assert dual.tolist() == [0.01, 0.06, 0.41, 1.0]


def test_benjamini_hochberg_is_one_step_up_pass_over_the_candidate_family() -> None:
    """Один проход; при m=8, q=0.05 подъём доходит до p=0.02 на i=5 и там stop."""
    p_values = np.asarray([0.01, 0.01, 0.01, 0.01, 0.02, 0.05, 0.5, 0.9])

    adjusted, significant = benjamini_hochberg(p_values, FALSE_DISCOVERY_RATE)

    assert significant.tolist() == [True, True, True, True, True, False, False, False]
    assert adjusted[:4].tolist() == pytest.approx([0.02, 0.02, 0.02, 0.02])
    assert adjusted[4] == pytest.approx(0.032)
    assert adjusted[5] == pytest.approx(0.05 * 8 / 6)
    assert adjusted[6] == pytest.approx(0.5 * 8 / 7)
    assert adjusted[7] == pytest.approx(0.9)
    assert np.all(adjusted <= 1.0)


def test_benjamini_hochberg_floor_needs_three_triads_at_the_add_one_minimum() -> None:
    """При m=15, q=0.05, p=0.01: i=3 — ровно порог, i=4 даёт запас 0.0125."""
    minimum = np.full(15, 1.0)
    minimum[:3] = 0.01
    _, significant = benjamini_hochberg(minimum, FALSE_DISCOVERY_RATE)
    minimum[:4] = 0.01
    _, comfortable = benjamini_hochberg(minimum, FALSE_DISCOVERY_RATE)

    assert int(significant.sum()) == 3
    assert int(comfortable.sum()) == 4


def test_persisted_quantity_names_carry_their_declared_unit_suffix() -> None:
    """Имена persisted quantities F18 — с суффиксами Unit (ratio без суффикса)."""
    validate_unit_name(BICOHERENCE_NAME, Unit.RATIO)
    validate_unit_name(BIPHASE_NAME, Unit.RAD)
    assert BICOHERENCE_NAME == "f18_bicoherence_squared"
    assert BIPHASE_NAME == "f18_biphase_rad"
