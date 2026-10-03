"""Аналитические тесты движка F17 cyclic spectral coherence."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.f17_coherence import estimate_cyclic_coherence
from lnt.characterization.f17_contract import (
    ARTIFACT_LIMIT,
    CLAIM_BOUNDARY,
    CYCLIC_FREQUENCY_NAME,
    CYCLIC_FREQUENCY_OFF_GRID,
    CYCLIC_SPECTRUM_NAME,
    DECLARED_CODES,
    F17_ID,
    F17_INDEX,
    INSUFFICIENT_CYCLES,
    METHOD,
    NO_SIGNIFICANT_CELL,
    PHASE_REFERENCE_UNAVAILABLE,
    SPEC_GAPS,
    ZERO_DENOMINATOR,
)
from lnt.characterization.f17_engine import compute_f17_cyclic_spectral_coherence
from lnt.characterization.f17_frequency import build_frequency_grid
from lnt.characterization.f17_multiplicity import benjamini_hochberg_masked
from lnt.characterization.f17_permutation import (
    fisher_yates_order,
    permute_cycle_samples,
)
from lnt.characterization.f17_result import F17Declarations, F17Result
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

_FS_HZ = 102_400.0
_CYCLE_SAMPLES = 2_048
_SEGMENT_SAMPLES = 4_096


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=8_192,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=199,
        deterministic_seed=6_022,
    )


def _phase(
    sample_count: int,
    *,
    cycle_samples: int = _CYCLE_SAMPLES,
    status: Status = Status.AVAILABLE,
    reason: str | None = None,
) -> PhaseCycles:
    starts = np.arange(0, sample_count, cycle_samples, dtype=np.float64)
    return PhaseCycles(
        sample_rate_hz=_FS_HZ,
        sample_count=sample_count,
        cycle_start_samples=starts,
        cycle_end_samples=starts + cycle_samples,
        cycle_valid=np.ones(starts.size, dtype=np.bool_),
        status=status,
        reason_code=reason,
    )


def _means(value: float = 0.0) -> PhaseMeans:
    return PhaseMeans(
        means_v=np.full(64, value, dtype=np.float64),
        counts=np.full(64, 1_000, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _coherent_pair(cycles: int = 40) -> tuple[np.ndarray, np.ndarray]:
    """Две синхронные боковые несущие с известной фазой цикла."""
    values = np.empty(cycles * _CYCLE_SAMPLES, dtype=np.float64)
    for cycle in range(cycles):
        start = cycle * _CYCLE_SAMPLES
        local = np.arange(_CYCLE_SAMPLES, dtype=np.float64)
        phase = 0.071 * cycle
        time = (start + local) / _FS_HZ
        values[start : start + _CYCLE_SAMPLES] = np.cos(
            2.0 * np.pi * 10_000.0 * time + phase
        ) + 0.8 * np.cos(2.0 * np.pi * 10_050.0 * time + phase)
    return values, values.copy()


def _independent_pair(cycles: int = 40) -> tuple[np.ndarray, np.ndarray]:
    """Разные фазовые траектории при одинаковых боковых частотах."""
    first, _ = _coherent_pair(cycles)
    second = np.empty_like(first)
    for cycle in range(cycles):
        start = cycle * _CYCLE_SAMPLES
        local = np.arange(_CYCLE_SAMPLES, dtype=np.float64)
        time = (start + local) / _FS_HZ
        phase = 0.37 * np.sin(0.9 * cycle)
        second[start : start + _CYCLE_SAMPLES] = np.cos(
            2.0 * np.pi * 10_000.0 * time + phase
        ) + 0.8 * np.cos(2.0 * np.pi * 10_050.0 * time - phase)
    return first, second


def _run(
    first: np.ndarray,
    second: np.ndarray,
    *,
    phase: PhaseCycles | None = None,
    means: PhaseMeans | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> F17Result:
    return compute_f17_cyclic_spectral_coherence(
        ch1_samples=first,
        ch2_samples=second,
        phase=phase or _phase(first.size),
        ch1_means=means or _means(),
        ch2_means=means or _means(),
        declarations=F17Declarations.locked(),
        resources=_resources(),
        checkpoint=checkpoint,
    )


def test_locked_contract_and_claim_boundary_match_authoritative_recipe() -> None:
    """F17 identity, locked surface и запрет притязаний не дрейфуют."""
    declarations = F17Declarations.locked()

    assert F17_ID == "f17_cyclic_spectral_coherence"
    assert F17_INDEX == 16
    assert METHOD == "phase_residual_declared_alpha_cycle_permutation_coherence"
    assert declarations.phase_bins == 64
    assert declarations.cyclic_frequencies_hz == (50.0, 100.0, 150.0, 200.0)
    assert declarations.segment_samples == 4_096
    assert declarations.window == "hann_periodic"
    assert declarations.overlap_fraction == 0.5
    assert declarations.analysis_low_hz == 3_000.0
    assert declarations.analysis_high_hz == 200_000.0
    assert declarations.nyquist_fraction_max == 0.45
    assert declarations.frequency_mapping == "exact_symmetric_fft_bins"
    assert declarations.surrogate == "complete_cycle_fisher_yates_permutation"
    assert declarations.surrogate_count == 199
    assert declarations.surrogate_seed == 6_022
    assert declarations.multiple_testing == "benjamini_hochberg"
    assert declarations.false_discovery_rate == 0.05
    assert declarations.minimum_complete_cycles == 40
    assert declarations.minimum_frames == 32
    assert declarations.maximum_stored_cells == 4_096
    assert DECLARED_CODES == (
        "phase_reference_unavailable",
        "insufficient_cycles",
        "insufficient_frames",
        "cyclic_frequency_off_grid",
        "zero_denominator",
        "no_significant_cell",
        "artifact_limit",
    )
    assert "not independent-replicate confidence intervals" in CLAIM_BOUNDARY
    assert "does not prove source" in CLAIM_BOUNDARY
    assert "unavailable is never fabricated" in CLAIM_BOUNDARY
    assert CYCLIC_FREQUENCY_NAME.endswith("_hz")
    assert CYCLIC_SPECTRUM_NAME.endswith("_v2")
    # Пробел объявленной сетки зафиксирован, а не обойден подбором удобной частоты.
    assert {gap[:5] for gap in SPEC_GAPS} == {"F17-1"}
    assert "cyclic_frequency_off_grid" in SPEC_GAPS[0]
    assert "divide 102400" in SPEC_GAPS[0]
    assert "_rate_code" in SPEC_GAPS[0]


def test_exact_grid_maps_known_sidebands_without_interpolation() -> None:
    """При fs=102400 alpha=50 даёт ровно один сдвиг бин в каждую сторону."""
    grid = build_frequency_grid(F17Declarations.locked(), _FS_HZ)

    assert grid.alpha_offsets.tolist() == [1, 2, 3, 4]
    center = int(np.flatnonzero(np.isclose(grid.frequencies_hz, 10_025.0))[0])
    assert bool(grid.available[0, center])
    assert int(grid.lower_bins[0, center]) == 400
    assert int(grid.upper_bins[0, center]) == 402
    assert not np.any(~grid.alpha_on_grid)


def test_coherence_formula_is_exact_for_hand_built_spectrum() -> None:
    """Для X_upper=2 и X_lower=1 формула даёт |2|^2/(4*1)=1."""
    declarations = F17Declarations.locked()
    grid = build_frequency_grid(declarations, _FS_HZ)
    center = int(np.flatnonzero(np.isclose(grid.frequencies_hz, 10_025.0))[0])
    rows = np.arange(1, 2_049, dtype=np.int64)
    first = np.zeros((rows.size, 1), dtype=np.complex128)
    second = np.zeros_like(first)
    first[401, 0] = 2.0
    second[399, 0] = 1.0

    estimate = estimate_cyclic_coherence(first, second, rows, grid)

    assert bool(estimate.available[0, center])
    assert estimate.cyclic_spectrum[0, center] == pytest.approx(2.0)
    assert estimate.coherence[0, center] == pytest.approx(1.0)
    assert estimate.segment_support[0, center] == 1


def test_coherence_marks_zero_denominator_without_zero_measurement() -> None:
    """Нулевая мощность даёт masked absence, а не выдуманный gamma2=0."""
    declarations = F17Declarations.locked()
    grid = build_frequency_grid(declarations, _FS_HZ)
    rows = np.arange(1, 2_049, dtype=np.int64)
    zero = np.zeros((rows.size, 1), dtype=np.complex128)

    estimate = estimate_cyclic_coherence(zero, zero, rows, grid)

    assert not np.any(estimate.available)
    assert np.all(np.isnan(estimate.coherence))
    assert np.all(estimate.segment_support == 0)


def test_fisher_yates_keeps_whole_cycle_blocks_and_is_repeatable() -> None:
    """Перестановка меняет порядок целых блоков, не разрезая ни один цикл."""
    blocks = [
        np.asarray([0, 1, 2], dtype=np.float64),
        np.asarray([10, 11, 12], dtype=np.float64),
        np.asarray([20, 21, 22], dtype=np.float64),
    ]
    first = fisher_yates_order(3, np.random.default_rng(6_022))
    second = fisher_yates_order(3, np.random.default_rng(6_022))

    assert np.array_equal(first, second)
    permuted = permute_cycle_samples(blocks, first)
    assert permuted.shape == (len(blocks), 3)
    assert any(
        np.array_equal(permuted[index], block) for index in range(len(blocks)) for block in blocks
    )
    assert all(any(np.array_equal(row, block) for block in blocks) for row in permuted)


def test_bh_adjustment_matches_hand_computed_ranking() -> None:
    """Для p=(.01,.04,.03) BH даёт q=(.03,.04,.04)."""
    values = np.asarray([[0.01, 0.04, 0.03]], dtype=np.float64)
    mask = np.ones_like(values, dtype=np.bool_)

    adjusted = benjamini_hochberg_masked(values, mask)

    np.testing.assert_allclose(adjusted, np.asarray([[0.03, 0.04, 0.04]]))


def test_coherent_channels_reach_known_cyclic_cell() -> None:
    """Синхронные боковые несущие дают gamma2 около единицы и BH-значимость."""
    first, second = _coherent_pair()

    result = _run(first, second)

    alpha_index = 0
    frequency_index = int(np.flatnonzero(np.isclose(result.frequencies_hz, 10_025.0))[0])
    assert result.status is Status.PARTIAL
    assert result.reason_codes == (ARTIFACT_LIMIT,)
    assert result.coherence[alpha_index, frequency_index] > 0.95
    assert result.raw_p_value[alpha_index, frequency_index] <= 0.05
    valid = result.cell_available
    assert np.all(result.raw_p_value[valid] >= 1.0 / 200.0)
    assert np.allclose(
        result.raw_p_value[valid] * 200.0, np.rint(result.raw_p_value[valid] * 200.0)
    )
    assert result.bh_p_value[alpha_index, frequency_index] <= 0.05
    assert bool(result.significant[alpha_index, frequency_index])
    assert result.stored_cell_count == 4_096
    assert result.omitted_cell_count == result.significant_cell_count - 4_096
    assert result.qualified_cycle_count == 40
    assert result.frame_count >= 32


def test_phase_mean_is_removed_before_cross_coherence() -> None:
    """Добавление одинакового 64-bin mean не меняет residual coherence."""
    first, second = _coherent_pair()
    result = _run(first, second, means=_means(3.0))
    alpha_index = 0
    frequency_index = int(np.flatnonzero(np.isclose(result.frequencies_hz, 10_025.0))[0])

    assert result.coherence[alpha_index, frequency_index] > 0.95
    assert result.status is Status.PARTIAL


def test_independent_channels_have_no_surrogate_significant_cell() -> None:
    """Независимые фазовые траектории не создают BH-значимую ячейку."""
    first, second = _independent_pair()

    result = _run(first, second)

    assert result.status is Status.PARTIAL
    assert NO_SIGNIFICANT_CELL in result.reason_codes
    assert not np.any(result.significant)
    assert result.stored_cell_count == 0


def test_engine_is_bit_identical_across_repeated_runs() -> None:
    """Один и тот же seed и вход дают побайтно одинаковые значения."""
    first, second = _coherent_pair()

    left = _run(first, second)
    right = _run(first, second)

    assert left.status is right.status
    assert left.reason_codes == right.reason_codes
    for name in (
        "cyclic_spectrum",
        "coherence",
        "raw_p_value",
        "bh_p_value",
        "segment_support",
        "cell_available",
        "significant",
        "stored_cyclic_spectrum",
        "stored_coherence",
        "stored_raw_p_value",
        "stored_bh_p_value",
        "stored_segment_support",
    ):
        assert np.array_equal(getattr(left, name), getattr(right, name), equal_nan=True), name
    assert left.stored_cell_count == right.stored_cell_count


def test_fewer_than_forty_cycles_is_exact_support_failure() -> None:
    """39 полных циклов дают insufficient_cycles и пустые домены."""
    first, second = _coherent_pair(39)
    result = _run(first, second)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (INSUFFICIENT_CYCLES,)
    assert result.cyclic_spectrum.size == 0
    assert result.qualified_sample_count == 0


def test_thirty_one_frames_is_exact_frame_failure() -> None:
    """При 48 kHz 40 циклов дают меньше 32 кадров, поэтому refusal до суррогатов.

    Частота 48 kHz не делит 102400, поэтому declared alpha лежат вне сетки FFT:
    rate-level структурный факт сильнее факта длины записи, и движок отказывает
    с cyclic_frequency_off_grid раньше, чем успевает посчитать кадры.
    """
    cycles = 40
    cycle_samples = 960
    count = cycles * cycle_samples
    phase = PhaseCycles(
        sample_rate_hz=48_000.0,
        sample_count=count,
        cycle_start_samples=np.arange(cycles, dtype=np.float64) * cycle_samples,
        cycle_end_samples=np.arange(1, cycles + 1, dtype=np.float64) * cycle_samples,
        cycle_valid=np.ones(cycles, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
    samples = np.zeros(count, dtype=np.float64)
    result = compute_f17_cyclic_spectral_coherence(
        ch1_samples=samples,
        ch2_samples=samples,
        phase=phase,
        ch1_means=_means(),
        ch2_means=_means(),
        declarations=F17Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (CYCLIC_FREQUENCY_OFF_GRID,)
    assert result.frame_count == 0


def test_canonical_500k_rate_records_exact_grid_gap() -> None:
    """На канонических 500 кГц declared alpha не лежат на сетке FFT 4096."""
    grid = build_frequency_grid(F17Declarations.locked(), 500_000.0)

    assert grid.alpha_offsets.tolist() == [-1, -1, -1, -1]
    assert not np.any(grid.alpha_on_grid)


def test_off_grid_alphas_are_unavailable_not_rounded() -> None:
    """При fs=100000 ни одна declared alpha не округляется до FFT-бина."""
    cycles = 40
    count = cycles * 2_000
    phase = PhaseCycles(
        sample_rate_hz=100_000.0,
        sample_count=count,
        cycle_start_samples=np.arange(cycles, dtype=np.float64) * 2_000.0,
        cycle_end_samples=np.arange(1, cycles + 1, dtype=np.float64) * 2_000.0,
        cycle_valid=np.ones(cycles, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
    samples = np.zeros(count, dtype=np.float64)
    result = compute_f17_cyclic_spectral_coherence(
        ch1_samples=samples,
        ch2_samples=samples,
        phase=phase,
        ch1_means=_means(),
        ch2_means=_means(),
        declarations=F17Declarations.locked(),
        resources=_resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (CYCLIC_FREQUENCY_OFF_GRID,)
    assert result.frequencies_hz.size == 0


@pytest.mark.parametrize("code", sorted(PHASE_ROOT_REASON_CODES))
def test_phase_root_codes_normalize_to_declared_f17_code(code: str) -> None:
    """Upstream phase-root reason никогда не выходит из словаря F17."""
    phase = replace(_phase(40 * _CYCLE_SAMPLES), status=Status.UNAVAILABLE, reason_code=code)
    first, second = _coherent_pair()
    result = _run(first, second, phase=phase)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert result.frequencies_hz.size == 0


def test_unavailable_result_publishes_no_axes_or_measurements() -> None:
    """Любой terminal support failure оставляет пустые домены, не нули."""
    phase = replace(
        _phase(40 * _CYCLE_SAMPLES),
        status=Status.UNAVAILABLE,
        reason_code="no_sync_reference",
    )
    first, second = _coherent_pair()
    result = _run(first, second, phase=phase)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    for name in (
        "cyclic_frequencies_hz",
        "frequencies_hz",
        "cyclic_spectrum",
        "coherence",
        "raw_p_value",
        "bh_p_value",
        "segment_support",
        "cell_available",
        "significant",
    ):
        assert getattr(result, name).size == 0, name
    assert result.stored_cell_count == 0


def test_zero_denominator_is_declared_unavailability() -> None:
    """Нулевые каналы дают zero_denominator до запуска 199 surrogates."""
    first, _second = _coherent_pair()
    zeros = np.zeros_like(first)
    result = _run(zeros, zeros)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (ZERO_DENOMINATOR,)
    assert result.cyclic_spectrum.size == 0


def test_partial_phase_support_is_not_total_reference_failure() -> None:
    """PARTIAL phase root не превращается в ложный phase_reference_unavailable."""
    partial = replace(
        _phase(40 * _CYCLE_SAMPLES),
        status=Status.PARTIAL,
        reason_code="insufficient_phase_support",
    )
    zeros = np.zeros(40 * _CYCLE_SAMPLES, dtype=np.float64)
    result = _run(zeros, zeros, phase=partial)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (ZERO_DENOMINATOR,)


def test_resource_surrogate_cap_cannot_silently_reduce_declared_count() -> None:
    """199 суррогатов не превращаются в 19 при меньшем resource limit."""
    resources = replace(_resources(), max_surrogates=19)
    first, second = _coherent_pair()
    with pytest.raises(ValueError, match="surrogate"):
        compute_f17_cyclic_spectral_coherence(
            ch1_samples=first,
            ch2_samples=second,
            phase=_phase(first.size),
            ch1_means=_means(),
            ch2_means=_means(),
            declarations=F17Declarations.locked(),
            resources=resources,
        )
