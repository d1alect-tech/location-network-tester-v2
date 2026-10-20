"""Аналитическая истина для чистых метрик полного ряда риппла.

Truth выведена из определений: среднее, центрированное population RMS AC,
фактический размах max-min. Ни одно ожидание не берётся из движка.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.errors import InputError
from lnt.ripple import interval_stats, mean_v, rms_ac_v, vpp_v

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import ArrayLike

_FS_HZ = 10_000.0
_COUNT = 10_000
_DC_V = 12.0
_AMPLITUDE_V = 0.05
_FREQ_HZ = 100.0
_TIME_S = np.arange(_COUNT, dtype=np.float64) / _FS_HZ
_SINE = _DC_V + _AMPLITUDE_V * np.sin(2.0 * np.pi * _FREQ_HZ * _TIME_S)


def test_float64_sine_mean_rms_and_vpp_match_closed_form() -> None:
    # Given: 100 exact cycles at 100 Hz, fs 10 kHz, DC 12 V, amplitude 0.05 V
    # When
    actual_mean = mean_v(_SINE)
    actual_rms = rms_ac_v(_SINE)
    actual_vpp = vpp_v(_SINE)

    # Then: analytic 12 V, A/sqrt(2), and 2A independent of the offset
    assert actual_mean == pytest.approx(_DC_V, rel=0.0, abs=1e-12)
    assert actual_rms == pytest.approx(_AMPLITUDE_V / np.sqrt(2.0), rel=1e-9)
    assert actual_vpp == pytest.approx(2.0 * _AMPLITUDE_V, rel=1e-9)


def test_offset_invariance_of_rms_and_vpp() -> None:
    # Given: the same tone with and without the 12 V offset
    centered = _AMPLITUDE_V * np.sin(2.0 * np.pi * _FREQ_HZ * _TIME_S)
    shifted = centered + _DC_V

    # When
    centered_rms = rms_ac_v(centered)
    shifted_rms = rms_ac_v(shifted)
    centered_vpp = vpp_v(centered)
    shifted_vpp = vpp_v(shifted)

    # Then: AC statistics are identical, and mean carries the offset
    assert shifted_rms == pytest.approx(centered_rms, rel=1e-12, abs=1e-15)
    assert shifted_vpp == pytest.approx(centered_vpp, rel=1e-12, abs=1e-15)
    assert mean_v(shifted) - mean_v(centered) == pytest.approx(_DC_V, abs=1e-12)


def test_centered_two_pass_avoids_cancellation() -> None:
    # Given: E[x^2] - mean^2 cancels to zero for 1e12 +/- 1 in float64
    samples = np.array([1e12 - 1.0, 1e12 + 1.0])
    naive_variance = float(np.mean(samples * samples) - np.mean(samples) ** 2)

    # When
    actual_rms = rms_ac_v(samples)

    # Then: centered population RMS is exactly the analytic 1 V
    assert naive_variance == pytest.approx(0.0, abs=1e-6)
    assert actual_rms == pytest.approx(1.0, rel=1e-15)
    assert vpp_v(samples) == pytest.approx(2.0, rel=1e-15)


def test_constant_clean_signal_has_zero_ac_rms_and_vpp() -> None:
    # Given: constant 5 V, no noise
    samples = np.full(64, 5.0, dtype=np.float64)

    # When / Then
    assert mean_v(samples) == 5.0
    assert rms_ac_v(samples) == 0.0
    assert vpp_v(samples) == 0.0


def test_synthetic_dc12_and_rail_sized_values_are_not_censored() -> None:
    # Given: pure math has no ADC rail; 12 V DC and +/-6 V values stay in math
    dc = np.full(128, 12.0, dtype=np.float64)
    rail_sized = np.array([-6.0, -6.0, 6.0, 6.0], dtype=np.float64)

    # When / Then: no clamp, no sample deletion
    assert mean_v(dc) == 12.0
    assert rms_ac_v(dc) == 0.0
    assert vpp_v(dc) == 0.0
    assert rms_ac_v(rail_sized) == 6.0
    assert vpp_v(rail_sized) == 12.0


def test_float32_input_is_accepted_and_input_is_not_mutated() -> None:
    # Given
    samples = np.full(16, 3.0, dtype=np.float32)
    before = samples.copy()

    # When
    result = mean_v(samples)
    interval_stats(samples, 1_000.0, 0.004)

    # Then
    assert result == 3.0
    np.testing.assert_array_equal(samples, before)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("metric", [mean_v, rms_ac_v, vpp_v])
def test_nonfinite_samples_raise_input_error(
    metric: Callable[[ArrayLike], float], bad: float
) -> None:
    # Given
    samples = np.array([0.0, bad], dtype=np.float64)

    # When / Then
    with pytest.raises(InputError, match="конечн"):
        metric(samples)


@pytest.mark.parametrize("metric", [mean_v, rms_ac_v, vpp_v])
def test_non_1d_or_empty_samples_raise_input_error(metric: Callable[[ArrayLike], float]) -> None:
    # Given / When / Then
    with pytest.raises(InputError, match="1-D"):
        metric(np.zeros((2, 2)))
    with pytest.raises(InputError, match="1-D"):
        metric(np.array(1.0))
    with pytest.raises(InputError, match="пуст"):
        metric(np.array([], dtype=np.float64))


def test_rms_and_vpp_require_two_samples() -> None:
    # Given
    one = np.array([1.0], dtype=np.float64)

    # When / Then
    assert mean_v(one) == 1.0
    with pytest.raises(InputError, match=">= 2"):
        rms_ac_v(one)
    with pytest.raises(InputError, match=">= 2"):
        vpp_v(one)


def test_interval_stats_partitions_with_true_bounds_and_partial_tail() -> None:
    # Given: fs 1 kHz, window 10 samples, 2 complete intervals and 5-sample tail
    samples = np.arange(25, dtype=np.float64)
    fs_hz = 1_000.0
    window_s = 0.01

    # When
    intervals = interval_stats(samples, fs_hz, window_s)

    # Then
    assert len(intervals) == 3
    first, second, tail = intervals
    assert (first.start_index, first.end_index_exclusive, first.sample_count) == (0, 10, 10)
    assert first.complete is True
    assert first.availability == "available"
    assert first.reason_codes == ()
    assert first.realized_duration_s == pytest.approx(0.01)
    assert first.mean_v == pytest.approx(4.5)
    assert first.rms_ac_v == pytest.approx(np.sqrt(8.25))
    assert first.vpp_v == pytest.approx(9.0)

    assert (second.start_index, second.end_index_exclusive, second.sample_count) == (10, 20, 10)
    assert second.mean_v == pytest.approx(14.5)
    assert second.rms_ac_v == pytest.approx(np.sqrt(8.25))
    assert second.vpp_v == pytest.approx(9.0)

    assert (tail.start_index, tail.end_index_exclusive, tail.sample_count) == (20, 25, 5)
    assert tail.complete is False
    assert tail.availability == "available"
    assert tail.realized_duration_s == pytest.approx(0.005)
    assert tail.mean_v == pytest.approx(22.0)
    assert tail.rms_ac_v == pytest.approx(np.sqrt(2.0))
    assert tail.vpp_v == pytest.approx(4.0)


def test_one_sample_tail_is_unavailable_with_original_bounds() -> None:
    # Given: 21 samples with a 10-sample window leave one trailing sample
    samples = np.arange(21, dtype=np.float64)

    # When
    intervals = interval_stats(samples, 1_000.0, 0.01)

    # Then: the timeline is not compressed and no number is fabricated
    assert len(intervals) == 3
    tail = intervals[-1]
    assert (tail.start_index, tail.end_index_exclusive, tail.sample_count) == (20, 21, 1)
    assert tail.complete is False
    assert tail.availability == "unavailable"
    assert tail.reason_codes == ("insufficient_samples",)
    assert tail.realized_duration_s == pytest.approx(0.001)
    assert tail.mean_v is None
    assert tail.rms_ac_v is None
    assert tail.vpp_v is None


def test_exact_multiple_has_no_partial_interval() -> None:
    # Given / When
    intervals = interval_stats(np.arange(20, dtype=np.float64), 1_000.0, 0.01)

    # Then
    assert len(intervals) == 2
    assert all(item.complete for item in intervals)


def test_empty_samples_produce_no_intervals() -> None:
    # Given / When
    intervals = interval_stats(np.array([], dtype=np.float64), 1_000.0, 0.01)

    # Then
    assert intervals == ()


def test_window_rounding_requires_at_least_two_samples() -> None:
    # Given: fs 100 Hz, window 0.014 s rounds to one sample
    samples = np.arange(4, dtype=np.float64)

    # When / Then
    with pytest.raises(InputError, match=">= 2"):
        interval_stats(samples, 100.0, 0.014)
    rounded_up = interval_stats(samples, 100.0, 0.016)
    assert [item.sample_count for item in rounded_up] == [2, 2]
    assert rounded_up[0].realized_duration_s == pytest.approx(0.02)


@pytest.mark.parametrize(
    ("fs_hz", "window_s"),
    [
        (0.0, 1.0),
        (-1.0, 1.0),
        (np.nan, 1.0),
        (np.inf, 1.0),
        (1_000.0, 0.0),
        (1_000.0, -0.1),
        (1_000.0, np.nan),
        (1_000.0, np.inf),
    ],
)
def test_invalid_interval_configuration_raises_input_error(fs_hz: float, window_s: float) -> None:
    # Given
    samples = np.zeros(8, dtype=np.float64)

    # When / Then
    with pytest.raises(InputError, match=r"конечн|> 0|>= 2"):
        interval_stats(samples, fs_hz, window_s)


def test_interval_stats_rejects_nonfinite_and_non_1d_samples() -> None:
    # Given / When / Then
    with pytest.raises(InputError, match="конечн"):
        interval_stats(np.array([0.0, np.nan, 2.0]), 1_000.0, 0.002)
    with pytest.raises(InputError, match="1-D"):
        interval_stats(np.zeros((2, 3)), 1_000.0, 0.002)


@pytest.mark.parametrize(
    "samples",
    [
        np.array([1.0 + 2.0j, 3.0 + 4.0j], dtype=np.complex128),
        np.array([1.0 + 0.0j], dtype=np.complex64),
        [1.0 + 2.0j, 3.0 + 4.0j],
    ],
)
@pytest.mark.parametrize("metric", [mean_v, rms_ac_v, vpp_v])
def test_complex_samples_raise_input_error(
    metric: Callable[[ArrayLike], float], samples: ArrayLike
) -> None:
    # Given: complex ndarray or list; no imaginary component may be discarded
    # When / Then
    with pytest.raises(InputError, match="комплексн"):
        metric(samples)


@pytest.mark.parametrize(
    "samples",
    [
        np.array([1.0 + 1.0j, 3.0 + 3.0j], dtype=np.complex128),
        [1.0 + 1.0j, 3.0 + 3.0j],
    ],
)
def test_interval_stats_rejects_complex_samples(samples: ArrayLike) -> None:
    # Given / When / Then
    with pytest.raises(InputError, match="комплексн"):
        interval_stats(samples, 1_000.0, 0.002)


@pytest.mark.parametrize("metric", [mean_v, rms_ac_v, vpp_v])
def test_overflowing_integer_samples_raise_input_error(
    metric: Callable[[ArrayLike], float],
) -> None:
    # Given: Python int beyond the float64 range
    # When / Then
    with pytest.raises(InputError, match="float64"):
        metric([10**400])


def test_interval_stats_rejects_overflowing_integer_samples() -> None:
    # Given / When / Then
    with pytest.raises(InputError, match="float64"):
        interval_stats([10**400, 2 * 10**400], 1_000.0, 0.002)
