"""Trace-детекторы Welch PSD (очередь B2): mean/rms/max-hold/min-hold.

Truth: одиночный громкий сегмент среди тихих — max-hold показывает
периодограмму сегмента, mean разбавляет ровно в N раз, rms — в sqrt(N),
min-hold остаётся нулём. Ожидания посчитаны прямой формулой
периодограммы (определение), а не выводом движка.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import signal

from lnt.psd import FrequencyBand, PsdSettings, compute_welch
from lnt.psd.errors import PsdSettingsError

_FS = 8000.0
_NPERSEG = 1024
_SEGMENTS = 5
_BURST_SEGMENT = 2
_TONE_HZ = 1000.0  # ровно бин 128: 1000 / (8000/1024) = 128
_BURST_BIN = 128


def _settings(*, detector: str = "mean", track_max_hold: bool = False) -> PsdSettings:
    """Базовые настройки теста; варьируются только детектор и max-hold."""
    return PsdSettings(
        sample_rate_hz=_FS,
        nperseg=_NPERSEG,
        max_chunk_samples=_NPERSEG,
        bands=(FrequencyBand(name="full", low_hz=0.0, high_hz=_FS / 2),),
        overlap_fraction=0.0,
        detector=detector,
        track_max_hold=track_max_hold,
    )


def _burst_samples() -> np.ndarray:
    total = _NPERSEG * _SEGMENTS
    samples = np.zeros(total, dtype=np.float32)
    start = _BURST_SEGMENT * _NPERSEG
    time = np.arange(_NPERSEG, dtype=np.float64) / _FS
    samples[start : start + _NPERSEG] = np.sin(2.0 * np.pi * _TONE_HZ * time).astype(np.float32)
    return samples


def _welch_scale(window: np.ndarray) -> float:
    """Скейл периодограммы по определению Уэлча."""
    return _FS * float(np.sum(window * window))


def _expected_burst_periodogram() -> np.ndarray:
    """Аналитическая периодограмма громкого сегмента (определение Уэлча)."""
    window = np.asarray(signal.get_window("hann", _NPERSEG, fftbins=True), dtype=np.float64)
    time = np.arange(_NPERSEG, dtype=np.float64) / _FS
    raw = np.sin(2.0 * np.pi * _TONE_HZ * time).astype(np.float32).astype(np.float64)
    segment = (raw - float(np.mean(raw))) * window
    transformed = np.fft.rfft(segment)
    periodogram = (transformed.real**2 + transformed.imag**2) / _welch_scale(window)
    periodogram[1:-1] *= 2.0
    return periodogram


def test_transient_visible_in_max_hold_lost_in_mean() -> None:
    # Given: один громкий сегмент среди восьми точных нулей
    samples = _burst_samples()
    expected = _expected_burst_periodogram()

    # When
    mean = compute_welch(samples, settings=_settings(detector="mean"))
    hold = compute_welch(samples, settings=_settings(detector="max-hold"))
    rms = compute_welch(samples, settings=_settings(detector="rms"))
    minimum = compute_welch(samples, settings=_settings(detector="min-hold"))

    # Then: точные коэффициенты разбавления переходного процесса
    assert mean.segment_count == hold.segment_count == _SEGMENTS
    np.testing.assert_allclose(hold.psd_v2_per_hz[_BURST_BIN], expected[_BURST_BIN], rtol=1e-9)
    np.testing.assert_allclose(
        mean.psd_v2_per_hz[_BURST_BIN], expected[_BURST_BIN] / _SEGMENTS, rtol=1e-9
    )
    np.testing.assert_allclose(
        rms.psd_v2_per_hz[_BURST_BIN], expected[_BURST_BIN] / np.sqrt(_SEGMENTS), rtol=1e-9
    )
    assert minimum.psd_v2_per_hz[_BURST_BIN] == 0.0
    assert hold.psd_v2_per_hz[_BURST_BIN] / mean.psd_v2_per_hz[_BURST_BIN] == pytest.approx(
        _SEGMENTS, rel=1e-9
    )


def test_detector_ordering_min_mean_rms_max() -> None:
    # Given / When
    samples = _burst_samples()
    results = {
        name: compute_welch(samples, settings=_settings(detector=name))
        for name in ("mean", "rms", "max-hold", "min-hold")
    }

    # Then: поточечный порядок детекторов на всём спектре
    assert np.all(results["min-hold"].psd_v2_per_hz <= results["mean"].psd_v2_per_hz)
    assert np.all(results["mean"].psd_v2_per_hz <= results["rms"].psd_v2_per_hz)
    assert np.all(results["rms"].psd_v2_per_hz <= results["max-hold"].psd_v2_per_hz)


def test_default_detector_is_mean_bit_identical() -> None:
    # Given
    samples = _burst_samples()

    # When
    default = compute_welch(samples, settings=_settings())
    explicit = compute_welch(samples, settings=_settings(detector="mean"))
    _, expected_psd = signal.welch(
        samples,
        fs=_FS,
        window="hann",
        nperseg=_NPERSEG,
        noverlap=0,
        detrend="constant",
        return_onesided=True,
        scaling="density",
        average="mean",
    )

    # Then: дефолт — mean бит-в-бит, согласие со SciPy прежнее
    assert default.detector == "mean"
    np.testing.assert_array_equal(default.psd_v2_per_hz, explicit.psd_v2_per_hz)
    np.testing.assert_allclose(default.psd_v2_per_hz, expected_psd, rtol=2e-6, atol=1e-15)


def test_single_segment_all_detectors_agree() -> None:
    # Given: ровно один сегмент — усреднять нечего
    time = np.arange(_NPERSEG, dtype=np.float64) / _FS
    samples = (0.5 * np.sin(2.0 * np.pi * 250.0 * time)).astype(np.float32)

    # When
    results = [
        compute_welch(samples, settings=_settings(detector=name))
        for name in ("mean", "rms", "max-hold", "min-hold")
    ]

    # Then
    for result in results[1:]:
        np.testing.assert_array_equal(result.psd_v2_per_hz, results[0].psd_v2_per_hz)


def test_unknown_detector_rejected() -> None:
    with pytest.raises(PsdSettingsError):
        _settings(detector="peak")


def test_track_max_hold_matches_dedicated_hold_run() -> None:
    # Given / When: один проход mean + попутный max-hold
    samples = _burst_samples()
    combined = compute_welch(samples, settings=_settings(detector="mean", track_max_hold=True))
    dedicated = compute_welch(samples, settings=_settings(detector="max-hold"))

    # Then: попутный след равен отдельному max-hold проходу, mean untouched
    assert combined.psd_max_hold_v2_per_hz is not None
    np.testing.assert_array_equal(combined.psd_max_hold_v2_per_hz, dedicated.psd_v2_per_hz)
    np.testing.assert_array_equal(
        combined.psd_v2_per_hz, compute_welch(samples, settings=_settings()).psd_v2_per_hz
    )
