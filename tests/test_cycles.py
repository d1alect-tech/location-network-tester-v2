"""Fractional rising zero crossings shared by cycle-based analyses."""

import numpy as np
import pytest

from lnt.cycles import rising_zero_crossings


def test_linear_ramps_cross_at_exact_fractional_samples_without_mutation() -> None:
    values = np.array([-1.0, 1.0, -1.0, 3.0], dtype=np.float64)
    original = values.copy()

    crossings = rising_zero_crossings(values)

    np.testing.assert_array_equal(crossings, np.array([0.5, 2.25], dtype=np.float64))
    np.testing.assert_array_equal(values, original)


def test_zero_plateau_crosses_at_last_zero_before_rising() -> None:
    values = np.array([-1.0, 0.0, 0.0, 2.0], dtype=np.float64)

    np.testing.assert_array_equal(rising_zero_crossings(values), np.array([2.0]))


@pytest.mark.parametrize(
    "values",
    [
        np.array([], dtype=np.float64),
        np.array([1.0, 0.0, -1.0], dtype=np.float64),
    ],
)
def test_empty_or_no_rising_crossing_returns_float64_empty(
    values: np.ndarray[tuple[int], np.dtype[np.float64]],
) -> None:
    crossings = rising_zero_crossings(values)

    assert crossings.size == 0
    assert crossings.dtype == np.float64


def test_sampled_sine_crossings_approach_analytic_crossing_times() -> None:
    period_samples = 256.0
    first_crossing = 10.25
    angular_step = 2.0 * np.pi / period_samples
    sample_indices = np.arange(1024, dtype=np.float64)
    values = np.sin(angular_step * (sample_indices - first_crossing))
    expected = first_crossing + period_samples * np.arange(4, dtype=np.float64)

    crossings = rising_zero_crossings(values)

    # |sin(x) - x| <= |x|^3/6 makes the secant-root error O(step^2).
    interpolation_error_bound = angular_step**2 / 3.0
    np.testing.assert_allclose(crossings, expected, rtol=0.0, atol=interpolation_error_bound)
