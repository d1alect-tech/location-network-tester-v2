"""Детектор нотчинга IEEE 519: глубина/площадь, лишние нули LF-огибающей."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.errors import InputError
from lnt.notching.models import (
    NOTCHING_VERSION,
    NotchEvent,
    NotchingInventory,
    NotchingSettings,
    notching_preset,
    notching_settings_hash,
)

FloatArray = NDArray[np.floating]
FILTER_ORDER: int = 4
# По одному фронту период не очертить — нужна хотя бы пара восходящих нулей.
_MIN_RISING_FOR_PERIOD: int = 2
# Минимум чанков для edge-guard и минимум точек/интервалов для оценки джиттера.
_MIN_SAMPLES_FOR_EDGE_GUARD: int = 4
_MIN_POSITIONS_FOR_JITTER: int = 3
_MIN_DIFFS_FOR_STD: int = 2


def detect_notching(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    settings: NotchingSettings | None = None,
    line_frequency_hz: float = 50.0,
) -> NotchingInventory:
    """Инвентаризует нотчи по отклонению от LF-огибающей и лишним нулям."""
    if settings is None:
        settings = notching_preset()
    _validate(samples, sample_rate_hz, line_frequency_hz, settings)
    arr = np.asarray(samples, dtype=np.float64)
    sample_count = int(arr.size)
    duration_s = sample_count / float(sample_rate_hz)
    lf = _lowpass(np.asarray(samples, dtype=np.float32), sample_rate_hz, settings.lowpass_hz)
    lf_rising = _rising_crossings(lf)
    raw_rising = _chunked_rising_crossings(samples, settings.chunk_samples)
    # Edge guard for spurious: ignore crossings within filter transient
    n = int(np.asarray(samples).size)
    edge_c = max(32, int(round(sample_rate_hz * 0.002)))  # noqa: RUF046
    edge_c = min(edge_c, n // 4) if n >= 4 else 0  # noqa: PLR2004
    if edge_c > 0:
        lf_rising = lf_rising[(lf_rising >= edge_c) & (lf_rising < n - edge_c)]
        raw_rising = raw_rising[(raw_rising >= edge_c) & (raw_rising < n - edge_c)]
    expected = int(lf_rising.size)
    observed = int(raw_rising.size)
    spurious = max(0, observed - expected)
    jitter_us = _jitter_us(raw_rising, sample_rate_hz)
    nominal_peak = _nominal_peak(lf, lf_rising)
    threshold_v = nominal_peak * settings.threshold_pct / 100.0
    notches = _scan_notches(arr, lf, sample_rate_hz, threshold_v, settings)
    # фильтр по минимальной ширине
    filtered = tuple(n for n in notches if n.duration_us >= settings.min_width_us)
    per_second = float(len(filtered)) / duration_s if duration_s > 0 else 0.0
    return NotchingInventory(
        schema_version=NOTCHING_VERSION,
        settings_hash=notching_settings_hash(settings),
        settings=settings,
        sample_rate_hz=float(sample_rate_hz),
        sample_count=sample_count,
        duration_s=duration_s,
        notch_count=len(filtered),
        notches_per_second=per_second,
        expected_crossings=expected,
        observed_crossings=observed,
        spurious_crossings=spurious,
        jitter_us=jitter_us,
        notches=filtered,
    )


def _validate(
    samples: FloatArray, sample_rate_hz: float, line_hz: float, settings: NotchingSettings
) -> None:
    view = np.asarray(samples)
    if view.ndim != 1 or view.size == 0:
        raise InputError("нотчинг: требуется непустой одномерный ряд")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise InputError("нотчинг: частота дискретизации должна быть конечной и >0")
    if not math.isfinite(line_hz) or line_hz <= 0:
        raise InputError("нотчинг: частота сети должна быть конечной и >0")
    if settings.chunk_samples <= 0:
        raise InputError("нотчинг: размер блока должен быть >0")


def _lowpass(
    samples: NDArray[np.float32], sample_rate_hz: float, cutoff_hz: float
) -> NDArray[np.float64]:
    sos = signal.butter(FILTER_ORDER, cutoff_hz, btype="lowpass", fs=sample_rate_hz, output="sos")
    wide = np.asarray(samples, dtype=np.float64)
    return np.asarray(signal.sosfiltfilt(sos, wide), dtype=np.float64)


def _rising_crossings(lf: NDArray[np.float64]) -> NDArray[np.float64]:
    below = lf[:-1] <= 0.0
    above = lf[1:] > 0.0
    indices = np.nonzero(below & above)[0]
    if indices.size == 0:
        return np.empty(0, dtype=np.float64)
    fractions = -lf[indices] / (lf[indices + 1] - lf[indices])
    return indices.astype(np.float64) + fractions


def _chunked_rising_crossings(samples: FloatArray, chunk_samples: int) -> NDArray[np.float64]:
    """Стриминговый подсчёт восходящих нулей блоками."""
    n = int(np.asarray(samples).size)
    out: list[float] = []
    prev: float | None = None
    for start in range(0, n, chunk_samples):
        stop = min(n, start + chunk_samples)
        chunk = np.asarray(samples[start:stop], dtype=np.float64)
        window = chunk if prev is None else np.concatenate((np.array([prev]), chunk))
        below = window[:-1] <= 0.0
        above = window[1:] > 0.0
        hits = np.nonzero(below & above)[0]
        if hits.size:
            fracs = -window[hits] / (window[hits + 1] - window[hits])
            base = start if prev is None else start - 1
            for h, f in zip(hits, fracs, strict=False):
                out.append(base + float(h) + float(f))
        prev = float(chunk[-1]) if chunk.size else prev
    return np.asarray(out, dtype=np.float64)


def _nominal_peak(lf: NDArray[np.float64], rising: NDArray[np.float64]) -> float:
    if rising.size < _MIN_RISING_FOR_PERIOD:
        return float(np.median(np.abs(lf))) * 1.2 if lf.size else 1.0
    maxima: list[float] = []
    for i in range(rising.size - 1):
        lo = math.floor(rising[i])
        hi = min(lf.size, math.ceil(rising[i + 1]) + 1)
        if hi > lo:
            maxima.append(float(np.max(np.abs(lf[lo:hi]))))
    if not maxima:
        return float(np.max(np.abs(lf))) if lf.size else 1.0
    return float(np.median(np.asarray(maxima)))


def _scan_notches(
    raw: NDArray[np.float64],
    lf: NDArray[np.float64],
    sample_rate_hz: float,
    threshold_v: float,
    settings: NotchingSettings,
) -> tuple[NotchEvent, ...]:
    """Chunked scan по отклонению |LF|-|raw| > порога."""
    n = int(raw.size)
    # Edge guard: ignore filter transient at boundaries (sosfiltfilt edge)
    edge = max(32, round(sample_rate_hz * 0.002))
    edge = min(edge, n // 4) if n >= _MIN_SAMPLES_FOR_EDGE_GUARD else 0
    intervals: list[tuple[int, int]] = []
    for start in range(0, n, settings.chunk_samples):
        stop = min(n, start + settings.chunk_samples)
        lf_chunk = lf[start:stop]
        raw_chunk = raw[start:stop]
        dev = np.abs(lf_chunk) - np.abs(raw_chunk)
        mask = dev > threshold_v
        # intervals локально
        padded = np.pad(mask, (1, 1), constant_values=False)
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        for s, e in edges.reshape(-1, 2):
            if mask[s]:
                intervals.append((start + int(s), start + int(e) - 1))
    merged = _merge_intervals(intervals)
    # Drop intervals touching edges (filter transient)
    if edge > 0:
        merged = [(s, e) for s, e in merged if s >= edge and e < n - edge]
    events: list[NotchEvent] = []
    dt = 1.0 / float(sample_rate_hz)
    for s, e in merged:
        block_dev = np.abs(lf[s : e + 1]) - np.abs(raw[s : e + 1])
        # только положительные отклонения уже, но на всякий
        block_dev = np.maximum(block_dev, 0.0)
        depth = float(np.max(block_dev)) if block_dev.size else 0.0
        area = float(np.sum(block_dev) * dt * 1e6)
        duration_us = float((e - s + 1) * dt * 1e6)
        events.append(
            NotchEvent(
                start_time_s=s * dt,
                end_time_s=(e + 1) * dt,
                duration_us=duration_us,
                depth_v=depth,
                area_v_us=area,
            )
        )
    return tuple(events)


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    intervals.sort()
    merged: list[list[int]] = [[intervals[0][0], intervals[0][1]]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(a, b) for a, b in merged]


def _jitter_us(positions: NDArray[np.float64], sample_rate_hz: float) -> float:
    if positions.size < _MIN_POSITIONS_FOR_JITTER:
        return 0.0
    diffs = np.diff(positions) / float(sample_rate_hz) * 1e6
    # std от медианы интервалов
    return float(np.std(diffs, ddof=1)) if diffs.size >= _MIN_DIFFS_FOR_STD else 0.0
