"""F05 uniform_phase_bin_moments RED analytic tests (Wave 4 todo 12)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from lnt.characterization.f05_phase_stats import (
    CIRCULAR_AVERAGE,
    EVENT_SOURCE,
    METHOD,
    MINIMUM_SUPPORT_PER_BIN,
    PHASE_BINS,
    VARIANCE_DDOF,
    F05Result,
    compute_f05_phase_conditioned_statistics,
)

from lnt.characterization.event_models import RootEvent
from lnt.characterization.phase_model import PhaseCycles
from lnt.characterization.records import Status
from lnt.events.models import Polarity

FS_HZ = 3200.0
BINS = 64
_CYCLES = 64
_DRAWS = 500
_DECLARED_CODES = {"phase_reference_unavailable", "insufficient_support"}


def _cycles(
    starts: list[float],
    ends: list[float],
    valid: list[bool],
    sample_count: int,
    *,
    status: Status = Status.AVAILABLE,
) -> PhaseCycles:
    return PhaseCycles(
        sample_rate_hz=FS_HZ,
        sample_count=sample_count,
        cycle_start_samples=np.array(starts, dtype=np.float64),
        cycle_end_samples=np.array(ends, dtype=np.float64),
        cycle_valid=np.array(valid, dtype=np.bool_),
        status=status,
        reason_code=None,
    )


def _event(
    peak_sample: int, *, start_sample: int | None = None, end_sample: int | None = None
) -> RootEvent:
    """RootEvent по образцу F02: спаны задаются явно, не через legacy-детектор."""
    start = peak_sample if start_sample is None else start_sample
    end = peak_sample if end_sample is None else end_sample
    return RootEvent(
        ordinal=0,
        timeline_segment=0,
        start_sample=start,
        end_sample=end,
        peak_sample=peak_sample,
        start_time_s=start / FS_HZ,
        end_time_s=end / FS_HZ,
        peak_time_s=peak_sample / FS_HZ,
        peak_value_v=1.0,
        polarity=Polarity.POSITIVE,
        snr_ratio=100.0,
        excess_v2_s=0.0,
        v2_s=0.0,
        clipped=False,
        dominant_band=None,
        dominant_band_reason_code=None,
        boundary=False,
    )


def _run(
    samples: np.ndarray,
    phase: PhaseCycles,
    events: tuple[RootEvent, ...] = (),
    *,
    bins: int = BINS,
    support: int = 2,
) -> F05Result:
    return compute_f05_phase_conditioned_statistics(
        samples,
        phase,
        events,
        phase_bins=bins,
        minimum_support_per_bin=support,
    )


def test_locked_parameters_match_the_frozen_recipe() -> None:
    """Пять полей контракта заморожены, как в рецепте characterization-v1."""
    assert METHOD == "uniform_phase_bin_moments"
    assert PHASE_BINS == 64
    assert MINIMUM_SUPPORT_PER_BIN == 20
    assert VARIANCE_DDOF == 1
    assert EVENT_SOURCE == "root_events"
    assert CIRCULAR_AVERAGE == "unit_vector"


def test_bin_moments_recover_the_analytic_piecewise_truth() -> None:
    """Два одинаковых цикла: среднее равно истине, разброс исчезает."""
    truth_v = np.arange(BINS, dtype=np.float64) / 8.0 - 4.0
    samples = np.tile(truth_v, 2)
    phase = _cycles([0.0, 64.0], [64.0, 128.0], [True, True], 128)

    result = _run(samples, phase)

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert np.all(result.valid_bins)
    assert np.array_equal(result.counts, np.full(BINS, 2, dtype=np.int64))
    assert np.allclose(result.means_v, truth_v)
    assert np.array_equal(result.variances_v2, np.zeros(BINS, dtype=np.float64))
    assert np.allclose(result.mean_squares_v2, truth_v**2)
    assert np.array_equal(result.event_probabilities, np.zeros(BINS, dtype=np.float64))


def test_mean_square_identity_holds_for_ddof_one() -> None:
    """ms = mu^2 + sigma2 * (n - 1) / n: тождество ddof=1, проверка алгебры."""
    rng = np.random.default_rng(6022)
    samples = rng.standard_normal(4 * BINS)
    phase = _cycles(
        [float(index * BINS) for index in range(4)],
        [float((index + 1) * BINS) for index in range(4)],
        [True, True, True, True],
        4 * BINS,
    )

    result = _run(samples, phase, support=1)

    counts = result.counts.astype(np.float64)
    assert np.array_equal(counts, np.full(BINS, 4, dtype=np.int64))
    expected = result.means_v**2 + result.variances_v2 * (counts - 1.0) / counts
    assert np.allclose(result.mean_squares_v2, expected)


def test_random_phase_kills_the_coherent_mean_but_not_the_mean_square() -> None:
    """Контроль из method-notes: случайная фаза несущей убирает когерентное среднее.

    Числа method-notes (max |mu| = 0.038; ms = 0.500 +/- 0.003) сняты на
    необъявленной установке, поэтому здесь проверяется аналитическая истина
    E[mu] = 0 и E[ms] = A^2/2 = 0.5. 500 реализаций дают по одному отсчёту на
    бин, отсюда СКО: sd(mu) ~ 0.707/sqrt(500) ~ 0.032, sd(ms) ~ 0.5/sqrt(500)
    ~ 0.022; границы взяты с запасом в 4 sigma.
    """
    rng = np.random.default_rng(6022)
    theta = np.arange(BINS, dtype=np.float64) / BINS * 2.0 * math.pi
    rows = [np.cos(theta + float(rng.uniform(0.0, 2.0 * math.pi))) for _ in range(_DRAWS)]
    samples = np.concatenate(rows)
    phase = _cycles(
        [float(index * BINS) for index in range(_DRAWS)],
        [float((index + 1) * BINS) for index in range(_DRAWS)],
        [True] * _DRAWS,
        _DRAWS * BINS,
    )

    result = _run(samples, phase, support=1)

    assert result.status is Status.AVAILABLE
    assert np.array_equal(result.counts, np.full(BINS, _DRAWS, dtype=np.int64))
    assert float(np.max(np.abs(result.means_v))) < 0.13
    assert float(np.max(np.abs(result.mean_squares_v2 - 0.5))) < 0.09


def test_underfilled_bins_are_masked_with_insufficient_support() -> None:
    """Один цикл на 64 бина: поддержка 1 < 2, значения не фабрикуются."""
    phase = _cycles([0.0], [64.0], [True], BINS)
    samples = np.ones(BINS, dtype=np.float64)

    result = _run(samples, phase, support=2)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("insufficient_support",)
    assert not np.any(result.valid_bins)
    assert np.array_equal(result.counts, np.ones(BINS, dtype=np.int64))
    assert np.array_equal(result.means_v, np.zeros(BINS, dtype=np.float64))
    # few_cycles и bin_empty объявлены, но условия срабатывания в спеке не заданы
    # (пробелы F05-1 и F05-2), поэтому этот срез их не эмитит.
    assert set(result.reason_codes) <= _DECLARED_CODES


def test_partial_support_marks_only_the_underfilled_bins() -> None:
    """Половина бинов набрана дважды, половина один раз: маска, а не выдумка."""
    phase = _cycles([0.0, 64.0], [64.0, 96.0], [True, True], 128)
    samples = np.ones(128, dtype=np.float64)

    result = _run(samples, phase, support=2)

    assert result.status is Status.PARTIAL
    assert result.reason_codes == ("insufficient_support",)
    assert np.count_nonzero(result.valid_bins) == BINS // 2
    assert np.all(result.counts[result.valid_bins] == 2)
    assert np.all(result.counts[~result.valid_bins] == 1)
    assert np.all(result.means_v[~result.valid_bins] == 0.0)


def test_event_indicator_marks_the_delimited_span_per_bin() -> None:
    """Индикатор события — весь размеченный спан, не только пик."""
    phase = _cycles([0.0], [64.0], [True], BINS)
    samples = np.zeros(BINS, dtype=np.float64)

    result = _run(samples, phase, (_event(8, start_sample=4, end_sample=11),), support=1)

    expected = np.zeros(BINS, dtype=np.float64)
    expected[4:12] = 1.0
    assert result.status is Status.AVAILABLE
    assert np.allclose(result.event_probabilities, expected)
    assert np.array_equal(result.counts, np.ones(BINS, dtype=np.int64))


def test_event_phase_resultant_uses_unit_vectors_not_a_linear_angle_mean() -> None:
    """Пики на 350 и 10 градусах: линейное среднее углов дало бы 180 градусов."""
    phase = _cycles([0.0, 360.0], [360.0, 720.0], [True, True], 720)
    samples = np.zeros(720, dtype=np.float64)

    result = _run(samples, phase, (_event(350), _event(370)), support=1)

    assert result.event_phase_resultant == pytest.approx(math.cos(math.radians(10.0)), abs=1e-9)
    assert result.event_phase_mean_rad == pytest.approx(0.0, abs=1e-9)
    # Дискриминатор: линейное среднее положило бы направление на pi.
    assert result.event_phase_mean_rad is not None
    assert abs(result.event_phase_mean_rad - math.pi) > 3.0


def test_unavailable_phase_root_maps_to_phase_reference_unavailable() -> None:
    """Отказ корня фазы сворачивается в объявленный код F05, без проброса."""
    phase = _cycles([], [], [], BINS, status=Status.UNAVAILABLE)

    result = _run(np.ones(BINS, dtype=np.float64), phase)

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == ("phase_reference_unavailable",)
    assert not np.any(result.valid_bins)
    assert result.event_phase_resultant is None
    assert result.event_phase_mean_rad is None


def test_only_declared_codes_are_ever_emitted() -> None:
    """Ни один апстрим-код корня фазы не протекает в словарь F05."""
    cases = (
        _run(np.ones(BINS, dtype=np.float64), _cycles([0.0], [64.0], [True], BINS), support=2),
        _run(np.ones(BINS, dtype=np.float64), _cycles([0.0], [64.0], [True], BINS), support=1),
        _run(
            np.ones(BINS, dtype=np.float64),
            _cycles([], [], [], BINS, status=Status.UNAVAILABLE),
        ),
    )
    for result in cases:
        assert set(result.reason_codes) <= _DECLARED_CODES
