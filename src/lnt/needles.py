"""Line-sync метрика иголок: σ_pk/μ_pk, P_async/P_sync, огибающая CH2.

Циклы сети выделяются по восходящим нулям CH2 (после НЧ-фильтра); CH1
режется на циклы и ресемплится на фазовую сетку. Синхронная часть — среднее
по циклам, асинхронная — остаток. Амплитуды иголок берутся из сырых отсчётов
в окне доминирующей фазы (без потерь ресемплинга).

Однокональный режим (``compute_needle_metrics_single``): опорного 50 Гц нет,
CH1 режется на номинальные окна 20 мс; фазозависимые метрики (P_sync/P_async,
частота сети, CV огибающей) честно недоступны (``None``).
"""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.errors import AnalysisError, SessionTooShortError

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]

MIN_CYCLES = 100
MIN_CROSSINGS = 2
PHASE_BINS = 4_096
FILTER_ORDER = 4
LF_LOWPASS_HZ = 200.0
HF_HIGHPASS_HZ = 3_000.0
MIN_LF_RMS_V = 0.05
MIN_LINE_HZ = 40.0
MAX_LINE_HZ = 70.0
PEAK_WINDOW_FRACTION = 0.03
POWER_EPS = 1e-30


class SyncSource(StrEnum):
    """Источник границ циклов сети: измеренный CH2 или номинальные окна 20 мс."""

    CH2 = "ch2"
    NOMINAL = "nominal"


@dataclass(frozen=True, slots=True, kw_only=True)
class NeedleMetrics:
    """Метрики line-sync иголок и НЧ-огибающей одной сессии.

    Фазозависимые поля — ``None`` в однокональном режиме (``sync_source=NOMINAL``).
    """

    sync_source: SyncSource
    cycles_analyzed: int
    line_frequency_hz: float | None
    needle_mean_v: float
    needle_sigma_ratio: float
    sync_power_v2: float | None
    async_power_v2: float | None
    async_sync_ratio: float | None
    lf_envelope_cv: float | None


def compute_needle_metrics(
    ch1: Float32Array,
    ch2: Float32Array,
    *,
    sample_rate_hz: float,
) -> NeedleMetrics:
    """Считает метрики иголок; CH1 — ВЧ-пробник, CH2 — форма 50 Гц."""
    hf = ch1.astype(np.float64)
    lf = ch2.astype(np.float64)
    rms = float(np.sqrt(np.mean(np.square(lf))))
    if rms < MIN_LF_RMS_V:
        raise AnalysisError(
            f"CH2 слишком слаб для синхронизации: RMS {rms:.4f} В < {MIN_LF_RMS_V} В",
        )
    positions = _rising_crossings(_apply_filter(lf, sample_rate_hz, LF_LOWPASS_HZ, "lowpass"))
    if positions.size < MIN_CROSSINGS:
        raise AnalysisError("CH2: не найдено ни одного полного цикла сети")
    line_frequency = sample_rate_hz / float(np.mean(np.diff(positions)))
    if not MIN_LINE_HZ <= line_frequency <= MAX_LINE_HZ:
        raise AnalysisError(
            f"CH2: частота синхронизации {line_frequency:.1f} Гц вне диапазона сети",
        )
    cycles_found = positions.size - 1
    if cycles_found < MIN_CYCLES:
        raise SessionTooShortError(cycles_found=cycles_found, cycles_required=MIN_CYCLES)
    hf_clean = _apply_filter(hf, sample_rate_hz, HF_HIGHPASS_HZ, "highpass")
    cycles = _resample_cycles(hf_clean, positions)
    mean_cycle = cycles.mean(axis=0)
    residual = cycles - mean_cycle
    sync_power = float(np.mean(np.square(mean_cycle)))
    async_power = float(np.mean(np.square(residual)))
    dominant_fraction = float(np.argmax(np.abs(mean_cycle))) / PHASE_BINS
    peaks = _needle_peaks(hf_clean, positions, dominant_fraction)
    needle_mean = float(np.mean(peaks))
    needle_sigma = float(np.std(peaks, ddof=1))
    lf_peaks = _cycle_maxima(lf, positions)
    return NeedleMetrics(
        sync_source=SyncSource.CH2,
        cycles_analyzed=cycles_found,
        line_frequency_hz=line_frequency,
        needle_mean_v=needle_mean,
        needle_sigma_ratio=needle_sigma / max(needle_mean, POWER_EPS),
        sync_power_v2=sync_power,
        async_power_v2=async_power,
        async_sync_ratio=async_power / max(sync_power, POWER_EPS),
        lf_envelope_cv=float(np.std(lf_peaks, ddof=1)) / max(float(np.mean(lf_peaks)), POWER_EPS),
    )


