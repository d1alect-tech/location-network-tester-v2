from __future__ import annotations

import tracemalloc
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.analysis_store.settings import WelchSettings
from lnt.psd import (
    FrequencyBand,
    PsdCancelledError,
    PsdDataError,
    PsdSettings,
    PsdSettingsError,
    compute_welch,
)

if TYPE_CHECKING:
    from pathlib import Path


def _settings(
    *,
    sample_rate_hz: float = 16_384.0,
    nperseg: int = 2_048,
    high_hz: float | None = None,
) -> PsdSettings:
    welch = WelchSettings(
        window="hann_periodic",
        segment_samples=nperseg,
        overlap_fraction=0.5,
        detrend="constant",
        scaling="density",
        average="mean",
    )
    return PsdSettings.from_recipe(
        sample_rate_hz=sample_rate_hz,
        welch=welch,
        bands=(
            FrequencyBand(
                name="all",
                low_hz=0.0,
                high_hz=sample_rate_hz / 2 if high_hz is None else high_hz,
            ),
        ),
        max_chunk_samples=nperseg * 2,
    )


class CancelAfterFirstChunk:
    """Тестовый токен меняет состояние после первой проверки."""

    def __init__(self) -> None:
        self.checks: int = 0

    @property
    def cancelled(self) -> bool:
        self.checks += 1
        return self.checks > 1


def test_integrated_psd_matches_time_domain_variance() -> None:
    # Given
    rng = np.random.default_rng(9102)
    samples = rng.normal(0.0, 0.4, 262_144).astype(np.float32)

    # When
    result = compute_welch(samples, settings=_settings())

    # Then
    expected_variance = float(np.var(samples, dtype=np.float64))
    integrated_power = result.band_rms[0].rms_v ** 2
    assert integrated_power == pytest.approx(expected_variance, rel=0.015)


def test_amplitude_scaling_is_quadratic() -> None:
    rng = np.random.default_rng(9103)
    samples = rng.normal(0.0, 0.2, 32_768).astype(np.float32)
    original = compute_welch(samples, settings=_settings())
    scaled = compute_welch(samples * 3.0, settings=_settings())
    assert scaled.psd_v2_per_hz == pytest.approx(original.psd_v2_per_hz * 9.0, rel=2e-6)


def test_integer_segment_time_shift_preserves_psd() -> None:
    samples = np.sin(2 * np.pi * 512 * np.arange(32_768) / 16_384).astype(np.float32)
    shifted = np.roll(samples, 2_048)
    first = compute_welch(samples, settings=_settings())
    second = compute_welch(shifted, settings=_settings())
    assert second.psd_v2_per_hz == pytest.approx(first.psd_v2_per_hz, rel=2e-6, abs=1e-15)


def test_chunk_geometry_does_not_change_psd() -> None:
    rng = np.random.default_rng(9104)
    samples = rng.normal(0.0, 0.2, 32_768).astype(np.float32)
    small = compute_welch(samples, settings=_settings())
    whole_settings = PsdSettings(
        sample_rate_hz=16_384.0,
        nperseg=2_048,
        max_chunk_samples=samples.size,
        bands=(FrequencyBand(name="all", low_hz=0.0, high_hz=8_192.0),),
    )
    whole = compute_welch(samples, settings=whole_settings)
    assert small.segment_count == whole.segment_count
    assert small.psd_v2_per_hz == pytest.approx(whole.psd_v2_per_hz, rel=2e-14, abs=1e-18)


def test_sample_rate_change_preserves_physical_tone_frequency_and_power() -> None:
    results = []
    for rate_hz in (16_384.0, 32_768.0):
        time = np.arange(round(rate_hz * 2), dtype=np.float64) / rate_hz
        samples = (0.5 * np.sin(2 * np.pi * 1_024 * time)).astype(np.float32)
        results.append(
            compute_welch(
                samples, settings=_settings(sample_rate_hz=rate_hz, nperseg=round(rate_hz / 8))
            )
        )
    peaks = [float(result.frequency_hz[np.argmax(result.psd_v2_per_hz)]) for result in results]
    assert peaks == pytest.approx([1_024.0, 1_024.0], abs=8.0)
    assert results[0].band_rms[0].rms_v == pytest.approx(results[1].band_rms[0].rms_v, rel=1e-5)


def test_zero_data_produces_exact_zero_linear_results() -> None:
    result = compute_welch(np.zeros(4_096, dtype=np.float32), settings=_settings())
    assert np.array_equal(result.psd_v2_per_hz, np.zeros_like(result.psd_v2_per_hz))
    assert result.band_rms[0].rms_v == 0.0


def test_cancellation_is_checked_between_bounded_chunks() -> None:
    # Given
    samples = np.zeros(65_536, dtype=np.float32)
    token = CancelAfterFirstChunk()

    # When / Then
    with pytest.raises(PsdCancelledError, match="отменён"):
        compute_welch(samples, settings=_settings(), cancellation=token)
    assert token.checks == 2


@pytest.mark.parametrize(
    ("samples", "settings", "message"),
    [
        (np.array([], dtype=np.float32), _settings(), "пуст"),
        (np.zeros(1_024, dtype=np.float32), _settings(), "корот"),
        (
            np.concatenate(
                (np.zeros(4_095, dtype=np.float32), np.array([np.nan], dtype=np.float32))
            ),
            _settings(),
            "NaN",
        ),
        (
            np.full(4_096, np.finfo(np.float64).max, dtype=np.float64),
            _settings(),
            "переполн",
        ),
    ],
)
def test_invalid_data_has_typed_failure(
    samples: np.ndarray[tuple[int], np.dtype[np.float32]]
    | np.ndarray[tuple[int], np.dtype[np.float64]],
    settings: PsdSettings,
    message: str,
) -> None:
    # Given / When / Then
    with pytest.raises(PsdDataError, match=message):
        compute_welch(samples, settings=settings)


def test_band_above_nyquist_has_typed_failure() -> None:
    # Given / When / Then
    with pytest.raises(PsdSettingsError, match="Найквист"):
        _settings(high_hz=8_193.0)


def test_large_memmap_does_not_materialize_whole_float64_record(tmp_path: Path) -> None:
    # Given: whole-record float64 conversion would allocate 32 MiB.
    path = tmp_path / "large.npy"
    writable = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(4_000_000,))
    writable[:] = 0.0
    del writable
    samples = np.load(path, mmap_mode="r", allow_pickle=False)
    settings = _settings(sample_rate_hz=1_000_000.0, nperseg=20_000)

    # When
    tracemalloc.start()
    compute_welch(samples, settings=settings)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Then: cap is less than half a whole float64 record.
    assert peak_bytes < samples.size * np.dtype(np.float64).itemsize // 2
