"""Паритетные тесты потокового взаимного спектра Уэлча CM/DM (задача T1).

Проверяем: побитовую эквивалентность потоковой сегментации однопроходной,
совпадение с lnt.psd.engine и scipy.signal.csd, неравенство Коши—Буняковского
по бинам и типизированные отказы на коротких/несогласованных входах.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from numpy.typing import NDArray
from scipy import signal

from lnt.analysis_store.settings import WelchSettings
from lnt.cm_dm.spectra import CrossWelchResult, compute_cross_welch
from lnt.psd import FrequencyBand, PsdSettings, compute_welch
from lnt.psd.errors import PsdDataError

if TYPE_CHECKING:
    from lnt.psd.models import PsdResult

Float64Vector = NDArray[np.float64]


def _engine_psd(samples: Float64Vector, fs: float, nperseg: int) -> PsdResult:
    """Считает PSD штатным движком lnt.psd с теми же параметрами сегментации."""
    recipe = WelchSettings(
        window="hann_periodic",
        segment_samples=nperseg,
        overlap_fraction=0.5,
        detrend="constant",
        scaling="density",
        average="mean",
    )
    settings = PsdSettings.from_recipe(
        sample_rate_hz=fs,
        welch=recipe,
        bands=(FrequencyBand(name="all", low_hz=0.0, high_hz=fs / 2),),
    )
    return compute_welch(samples, settings=settings)


def _reference_cross_welch(
    ch1: Float64Vector,
    ch2: Float64Vector,
    fs: float,
    nperseg: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.complex128]]:
    """Прямой однопроходный расчёт по всей записи без потоковых порций."""
    window = np.asarray(signal.get_window("hann", nperseg, fftbins=True), dtype=np.float64)
    step = nperseg // 2
    segment_total = 1 + (ch1.size - nperseg) // step
    scale = 1.0 / (fs * float(np.sum(window * window)))
    bins = nperseg // 2 + 1
    acc_ll = np.zeros(bins, dtype=np.float64)
    acc_nn = np.zeros(bins, dtype=np.float64)
    acc_ln = np.zeros(bins, dtype=np.complex128)
    for offset in range(0, segment_total * step, step):
        seg1 = ch1[offset : offset + nperseg]
        seg2 = ch2[offset : offset + nperseg]
        transformed1 = np.fft.rfft((seg1 - float(np.mean(seg1))) * window)
        transformed2 = np.fft.rfft((seg2 - float(np.mean(seg2))) * window)
        acc_ll += np.asarray(transformed1.real**2 + transformed1.imag**2) * scale
        acc_nn += np.asarray(transformed2.real**2 + transformed2.imag**2) * scale
        acc_ln += np.conj(transformed1) * transformed2 * scale
    interior = slice(1, -1) if nperseg % 2 == 0 else slice(1, None)
    acc_ll[interior] *= 2.0
    acc_nn[interior] *= 2.0
    acc_ln[interior] *= 2.0
    return acc_ll / segment_total, acc_nn / segment_total, acc_ln / segment_total


def test_cross_welch_autospectrum_matches_psd_engine() -> None:
    rng = np.random.default_rng(20260825)
    fs = 1_000_000.0
    # fs/250 = 4000 -> next_pow2 = 4096 -> зажим в нижнюю границу 8192.
    ch1 = rng.standard_normal(300_000)
    result = compute_cross_welch(ch1, ch1, fs)
    engine = _engine_psd(ch1, fs, nperseg=8_192)
    assert result.segment_count == engine.segment_count
    np.testing.assert_allclose(result.frequency_hz, engine.frequency_hz)
    np.testing.assert_allclose(
        np.sqrt(result.s_ll),
        engine.asd_v_per_sqrt_hz,
        rtol=2e-6,
        atol=1e-15,
    )


def test_cross_welch_matches_scipy_csd() -> None:
    rng = np.random.default_rng(42)
    fs = 192_000.0
    nperseg = 2_048
    time = np.arange(60_000) / fs
    ch1 = 0.4 * np.sin(2.0 * np.pi * 9_500.0 * time) + 0.05 * rng.standard_normal(time.size)
    ch2 = 0.3 * np.sin(2.0 * np.pi * 9_500.0 * time + 0.7) + 0.08 * rng.standard_normal(time.size)
    result = compute_cross_welch(ch1, ch2, fs, nperseg=nperseg)
    ref_freq, ref_ln = signal.csd(
        ch1,
        ch2,
        fs=fs,
        window="hann",
        nperseg=nperseg,
        detrend="constant",
        scaling="density",
    )
    np.testing.assert_allclose(result.frequency_hz, ref_freq)
    np.testing.assert_allclose(np.real(result.s_ln_cplx), np.real(ref_ln), rtol=1e-7)
    np.testing.assert_allclose(np.imag(result.s_ln_cplx), np.imag(ref_ln), rtol=1e-7)


def test_block_boundaries_match_continuous_segmentation() -> None:
    rng = np.random.default_rng(7)
    fs = 480_000.0
    nperseg = 1_024
    ch1 = rng.standard_normal(50_001)
    ch2 = 0.5 * rng.standard_normal(50_001)
    by_default = compute_cross_welch(ch1, ch2, fs, nperseg=nperseg)
    by_small_blocks = compute_cross_welch(ch1, ch2, fs, nperseg=nperseg, block_samples=4_097)
    by_tiny_blocks = compute_cross_welch(ch1, ch2, fs, nperseg=nperseg, block_samples=100)
    step = nperseg // 2
    expected_segments = 1 + (ch1.size - nperseg) // step
    assert isinstance(by_default, CrossWelchResult)
    for variant in (by_small_blocks, by_tiny_blocks):
        assert np.array_equal(variant.frequency_hz, by_default.frequency_hz)
        assert np.array_equal(variant.s_ll, by_default.s_ll)
        assert np.array_equal(variant.s_nn, by_default.s_nn)
        assert np.array_equal(variant.s_ln_cplx, by_default.s_ln_cplx)
        assert variant.segment_count == expected_segments
    ref_ll, ref_nn, ref_ln = _reference_cross_welch(ch1, ch2, fs, nperseg)
    np.testing.assert_allclose(by_default.s_ll, ref_ll, rtol=1e-12)
    np.testing.assert_allclose(by_default.s_nn, ref_nn, rtol=1e-12)
    np.testing.assert_allclose(by_default.s_ln_cplx, ref_ln, rtol=1e-12)


def test_cauchy_schwarz_holds_per_bin() -> None:
    rng = np.random.default_rng(2026)
    fs = 1_000_000.0
    ch1 = rng.standard_normal(120_000)
    ch2 = rng.standard_normal(120_000)
    result = compute_cross_welch(ch1, ch2, fs)
    lhs = np.abs(result.s_ln_cplx) ** 2
    rhs = result.s_ll * result.s_nn * (1.0 + 1e-9)
    assert bool(np.all(lhs <= rhs))


def test_empty_and_short_inputs_raise() -> None:
    fs = 1_000_000.0
    empty: Float64Vector = np.array([], dtype=np.float64)
    with pytest.raises(PsdDataError):
        compute_cross_welch(empty, empty, fs)
    short1: Float64Vector = np.zeros(8_000, dtype=np.float64)
    with pytest.raises(PsdDataError):
        compute_cross_welch(short1, short1, fs, nperseg=4_096)
    long_enough: Float64Vector = np.zeros(10_000, dtype=np.float64)
    mismatched: Float64Vector = np.zeros(9_999, dtype=np.float64)
    with pytest.raises(PsdDataError):
        compute_cross_welch(long_enough, mismatched, fs)
