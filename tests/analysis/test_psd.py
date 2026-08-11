from __future__ import annotations

import numpy as np
import pytest
from scipy import signal

from lnt.analysis_store.settings import WelchSettings
from lnt.psd import FrequencyBand, PsdSettings, compute_welch


def _recipe_settings(segment_samples: int) -> WelchSettings:
    return WelchSettings(
        window="hann_periodic",
        segment_samples=segment_samples,
        overlap_fraction=0.5,
        detrend="constant",
        scaling="density",
        average="mean",
    )


def test_chunked_welch_matches_scipy_for_float32_input() -> None:
    # Given
    rng = np.random.default_rng(20260811)
    samples = rng.normal(0.0, 0.2, 65_536).astype(np.float32)
    settings = PsdSettings.from_recipe(
        sample_rate_hz=48_000.0,
        welch=_recipe_settings(2_048),
        bands=(FrequencyBand(name="audio", low_hz=3_000.0, high_hz=20_000.0),),
        max_chunk_samples=4_096,
    )

    # When
    result = compute_welch(samples, settings=settings)
    expected_frequency, expected_psd = signal.welch(
        samples,
        fs=48_000.0,
        window="hann",
        nperseg=2_048,
        noverlap=1_024,
        detrend="constant",
        return_onesided=True,
        scaling="density",
        average="mean",
    )

    # Then
    np.testing.assert_array_equal(result.frequency_hz, expected_frequency)
    np.testing.assert_allclose(result.psd_v2_per_hz, expected_psd, rtol=2e-6, atol=1e-15)


def test_outputs_expose_units_and_derived_quantities() -> None:
    # Given
    sample_rate_hz = 8_000.0
    time_s = np.arange(16_384, dtype=np.float64) / sample_rate_hz
    samples = (0.25 * np.sin(2 * np.pi * 1_000.0 * time_s)).astype(np.float32)
    settings = PsdSettings.from_recipe(
        sample_rate_hz=sample_rate_hz,
        welch=_recipe_settings(1_024),
        bands=(FrequencyBand(name="tone", low_hz=900.0, high_hz=1_100.0),),
    )

    # When
    result = compute_welch(samples, settings=settings)

    # Then
    np.testing.assert_allclose(result.asd_v_per_sqrt_hz**2, result.psd_v2_per_hz)
    finite = result.psd_v2_per_hz > 0
    np.testing.assert_allclose(
        result.level_db_v2_per_hz[finite],
        10.0 * np.log10(result.psd_v2_per_hz[finite] / 1.0),
    )
    assert result.psd_unit == "V²/Hz"
    assert result.asd_unit == "V/√Hz"
    assert result.level_unit == "dB re 1 V²/Hz"
    assert result.band_rms[0].unit == "V"
    assert result.band_rms[0].rms_v == pytest.approx(0.25 / np.sqrt(2), rel=0.01)


def test_frequency_grid_is_exact_rfftfreq_grid() -> None:
    # Given
    settings = PsdSettings.from_recipe(
        sample_rate_hz=10_000.0,
        welch=_recipe_settings(1_000),
        bands=(FrequencyBand(name="valid", low_hz=0.0, high_hz=5_000.0),),
    )
    samples = np.zeros(4_000, dtype=np.float32)

    # When
    result = compute_welch(samples, settings=settings)

    # Then
    np.testing.assert_array_equal(result.frequency_hz, np.fft.rfftfreq(1_000, d=1 / 10_000.0))


def test_default_recipe_preserves_fifty_hertz_and_measurement_band() -> None:
    # Given / When
    settings = PsdSettings.default(sample_rate_hz=8_000_000.0)

    # Then
    assert settings.nperseg == 160_000
    assert settings.resolution_hz == 50.0
    assert settings.bands == (
        FrequencyBand(name="measurement", low_hz=3_000.0, high_hz=3_000_000.0),
    )
