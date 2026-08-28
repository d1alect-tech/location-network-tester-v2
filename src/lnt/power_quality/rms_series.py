"""Потоковый расчёт RMS полупериодов сети на ограниченных блоках памяти.

Вход — mmap-представление float32 (срез mmap копирует только срез). Все
пересечения нуля (подвыборочная интерполяция, концепт needles) и суммы квадратов
ищутся в блоках ``chunk_samples``; между блоками переносятся последнее значение
и накопленная сумма квадратов. Полная запись в float64 не материализуется:
префиксные суммы извлекаются только в индексах границ полупериодов.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError

Float64Array = NDArray[np.float64]
FloatArray = NDArray[np.floating]
DEFAULT_CHUNK_SAMPLES = 1_048_576
MIN_CROSSINGS = 3
_MIN_DISTINCT_POSITIONS: Final = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class HalfCycleRmsSeries:
    """Ряд RMS по полупериодам: центры окон, значения и границы (в секундах)."""

    times_s: Float64Array
    rms_v: Float64Array
    edges_s: Float64Array


def detect_half_cycle_rms(
    samples_view: FloatArray,
    *,
    line_frequency_hz: float,
    chunk_samples: int = DEFAULT_CHUNK_SAMPLES,
) -> HalfCycleRmsSeries:
    """Считает ряд полупериодного RMS потоково, без полной развёртки float64.

    Границы полупериодов — все пересечения нуля с линейной интерполяцией;
    интегрирование ведётся по целочисленным окнам между округлёнными вверх
    границами через префиксные суммы квадратов (O(1) на окно). Частота
    дискретизации выводится из измеренного полупериода и номинальной частоты;
    хвост записи короче полутона закрывается границей конца записи.
    """
    _validate(samples_view, line_frequency_hz, chunk_samples)
    sample_count = int(np.asarray(samples_view).shape[0])
    bounds, positions, prefixes, total_sq = _stream_bounds_and_prefixes(
        samples_view, sample_count=sample_count, chunk_samples=chunk_samples
    )
    keep = _keep_mask(positions)
    bounds, positions, prefixes = bounds[keep], positions[keep], prefixes[keep]
    if positions.size < MIN_CROSSINGS:
        raise InputError("качество питания: запись короче двух полупериодов сети")
    half_step_samples = float(np.median(np.diff(positions)))
    sample_rate_hz = half_step_samples * 2.0 * line_frequency_hz
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("качество питания: не удалось оценить частоту дискретизации")
    if float(sample_count) - float(positions[-1]) >= 0.5 * half_step_samples:
        bounds = np.append(bounds, sample_count)
        positions = np.append(positions, float(sample_count))
        prefixes = np.append(prefixes, total_sq)
    widths = np.diff(bounds)
    sums = np.diff(prefixes)
    rms = np.sqrt(sums / np.maximum(widths, 1))
    edges_s = positions / sample_rate_hz
    return HalfCycleRmsSeries(
        times_s=(edges_s[:-1] + edges_s[1:]) / 2.0,
        rms_v=rms,
        edges_s=edges_s,
    )


def _keep_mask(positions: Float64Array) -> NDArray[np.bool_]:
    """Отбрасывает шумовые двойные пересечения у нуля: шаг меньше полутоны."""
    mask = np.ones(positions.size, dtype=np.bool_)
    if positions.size < _MIN_DISTINCT_POSITIONS:
        return mask
    half_step = 0.5 * float(np.median(np.diff(positions)))
    last = float(positions[0])
    for index in range(1, positions.size):
        if float(positions[index]) - last < half_step:
            mask[index] = False
            continue
        last = float(positions[index])
    return mask


def _validate(samples_view: FloatArray, line_frequency_hz: float, chunk_samples: int) -> None:
    view = np.asarray(samples_view)
    if view.ndim != 1 or view.shape[0] == 0:
        raise InputError("качество питания: требуется непустой одномерный ряд")
    if not math.isfinite(line_frequency_hz) or line_frequency_hz <= 0.0:
        raise InputError("качество питания: частота сети должна быть конечной и > 0")
    if chunk_samples <= 0:
        raise InputError("качество питания: размер блока должен быть > 0")


def _stream_bounds_and_prefixes(
    samples_view: FloatArray,
    *,
    sample_count: int,
    chunk_samples: int,
) -> tuple[NDArray[np.int64], Float64Array, Float64Array, float]:
    """Проходит запись блоками: границы полупериодов и суммы квадратов в них."""
    previous: float | None = None
    carry_sq = 0.0
    last_bound = 0
    pending: list[int] = []
    bounds: list[int] = []
    positions: list[float] = []
    prefixes: list[float] = []
    for start in range(0, sample_count, chunk_samples):
        stop = min(sample_count, start + chunk_samples)
        chunk = np.asarray(samples_view[start:stop], dtype=np.float64)
        if not bool(np.isfinite(chunk).all()):
            raise InputError("качество питания: ряд содержит нечисловые значения")
        cumsq = np.cumsum(chunk * chunk)
        base = start if previous is None else start - 1
        for local_value in _chunk_crossings(chunk, previous):
            position = base + float(local_value)
            bound = min(max(math.ceil(position), 1), sample_count)
            if bound > last_bound:
                last_bound = bound
                bounds.append(bound)
                positions.append(position)
                pending.append(bound)
        ready = sum(1 for bound in pending if bound < stop)
        prefixes.extend(carry_sq + float(cumsq[bound - start]) for bound in pending[:ready])
        del pending[:ready]
        carry_sq += float(cumsq[-1])
        previous = float(chunk[-1])
    prefixes.extend(carry_sq for _ in pending)
    return (
        np.asarray(bounds, dtype=np.int64),
        np.asarray(positions, dtype=np.float64),
        np.asarray(prefixes, dtype=np.float64),
        carry_sq,
    )


def _chunk_crossings(chunk: Float64Array, previous: float | None) -> Float64Array:
    """Локальные позиции всех пересечений нуля внутри блока (вверх и вниз)."""
    window = chunk if previous is None else np.concatenate((np.array([previous]), chunk))
    positive = window > 0.0
    hits = np.nonzero(positive[:-1] != positive[1:])[0]
    if hits.size == 0:
        return np.empty(0, dtype=np.float64)
    fractions = -window[hits] / (window[hits + 1] - window[hits])
    return hits.astype(np.float64) + fractions
