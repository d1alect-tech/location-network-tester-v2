"""EFT/burst детектор 61000-4-4: Hilbert envelope + 15 мс / 300 мс."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.burst.models import (
    BURST_VERSION,
    BurstEvent,
    BurstInventory,
    BurstSequence,
    BurstSettings,
    burst_preset,
    burst_settings_hash,
)
from lnt.errors import InputError

FloatArray = NDArray[np.floating]
_OVERLAP: int = 4096
_MAD_TO_SIGMA: float = 1.4826
_SIGMA_MULT: float = 4.0
_MIN_THRESHOLD: float = 1e-12
_GAP_MS: float = 2.0
_FALLBACK_PERCENTILE: float = 95.0
# Период повторения считается по пачкам внутри серии: одна пачка его не задаёт.
_MIN_BURSTS_FOR_PERIOD: int = 2


def detect_bursts(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    settings: BurstSettings | None = None,
) -> BurstInventory:
    """Находит bursts по порогу огибающей Hilbert, группирует 15 мс/300 мс."""
    if settings is None:
        settings = burst_preset()
    _validate(samples, sample_rate_hz, settings)
    arr = np.asarray(samples, dtype=np.float64)
    n = int(arr.size)
    duration_s = n / float(sample_rate_hz)
    envelope = _chunked_envelope(arr, settings.chunk_samples)
    median = float(np.median(envelope))
    mad = float(np.median(np.abs(envelope - median)))
    sigma = mad * _MAD_TO_SIGMA
    thresh_factor = median * settings.threshold_factor if median > 0 else sigma * 3.0
    thresh_sigma = median + _SIGMA_MULT * sigma
    threshold = max(thresh_factor, thresh_sigma)
    if threshold <= _MIN_THRESHOLD:
        threshold = float(np.percentile(envelope, _FALLBACK_PERCENTILE)) or 0.1
    mask = envelope > threshold
    raw_intervals = _mask_to_intervals(mask)
    gap_samples = round(_GAP_MS * 1e-3 * sample_rate_hz)
    merged = _merge_with_gap(raw_intervals, gap_samples)
    # фильтр по длительности burst
    bursts: list[BurstEvent] = []
    dt = 1.0 / float(sample_rate_hz)
    min_s = settings.min_burst_duration_ms * 1e-3
    max_s = settings.max_burst_duration_ms * 1e-3
    for s, e in merged:
        dur_s = (e - s + 1) * dt
        if not (min_s <= dur_s <= max_s):
            continue
        peak = float(np.max(envelope[s : e + 1]))
        bursts.append(
            BurstEvent(
                start_time_s=s * dt,
                end_time_s=(e + 1) * dt,
                duration_ms=dur_s * 1e3,
                peak_envelope_v=peak,
            )
        )
    # сортировка по времени
    bursts.sort(key=lambda b: b.start_time_s)
    sequences = _group_sequences(bursts, settings.burst_period_ms)
    per_second = float(len(bursts)) / duration_s if duration_s > 0 else 0.0
    return BurstInventory(
        schema_version=BURST_VERSION,
        settings_hash=burst_settings_hash(settings),
        settings=settings,
        sample_rate_hz=float(sample_rate_hz),
        sample_count=n,
        duration_s=duration_s,
        burst_count=len(bursts),
        bursts_per_second=per_second,
        sequence_count=len(sequences),
        bursts=tuple(bursts),
        sequences=tuple(sequences),
    )


def _validate(samples: FloatArray, fs: float, settings: BurstSettings) -> None:
    view = np.asarray(samples)
    if view.ndim != 1 or view.size == 0:
        raise InputError("burst: требуется непустой одномерный ряд")
    if not math.isfinite(fs) or fs <= 0:
        raise InputError("burst: частота дискретизации некорректна")
    if settings.chunk_samples <= 0:
        raise InputError("burst: размер блока должен быть >0")


def _chunked_envelope(arr: NDArray[np.float64], chunk_samples: int) -> NDArray[np.float64]:
    """Hilbert огибающая по блокам с overlap."""
    n = int(arr.size)
    out = np.empty(n, dtype=np.float64)
    overlap = min(_OVERLAP, chunk_samples // 4)
    pos = 0
    while pos < n:
        stop = min(n, pos + chunk_samples)
        # расширенный блок
        ext_start = max(0, pos - overlap)
        ext_stop = min(n, stop + overlap)
        chunk = arr[ext_start:ext_stop]
        # hilbert via scipy
        analytic = signal.hilbert(chunk)
        env_ext = np.abs(analytic)
        # копируем центральную часть
        copy_start = pos - ext_start
        copy_len = stop - pos
        out[pos:stop] = env_ext[copy_start : copy_start + copy_len]
        pos = stop
    return out


def _mask_to_intervals(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    padded = np.pad(mask, (1, 1), constant_values=False)
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    intervals: list[tuple[int, int]] = []
    for s, e in edges.reshape(-1, 2):
        if mask[int(s)]:
            intervals.append((int(s), int(e) - 1))
    return intervals


def _merge_with_gap(intervals: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    if not intervals:
        return []
    intervals.sort()
    merged: list[list[int]] = [[intervals[0][0], intervals[0][1]]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1] + gap + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(a, b) for a, b in merged]


def _group_sequences(bursts: list[BurstEvent], period_ms: float) -> list[BurstSequence]:
    if not bursts:
        return []
    # gap >1.5*period начинает новую последовательность
    gap_s = period_ms * 1.5e-3
    groups: list[list[BurstEvent]] = [[bursts[0]]]
    for b in bursts[1:]:
        prev = groups[-1][-1]
        if (b.start_time_s - prev.end_time_s) <= gap_s:
            groups[-1].append(b)
        else:
            groups.append([b])
    seqs: list[BurstSequence] = []
    for g in groups:
        start = g[0].start_time_s
        end = g[-1].end_time_s
        count = len(g)
        if count >= _MIN_BURSTS_FOR_PERIOD:
            periods = [g[i + 1].start_time_s - g[i].start_time_s for i in range(count - 1)]
            avg_ms = float(np.mean(periods)) * 1e3
        else:
            avg_ms = period_ms
        seqs.append(
            BurstSequence(
                start_time_s=start,
                end_time_s=end,
                burst_count=count,
                period_ms=avg_ms,
            )
        )
    return seqs
