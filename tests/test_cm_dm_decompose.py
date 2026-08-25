"""RED-контракты T2: чистая математика CM/DM-декомпозиции (src/lnt/cm_dm/decompose.py)."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.cm_dm.decompose import (
    CM_DM_LOW_HZ,
    DecomposedSpectra,
    PeakAttribution,
    band_mask,
    band_rms,
    decompose,
    pick_peaks,
)

ComplexArray = NDArray[np.complex128]
Float64Array = NDArray[np.float64]


def _arbitrary_physical_spectra(
    rng: np.random.Generator,
    bins: int = 48,
) -> tuple[Float64Array, Float64Array, ComplexArray]:
    """Произвольные физичные спектры: автоспектры > 0, |S_LN| <= sqrt(S_LL*S_NN)."""
    s_ll = rng.uniform(0.5, 2.0, bins)
    s_nn = rng.uniform(0.5, 2.0, bins)
    rho = rng.uniform(0.1, 0.9, bins)
    phase = rng.uniform(-np.pi, np.pi, bins)
    s_ln = rho * np.sqrt(s_ll * s_nn) * np.exp(1j * phase)
    return s_ll, s_nn, s_ln.astype(np.complex128)


def test_cm_plus_dm_equals_half_total_power(rng: np.random.Generator) -> None:
    """P_CM + P_DM == (S_LL + S_NN)/2 тождественно, на произвольных входах."""
    s_ll, s_nn, s_ln = _arbitrary_physical_spectra(rng)
    result = decompose(s_ll, s_nn, s_ln, segment_count=16)

    assert isinstance(result, DecomposedSpectra)
    assert result.cm_psd.dtype == np.dtype(np.float64)
    assert result.dm_psd.dtype == np.dtype(np.float64)
    assert result.coherence.dtype == np.dtype(np.float64)
    expected_total_half = (s_ll + s_nn) / 2.0
    np.testing.assert_allclose(result.cm_psd + result.dm_psd, expected_total_half, rtol=1e-12)


def test_in_phase_signals_land_in_cm() -> None:
    """Синфазные каналы (S_LN = +sqrt(S_LL*S_NN)): весь сигнал в CM, DM == 0."""
    autospectrum = np.full(32, 2.5)
    s_ln = np.full(32, 2.5, dtype=np.complex128)  # |s_ln| == sqrt(s_ll*s_nn), фаза 0
    result = decompose(autospectrum, autospectrum.copy(), s_ln, segment_count=16)

    total_half = autospectrum  # (s_ll + s_nn)/2 == s_ll
    np.testing.assert_allclose(result.dm_psd, 0.0, atol=1e-12 * float(total_half.max()))
    np.testing.assert_allclose(result.cm_psd, total_half, rtol=1e-12)


def test_antiphase_signals_land_in_dm() -> None:
    """Противофазные каналы (S_LN = -sqrt(S_LL*S_NN)): весь сигнал в DM, CM == 0."""
    autospectrum = np.full(32, 2.5)
    s_ln = np.full(32, -2.5, dtype=np.complex128)  # действительный отрицательный
    result = decompose(autospectrum, autospectrum.copy(), s_ln, segment_count=16)

    total_half = autospectrum
    np.testing.assert_allclose(result.cm_psd, 0.0, atol=1e-12 * float(total_half.max()))
    np.testing.assert_allclose(result.dm_psd, total_half, rtol=1e-12)


def test_coherence_of_identical_channels_is_one_after_debias() -> None:
    """Полностью когерентные каналы: gamma_hat == 1, после дебиаса == 1 при любом N > 1."""
    autospectrum = np.full(32, 2.5)
    s_ln = np.full(32, 2.5, dtype=np.complex128)
    for segments in (2, 16):
        result = decompose(autospectrum, autospectrum.copy(), s_ln, segment_count=segments)
        np.testing.assert_allclose(result.coherence, 1.0, rtol=1e-12)


def test_coherence_of_independent_noise_debiased_to_zero(rng: np.random.Generator) -> None:
    """Независимые шумы: дебиас прижимает оценку к нулю против сырой gamma_hat ~ 1/N.

    Выбор метода: Монте-Карло по многим испытаниям сегментного усреднения
    (а не аналитический случай gamma_hat = 1/N) — проверяем свойство
    несмещённости на реалистичных оценках MSC. Нюанс: из-за clamp(max(0, ·))
    среднее скорректированных значений остаётся слегка положительным
    (порядка sigma/sqrt(2*pi)), поэтому порог — уровень смещения, не нуль,
    а сырая оценка служит базой для сравнения.
    """
    n_segments, n_trials, n_bins = 64, 150, 6
    raw_sum = np.zeros(n_bins)
    corrected_sum = np.zeros(n_bins)
    for _ in range(n_trials):
        x = rng.standard_normal((n_segments, n_bins))
        y = rng.standard_normal((n_segments, n_bins))
        s_xx = (x * x).mean(axis=0)
        s_yy = (y * y).mean(axis=0)
        s_xy = (x * y).mean(axis=0).astype(np.complex128)
        raw_sum += np.abs(s_xy) ** 2 / (s_xx * s_yy)
        corrected_sum += decompose(s_xx, s_yy, s_xy, segment_count=n_segments).coherence
    raw_mean = raw_sum / n_trials
    corrected_mean = corrected_sum / n_trials
    # Посылка дебиаса: E[gamma_hat] ~= 1/N для независимых каналов.
    np.testing.assert_allclose(raw_mean * n_segments, 1.0, rtol=0.15)
    # После коррекции смещение исчезло в уровне шума зажима и много меньше сырого.
    assert float(np.max(corrected_mean)) < 0.02
    # Зажим max(0, ·) оставляет пол порядка sigma/sqrt(2*pi) (~0.4/N), поэтому
    # отношение к сырой оценке стабилизируется около ~0.5, а не к нулю.
    assert float(corrected_mean.mean()) < float(raw_mean.mean()) * 0.75


def test_single_average_clamps_to_zero() -> None:
    """segment_count == 1 => когерентность везде 0; никаких NaN/inf в результате."""
    autospectrum = np.full(16, 3.0)
    autospectrum[0] = 0.0  # нулевой бин автоспектра не должен породить NaN
    s_ln = np.full(16, 3.0, dtype=np.complex128)
    result = decompose(autospectrum, autospectrum.copy(), s_ln, segment_count=1)

    assert result.coherence.shape == autospectrum.shape
    np.testing.assert_array_equal(result.coherence, np.zeros_like(result.coherence))
    assert np.all(np.isfinite(result.cm_psd))
    assert np.all(np.isfinite(result.dm_psd))
    assert np.all(np.isfinite(result.coherence))


def test_band_mask_and_rms_integration() -> None:
    """Белый PSD sigma^2/Гц в полосе: band_rms == sigma*sqrt(f2-f1); маска точна вне полосы."""
    freqs = np.linspace(0.0, 40_000.0, 4_001)  # шаг 10 Гц
    low_hz, high_hz = 9_000.0, 30_000.0
    mask = band_mask(freqs, low_hz, high_hz)

    inside = freqs[mask]
    assert inside[0] == low_hz
    assert inside[-1] == high_hz
    assert not bool(mask[freqs < low_hz].any())
    assert not bool(mask[freqs > high_hz].any())
    assert CM_DM_LOW_HZ == 9_000.0
    assert bool(band_mask(freqs, CM_DM_LOW_HZ, high_hz)[900])

    sigma2_per_hz = 4e-10  # плоский PSD: Вт²/Гц в условных единицах
    psd = np.full(freqs.size, sigma2_per_hz)
    rms = band_rms(psd, freqs, low_hz, high_hz)
    expected_rms = np.sqrt(sigma2_per_hz * (high_hz - low_hz))
    assert rms == pytest.approx(float(expected_rms), rel=1e-9)
    # Диапазон частот за пределами сетки: маска пуста -> интеграл 0 -> RMS == 0.
    assert band_rms(psd, freqs, 41_000.0, 45_000.0) == pytest.approx(0.0, abs=1e-30)


def test_peak_attribution_modes() -> None:
    """Два пика: доминантный в CM на f_a и меньший в DM на f_b — атрибуция и порядок."""
    freqs = np.linspace(0.0, 100_000.0, 4_001)  # шаг 25 Гц
    floor = 1e-12
    f_a, f_b = 12_000.0, 25_000.0
    cm_shape = floor + 1e-6 * np.exp(-0.5 * ((freqs - f_a) / 300.0) ** 2)  # пик ~60 дБ
    dm_shape = floor + 1e-8 * np.exp(-0.5 * ((freqs - f_b) / 300.0) ** 2)  # пик ~40 дБ

    peaks = pick_peaks(freqs, cm_shape, dm_shape)

    assert len(peaks) == 2
    assert all(isinstance(peak, PeakAttribution) for peak in peaks)
    assert [peak.mode for peak in peaks] == ["cm", "dm"]
    assert peaks[0].frequency_hz == pytest.approx(f_a, abs=60.0)
    assert peaks[1].frequency_hz == pytest.approx(f_b, abs=60.0)
    assert peaks[0].level_db == pytest.approx(10.0 * np.log10(1e-6), rel=1e-3)
    assert peaks[1].level_db == pytest.approx(10.0 * np.log10(1e-8), rel=1e-3)
    # Ограничение max_peaks оставляет только самый выраженный пик (CM).
    strongest_only = pick_peaks(freqs, cm_shape, dm_shape, max_peaks=1)
    assert len(strongest_only) == 1
    assert strongest_only[0].mode == "cm"
