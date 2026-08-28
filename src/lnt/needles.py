"""Line-sync метрика иголок: σ_pk/μ_pk, P_async/P_sync, огибающая CH2.

Циклы сети выделяются по восходящим нулям CH2 (после НЧ-фильтра); CH1
режется на циклы и ресемплится на фазовую сетку. Синхронная часть — среднее
по циклам, асинхронная — остаток. Амплитуды иголок берутся из сырых отсчётов
в окне доминирующей фазы (без потерь ресемплинга).

Однокональный режим (``compute_needle_metrics_single``): опорного 50 Гц нет,
CH1 режется на номинальные окна 20 мс; фазозависимые метрики (P_sync/P_async,
частота сети, CV огибающей) честно недоступны (``None``).

Память (T17): тяжёлые ядра вынесены в ``_needle_memory`` — бутстрэп копит
статистики последовательными тиражами (O(пиков) вместо O(тиражи×пики)),
ресемплинг идёт батчами в два прохода (O(батча) вместо матрицы
циклы×4096). Остаточный пик — фильтрация: ``sosfiltfilt`` требует полных
f64-копий записи, транзиентно ~3×запись(f64) ≈ 6×запись(f32) на
фильтруемый канал; после фильтра устойчиво живёт один массив результата.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt._needle_memory import (
    PHASE_BINS,
    bootstrap_quantiles,
    chunked_rms,
    resample_mean_cycle,
    residual_async_power,
)
from lnt.errors import AnalysisError, SessionTooShortError

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]

MIN_CYCLES = 100
MIN_CROSSINGS = 2
FILTER_ORDER = 4
LF_LOWPASS_HZ = 200.0
HF_HIGHPASS_HZ = 3_000.0
MIN_LF_RMS_V = 0.05
MIN_LINE_HZ = 40.0
MAX_LINE_HZ = 70.0
PEAK_WINDOW_FRACTION = 0.03
POWER_EPS = 1e-30
BOOTSTRAP_SAMPLES: Final = 10_000
MIN_UNCERTAINTY_N: Final = 3
CONFIDENCE_LEVEL: Final = 0.95
INTERVAL_METHOD: Final = "seeded_cycle_bootstrap_percentile_95"


class SyncSource(StrEnum):
    """Источник границ циклов сети: измеренный CH2 или номинальные окна 20 мс."""

    CH2 = "ch2"
    NOMINAL = "nominal"


@dataclass(frozen=True, slots=True, kw_only=True)
class NeedleMetricInterval:
    """Двусторонний бутстрэп-интервал одной needle-оценки."""

    low: float
    high: float


@dataclass(frozen=True, slots=True, kw_only=True)
class NeedleMetricIntervalPair:
    """Маркированная 95%-неопределённость μ_pk и σ_pk/μ_pk по цикловым пикам."""

    method: str
    confidence_level: float
    needle_mean_v: NeedleMetricInterval
    needle_sigma_ratio: NeedleMetricInterval


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
    uncertainty: NeedleMetricIntervalPair | None = None


def compute_needle_metrics(
    ch1: Float32Array,
    ch2: Float32Array,
    *,
    sample_rate_hz: float,
    seed: int = 0,
) -> NeedleMetrics:
    """Считает метрики иголок; CH1 — ВЧ-пробник, CH2 — форма 50 Гц.

    ``seed`` управляет сеянным бутстрэпом 95%-интервалов (см.
    ``uncertainty``); при числе пиков ниже 3 интервал недоступен и
    ``uncertainty`` равен ``None``.
    """
    rms = chunked_rms(ch2)
    if rms < MIN_LF_RMS_V:
        raise AnalysisError(
            f"CH2 слишком слаб для синхронизации: RMS {rms:.4f} В < {MIN_LF_RMS_V} В",
        )
    lf_clean = _apply_filter(ch2, sample_rate_hz, LF_LOWPASS_HZ, "lowpass")
    positions = _rising_crossings(lf_clean)
    del lf_clean  # отфильтрованный CH2 больше не нужен — освободить до фильтра CH1
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
    hf_clean = _apply_filter(ch1, sample_rate_hz, HF_HIGHPASS_HZ, "highpass")
    mean_cycle = resample_mean_cycle(hf_clean, positions)
    sync_power = float(np.mean(np.square(mean_cycle)))
    async_power = residual_async_power(hf_clean, positions, mean_cycle)
    dominant_fraction = float(np.argmax(np.abs(mean_cycle))) / PHASE_BINS
    peaks = _needle_peaks(hf_clean, positions, dominant_fraction)
    needle_mean = float(np.mean(peaks))
    needle_sigma = float(np.std(peaks, ddof=1))
    lf_peaks = _cycle_maxima(ch2, positions)
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
        uncertainty=_bootstrap_uncertainty(peaks, seed=seed),
    )


def compute_needle_metrics_single(
    ch1: Float32Array,
    *,
    sample_rate_hz: float,
    line_frequency_hz: float = 50.0,
    seed: int = 0,
) -> NeedleMetrics:
    """Считает метрики иголок без опорного CH2 по номинальным окнам сети.

    Пик берётся как максимум |CH1| в каждом окне длиной 1/f_сети;
    фазозависимые метрики недоступны и возвращаются как ``None``.
    Максимумы окон служат выборкой для сеянного бутстрэпа ``uncertainty``;
    при числе пиков ниже 3 он равен ``None``.
    """
    samples_per_cycle = sample_rate_hz / line_frequency_hz
    cycle_count = int(ch1.size / samples_per_cycle)
    if cycle_count < MIN_CYCLES:
        raise SessionTooShortError(cycles_found=cycle_count, cycles_required=MIN_CYCLES)
    hf_clean = _apply_filter(ch1, sample_rate_hz, HF_HIGHPASS_HZ, "highpass")
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
        uncertainty=_bootstrap_uncertainty(peaks, seed=seed),
    )


def _bootstrap_uncertainty(
    peaks: Float64Array,
    *,
    seed: int,
) -> NeedleMetricIntervalPair | None:
    """Сеянный бутстрэп 95%-CI для μ_pk и σ_pk/μ_pk; ``None`` при n < 3."""
    if int(peaks.size) < MIN_UNCERTAINTY_N:
        return None
    mean_low, mean_high, ratio_low, ratio_high = bootstrap_quantiles(
        peaks,
        seed=seed,
        samples=BOOTSTRAP_SAMPLES,
        eps=POWER_EPS,
    )
    return NeedleMetricIntervalPair(
        method=INTERVAL_METHOD,
        confidence_level=CONFIDENCE_LEVEL,
        needle_mean_v=NeedleMetricInterval(low=mean_low, high=mean_high),
        needle_sigma_ratio=NeedleMetricInterval(low=ratio_low, high=ratio_high),
    )


def _apply_filter(
    samples: Float32Array,
    sample_rate_hz: float,
    cutoff_hz: float,
    kind: str,
) -> Float64Array:
    """Фильтр Баттерворта нулевой фазы; f64-копия входа умирает на выходе.

    Единственное место с полноразмерной f64-копией записи: sosfiltfilt
    считает только в double, а расширение f32→f64 точное.
    """
    sos = signal.butter(FILTER_ORDER, cutoff_hz, btype=kind, fs=sample_rate_hz, output="sos")
    wide = np.asarray(samples, dtype=np.float64)
    return np.asarray(signal.sosfiltfilt(sos, wide), dtype=np.float64)


def _rising_crossings(lf: Float64Array) -> Float64Array:
    below = lf[:-1] <= 0.0
    above = lf[1:] > 0.0
    indices = np.nonzero(below & above)[0]
    if indices.size == 0:
        return np.empty(0, dtype=np.float64)
    fractions = -lf[indices] / (lf[indices + 1] - lf[indices])
    return indices.astype(np.float64) + fractions


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


def _cycle_maxima(lf: Float32Array, positions: Float64Array) -> Float64Array:
    """Максимумы сырого CH2 по циклам, побитово равные прежним значениям.

    Расширение f32→f64 точное, поэтому пооконное приведение эквивалентно
    прежнему цельномассивному.
    """
    maxima = np.empty(positions.size - 1, dtype=np.float64)
    for cycle_index in range(positions.size - 1):
        low = int(np.floor(positions[cycle_index]))
        high = min(lf.size, int(np.ceil(positions[cycle_index + 1])) + 1)
        maxima[cycle_index] = float(np.max(lf[low:high].astype(np.float64)))
    return maxima
