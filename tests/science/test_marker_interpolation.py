"""Параболическая интерполяция readout маркеров: истина от аналитики, не от движка.

Аналитическая основа (не зависит от движка):
* вершина заданной параболы в дБ восстанавливается точно по трём бинам;
* тон известной частоты лежит в пределах ±0.5 бина от уточнённой частоты;
* мощность тона A²/2 даёт СКЗ A/√2 интегрированием PSD (той же нормой,
  что truth-тест B1 ``test_tone_power_is_window_independent``);
* гармоники лежат ровно на кратных основной частоты.
"""

from __future__ import annotations

import numpy as np

from lnt.markers import band_rms_v, harmonic_table
from lnt.spectrum import (
    BandSpectrum,
    compute_band_spectrum,
    frequency_at,
    level_at_db,
)
from tests.science.truth import verify_scalar

FS_HZ = 16_384.0
AMPLITUDE_V = 0.8
TONE_RMS_V = AMPLITUDE_V / float(np.sqrt(2.0))


def _tone(frequency_hz: float) -> np.ndarray:
    time = np.arange(16_384, dtype=np.float64) / FS_HZ
    return (AMPLITUDE_V * np.sin(2 * np.pi * frequency_hz * time)).astype(np.float32)


def test_parabola_vertex_is_exact_for_analytic_parabola() -> None:
    """Вершина заданной параболы в дБ восстанавливается точно (истина замкнутая)."""
    resolution_hz = 10.0
    vertex_bin = 5.3
    vertex_db = -40.0
    curvature_db = 6.0
    bins = np.arange(12, dtype=np.float64)
    parabola_db = vertex_db - curvature_db * (bins - vertex_bin) ** 2
    frequencies_hz = bins * resolution_hz
    psd = 10.0 ** (parabola_db / 10.0)
    ask_hz = 5.0 * resolution_hz
    verify_scalar(
        level_at_db_for_arrays(frequencies_hz, psd, ask_hz),
        expected=vertex_db,
        absolute_tolerance=1e-9,
        rationale="Замкнутая парабола: вершина обязана совпадать бит-в-бит с точностью float.",
    )
    verify_scalar(
        frequency_at_for_arrays(frequencies_hz, psd, ask_hz),
        expected=vertex_bin * resolution_hz,
        absolute_tolerance=1e-9,
        rationale="Та же замкнутая парабола: частота вершины известна аналитически.",
    )


def test_midbin_tone_frequency_within_half_bin() -> None:
    """Тон между бинами находится с точностью ±0.5 бина (истина — частота тона)."""
    tone_hz = 5_032.0  # середина между бинами сетки df=16 Гц (rbw 50), внутри 3 кГц–3 МГц
    band = compute_band_spectrum(_tone(tone_hz), sample_rate_hz=FS_HZ, rbw_hz=50.0)
    half_bin = band.resolution_hz / 2.0
    verify_scalar(
        frequency_at(band, tone_hz),
        expected=tone_hz,
        absolute_tolerance=half_bin,
        rationale=(
            "Параболическая поправка ограничена ±0.5 бина; частота тона задана "
            "аналитически при синтезе, движок её не определяет."
        ),
    )
    nearest_index = int(np.argmin(np.abs(band.frequencies_hz - tone_hz)))
    nearest_db = 10.0 * float(np.log10(band.psd_v2_per_hz[nearest_index]))
    assert level_at_db(band, tone_hz) >= nearest_db - 1e-9, (
        "интерполяция компенсирует scalloping только вверх от ближайшего бина"
    )


def test_harmonic_table_hits_exact_multiples() -> None:
    """Гармоники H2–H40 лежат ровно на кратных основной (истина — арифметика)."""
    fundamental_hz = 512.0
    time = np.arange(16_384, dtype=np.float64) / FS_HZ
    samples = (
        np.sin(2 * np.pi * fundamental_hz * time)
        + 0.1 * np.sin(2 * np.pi * 2 * fundamental_hz * time)
    ).astype(np.float32)
    band = compute_band_spectrum(samples, sample_rate_hz=FS_HZ, rbw_hz=50.0, band_low_hz=500.0)
    table = harmonic_table(band.frequencies_hz, band.psd_v2_per_hz, fundamental_hz)
    assert table, "в полосе 3 кГц–3 МГц обязаны найтись гармоники 512 Гц"
    for marker in table:
        verify_scalar(
            marker.frequency_hz,
            expected=marker.order * fundamental_hz,
            absolute_tolerance=1e-9,
            rationale="Частота гармоники — целое кратное основной по определению.",
        )
        assert np.isfinite(marker.level_db), "уровень гармоники обязан быть конечным"
    assert table[0].order == 2, "таблица начинается с H2"
    assert all(marker.order <= 40 for marker in table), "таблица ограничена H40"


def test_band_rms_matches_tone_power() -> None:
    """СКЗ полосы для чистого тона равно A/√2 (истина — мощность тона A²/2)."""
    band = compute_band_spectrum(_tone(5_040.0), sample_rate_hz=FS_HZ, rbw_hz=50.0)
    verify_scalar(
        band_rms_v(
            band.frequencies_hz,
            band.psd_v2_per_hz,
            resolution_hz=band.resolution_hz,
            low_hz=band.band_low_hz,
            high_hz=band.band_high_hz,
        ),
        expected=TONE_RMS_V,
        absolute_tolerance=0.03 * TONE_RMS_V,
        rationale=(
            "Интеграл PSD вокруг тона равен A²/2 при плотностном скейле; 3% покрывают "
            "конечную ширину полосы и float32-округление (та же норма, что в B1)."
        ),
    )


def level_at_db_for_arrays(
    frequencies_hz: np.ndarray, psd_v2_per_hz: np.ndarray, frequency_hz: float
) -> float:
    """Уровень через BandSpectrum-обёртку, чтобы тест шёл через публичный контракт."""
    spectrum = BandSpectrum(
        frequencies_hz=np.asarray(frequencies_hz, dtype=np.float64),
        psd_v2_per_hz=np.asarray(psd_v2_per_hz, dtype=np.float64),
        resolution_hz=10.0,
        band_low_hz=float(frequencies_hz[0]),
        band_high_hz=float(frequencies_hz[-1]),
        peaks=(),
    )
    return level_at_db(spectrum, frequency_hz)


def frequency_at_for_arrays(
    frequencies_hz: np.ndarray, psd_v2_per_hz: np.ndarray, frequency_hz: float
) -> float:
    """Частота через BandSpectrum-обёртку, чтобы тест шёл через публичный контракт."""
    spectrum = BandSpectrum(
        frequencies_hz=np.asarray(frequencies_hz, dtype=np.float64),
        psd_v2_per_hz=np.asarray(psd_v2_per_hz, dtype=np.float64),
        resolution_hz=10.0,
        band_low_hz=float(frequencies_hz[0]),
        band_high_hz=float(frequencies_hz[-1]),
        peaks=(),
    )
    return frequency_at(spectrum, frequency_hz)
