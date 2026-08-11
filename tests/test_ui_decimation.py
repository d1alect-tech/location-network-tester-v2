from pathlib import Path

import numpy as np
import pytest

from lnt.errors import InputError
from lnt.ui.decimation import decimate_spectrum, decimate_waveform, min_max_envelope

MAX_POINTS = 4_000


def test_waveform_preserves_spike_that_uniform_stride_misses() -> None:
    # Given
    samples = np.zeros(1_000_000, dtype=np.float32)
    spike_index = 543_217
    samples[spike_index] = 1.0
    uniform_stride = int(np.ceil(samples.size / MAX_POINTS))

    # When
    result = decimate_waveform(samples, sample_rate_hz=8_000_000.0, max_points=MAX_POINTS)

    # Then
    assert 1.0 not in samples[::uniform_stride]
    assert 1.0 in result.y


def test_waveform_stays_within_point_budget_for_large_input() -> None:
    # Given
    samples = np.zeros(2_000_000, dtype=np.float32)

    # When
    result = decimate_waveform(samples, sample_rate_hz=8_000_000.0, max_points=MAX_POINTS)

    # Then
    assert result.point_count <= MAX_POINTS
    assert result.point_count == len(result.x) == len(result.y)


def test_envelope_passes_through_short_series_exactly() -> None:
    # Given
    x = np.array([0.0, 0.25, 0.5, 0.75], dtype=np.float64)
    y = np.array([2.0, -1.0, 3.0, 0.5], dtype=np.float64)

    # When
    result = min_max_envelope(x, y, max_points=4)

    # Then
    assert result.x == (0.0, 0.25, 0.5, 0.75)
    assert result.y == (2.0, -1.0, 3.0, 0.5)
    assert result.point_count == 4


def test_envelope_preserves_temporal_order() -> None:
    # Given
    x = np.arange(101, dtype=np.float64)
    y = np.sin(x)

    # When
    result = min_max_envelope(x, y, max_points=20)

    # Then
    assert np.all(np.diff(result.x) > 0.0)


def test_envelope_always_preserves_first_and_last_samples() -> None:
    # Given
    x = np.arange(20, dtype=np.float64)
    y = np.array([7.0, *np.zeros(18, dtype=np.float64), -9.0], dtype=np.float64)

    # When
    result = min_max_envelope(x, y, max_points=8)

    # Then
    assert (result.x[0], result.y[0]) == (0.0, 7.0)
    assert (result.x[-1], result.y[-1]) == (19.0, -9.0)


def test_waveform_x_values_are_selected_indices_divided_by_rate() -> None:
    # Given
    sample_rate_hz = 8.0
    samples = np.arange(32, dtype=np.float32)

    # When
    result = decimate_waveform(samples, sample_rate_hz=sample_rate_hz, max_points=10)

    # Then
    np.testing.assert_array_equal(np.asarray(result.x), np.asarray(result.y) / sample_rate_hz)


def test_spectrum_strips_pairs_unsafe_for_log_axes() -> None:
    # Given
    frequency_hz = np.array(
        [-1.0, 0.0, 10.0, 20.0, np.nan, 30.0, 40.0, np.inf, 50.0, 60.0],
        dtype=np.float64,
    )
    psd_v2_per_hz = np.array(
        [1.0, 1.0, 2.0, 0.0, 3.0, np.nan, np.inf, 4.0, -1.0, 5.0],
        dtype=np.float64,
    )

    # When
    result = decimate_spectrum(frequency_hz, psd_v2_per_hz, max_points=10)

    # Then
    assert result.x == (10.0, 60.0)
    assert result.y == (2.0, 5.0)
    assert all(value > 0.0 and np.isfinite(value) for value in (*result.x, *result.y))


@pytest.mark.parametrize("sample_rate_hz", [0.0, float("nan")])
def test_waveform_rejects_invalid_sample_rate(sample_rate_hz: float) -> None:
    # Given
    samples = np.zeros(16, dtype=np.float32)

    # When / Then
    with pytest.raises(InputError, match="частота дискретизации"):
        decimate_waveform(samples, sample_rate_hz=sample_rate_hz, max_points=8)


def test_waveform_rejects_non_vector_samples() -> None:
    # Given
    samples = np.zeros((2, 8), dtype=np.float32)

    # When / Then
    with pytest.raises(InputError, match="одномерным"):
        decimate_waveform(samples, sample_rate_hz=8_000_000.0, max_points=8)


def test_waveform_rejects_point_budget_below_four() -> None:
    # Given
    samples = np.zeros(16, dtype=np.float32)

    # When / Then
    with pytest.raises(InputError, match="max_points"):
        decimate_waveform(samples, sample_rate_hz=8_000_000.0, max_points=3)


def test_spectrum_returns_empty_series_without_log_safe_pairs() -> None:
    # Given
    frequency_hz = np.array([-1.0, 0.0, np.nan], dtype=np.float64)
    psd_v2_per_hz = np.array([1.0, 0.0, np.inf], dtype=np.float64)

    # When
    result = decimate_spectrum(frequency_hz, psd_v2_per_hz, max_points=8)

    # Then
    assert result.x == ()
    assert result.y == ()
    assert result.point_count == 0


def test_waveform_accepts_read_only_memmap(tmp_path: Path) -> None:
    # Given
    path = tmp_path / "samples.npy"
    np.save(path, np.arange(64, dtype=np.float32))
    samples = np.load(path, mmap_mode="r")

    # When
    result = decimate_waveform(samples, sample_rate_hz=16.0, max_points=12)

    # Then
    assert result.point_count <= 12
    assert result.x[0] == 0.0
    assert result.x[-1] == pytest.approx(63.0 / 16.0)