def compute_needle_metrics_single(
    ch1: Float32Array,
    *,
    sample_rate_hz: float,
    line_frequency_hz: float = 50.0,
) -> NeedleMetrics:
    """Считает метрики иголок без опорного CH2 по номинальным окнам сети.

    Пик берётся как максимум |CH1| в каждом окне длиной 1/f_сети;
    фазозависимые метрики недоступны и возвращаются как ``None``.
    """
    hf = ch1.astype(np.float64)
    samples_per_cycle = sample_rate_hz / line_frequency_hz
    cycle_count = int(hf.size / samples_per_cycle)
    if cycle_count < MIN_CYCLES:
        raise SessionTooShortError(cycles_found=cycle_count, cycles_required=MIN_CYCLES)
    hf_clean = _apply_filter(hf, sample_rate_hz, HF_HIGHPASS_HZ, "highpass")
    positions = np.arange(cycle_count + 1, dtype=np.float64) * samples_per_cycle
    peaks = np.empty(cycle_count, dtype=np.float64)
    for cycle_index in range(cycle_count):
        low = int(np.floor(positions[cycle_index]))
        high = min(hf_clean.size, int(np.ceil(positions[cycle_index + 1])) + 1)
        peaks[cycle_index] = float(np.max(np.abs(hf_clean[low:high])))
    needle_mean = float(np.mean(peaks))
    needle_sigma = float(np.std(peaks, ddof=1))
    return NeedleMetrics(
        sync_source=SyncSource.NOMINAL,
        cycles_analyzed=cycle_count,
        line_frequency_hz=None,
        needle_mean_v=needle_mean,
        needle_sigma_ratio=needle_sigma / max(needle_mean, POWER_EPS),
        sync_power_v2=None,
        async_power_v2=None,
        async_sync_ratio=None,
        lf_envelope_cv=None,
    )


def _apply_filter(
    samples: Float64Array,
    sample_rate_hz: float,
    cutoff_hz: float,
    kind: str,
) -> Float64Array:
    sos = signal.butter(FILTER_ORDER, cutoff_hz, btype=kind, fs=sample_rate_hz, output="sos")
    return np.asarray(signal.sosfiltfilt(sos, samples), dtype=np.float64)


def _rising_crossings(lf: Float64Array) -> Float64Array:
    below = lf[:-1] <= 0.0
    above = lf[1:] > 0.0
    indices = np.nonzero(below & above)[0]
    if indices.size == 0:
        return np.empty(0, dtype=np.float64)
    fractions = -lf[indices] / (lf[indices + 1] - lf[indices])
    return indices.astype(np.float64) + fractions


def _resample_cycles(hf: Float64Array, positions: Float64Array) -> Float64Array:
    cycle_count = positions.size - 1
    starts = positions[:-1]
    lengths = np.diff(positions)
    phase_grid = np.arange(PHASE_BINS, dtype=np.float64) / PHASE_BINS
    sample_points = starts[:, np.newaxis] + lengths[:, np.newaxis] * phase_grid[np.newaxis, :]
    flat = np.interp(sample_points.ravel(), np.arange(hf.size, dtype=np.float64), hf)
    return flat.reshape(cycle_count, PHASE_BINS)


def _needle_peaks(
    hf: Float64Array,
    positions: Float64Array,
    dominant_fraction: float,
) -> Float64Array:
    peaks = np.empty(positions.size - 1, dtype=np.float64)
    for cycle_index in range(positions.size - 1):
        start = positions[cycle_index]
        period = positions[cycle_index + 1] - start
        window_low = start + (dominant_fraction - PEAK_WINDOW_FRACTION) * period
        window_high = start + (dominant_fraction + PEAK_WINDOW_FRACTION) * period
        low = max(0, int(np.floor(window_low)))
        high = min(hf.size, int(np.ceil(window_high)) + 1)
        peaks[cycle_index] = float(np.max(np.abs(hf[low:high])))
    return peaks


def _cycle_maxima(lf: Float64Array, positions: Float64Array) -> Float64Array:
    maxima = np.empty(positions.size - 1, dtype=np.float64)
    for cycle_index in range(positions.size - 1):
        low = int(np.floor(positions[cycle_index]))
        high = min(lf.size, int(np.ceil(positions[cycle_index + 1])) + 1)
        maxima[cycle_index] = float(np.max(lf[low:high]))
    return maxima
