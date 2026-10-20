"""Чистые метрики полного ряда риппла.

Модуль не знает про клиппинг, калибровку или доступность железа:
некорректный математический вход даёт :class:`lnt.errors.InputError`,
а QC/availability остаются у вызывающего слоя.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from lnt.errors import InputError

Float64Array = NDArray[np.float64]
Availability = Literal["available", "unavailable"]
ReasonCode = Literal["insufficient_samples"]

_MIN_SAMPLES_FOR_RMS: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class IntervalStats:
    """Статистика одного исходного интервала без сжатия временной сетки."""

    start_index: int
    end_index_exclusive: int
    sample_count: int
    complete: bool
    realized_duration_s: float
    availability: Availability
    reason_codes: tuple[ReasonCode, ...]
    mean_v: float | None
    rms_ac_v: float | None
    vpp_v: float | None


def mean_v(samples: ArrayLike) -> float:
    """Возвращает среднее арифметическое в float64."""
    values = _checked_samples(samples)
    return _mean(values)


def rms_ac_v(samples: ArrayLike) -> float:
    """Возвращает population RMS переменной составляющей (центрированный two-pass)."""
    values = _checked_samples(samples)
    _require_two(values)
    return _rms_ac(values, _mean(values))


def vpp_v(samples: ArrayLike) -> float:
    """Возвращает фактический размах max-min по всем отсчётам."""
    values = _checked_samples(samples)
    _require_two(values)
    return _vpp(values)


def interval_stats(samples: ArrayLike, fs: float, window_s: float) -> tuple[IntervalStats, ...]:
    """Делит ряд на неперекрывающиеся интервалы с исходными индексами.

    Окно округляется как ``round(fs * window_s)`` и требует >= 2 отсчётов.
    Хвост сохраняет истинную длину и ``complete=False``; хвост из одного
    отсчёта помечается unavailable, числа не фабрикуются.
    """
    values = _checked_samples(samples, allow_empty=True)
    window_samples = _window_samples(fs, window_s)
    intervals: list[IntervalStats] = []
    start = 0
    total = values.size
    while start + window_samples <= total:
        end = start + window_samples
        intervals.append(_interval(values, start, end, fs, complete=True))
        start = end
    if start < total:
        intervals.append(_interval(values, start, total, fs, complete=False))
    return tuple(intervals)


def _checked_samples(samples: ArrayLike, *, allow_empty: bool = False) -> Float64Array:
    try:
        raw = np.asarray(samples)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InputError("риппл: samples должны быть числовыми") from exc
    if np.iscomplexobj(raw):
        raise InputError("риппл: комплексные samples не поддерживаются")
    try:
        values = np.asarray(raw, dtype=np.float64)
    except OverflowError as exc:
        raise InputError("риппл: samples не помещаются в диапазон float64") from exc
    except (TypeError, ValueError) as exc:
        raise InputError("риппл: samples должны быть числовыми") from exc
    if values.ndim != 1:
        raise InputError("риппл: samples должны быть 1-D")
    if not allow_empty and values.size == 0:
        raise InputError("риппл: samples не должны быть пустыми")
    if not np.isfinite(values).all():
        raise InputError("риппл: samples должны быть конечными")
    return values


def _require_two(values: Float64Array) -> None:
    if values.size < _MIN_SAMPLES_FOR_RMS:
        raise InputError("риппл: для RMS/Vpp требуется >= 2 отсчётов")


def _mean(values: Float64Array) -> float:
    result = float(np.mean(values))
    if not math.isfinite(result):
        raise InputError("риппл: среднее вышло за конечный диапазон float64")
    return result


def _rms_ac(values: Float64Array, mean_value: float) -> float:
    centered = values - mean_value
    result = float(np.sqrt(np.mean(centered * centered)))
    if not math.isfinite(result):
        raise InputError("риппл: RMS AC вышел за конечный диапазон float64")
    return result


def _vpp(values: Float64Array) -> float:
    result = float(np.max(values) - np.min(values))
    if not math.isfinite(result):
        raise InputError("риппл: Vpp вышел за конечный диапазон float64")
    return result


def _window_samples(fs: float, window_s: float) -> int:
    if not math.isfinite(fs) or fs <= 0:
        raise InputError("риппл: частота дискретизации должна быть конечной и > 0")
    if not math.isfinite(window_s) or window_s <= 0:
        raise InputError("риппл: окно должно быть конечным и > 0")
    requested_samples = fs * window_s
    if not math.isfinite(requested_samples):
        raise InputError("риппл: окно вышло за конечный диапазон float64")
    window_samples = round(requested_samples)
    if window_samples < _MIN_SAMPLES_FOR_RMS:
        raise InputError("риппл: окно должно содержать >= 2 отсчётов")
    return window_samples


def _interval(
    values: Float64Array,
    start: int,
    end: int,
    fs: float,
    *,
    complete: bool,
) -> IntervalStats:
    count = end - start
    duration = count / fs
    if not math.isfinite(duration):
        raise InputError("риппл: длительность интервала вышла за конечный диапазон float64")
    if count < _MIN_SAMPLES_FOR_RMS:
        return IntervalStats(
            start_index=start,
            end_index_exclusive=end,
            sample_count=count,
            complete=complete,
            realized_duration_s=duration,
            availability="unavailable",
            reason_codes=("insufficient_samples",),
            mean_v=None,
            rms_ac_v=None,
            vpp_v=None,
        )
    segment = values[start:end]
    mean_value = _mean(segment)
    return IntervalStats(
        start_index=start,
        end_index_exclusive=end,
        sample_count=count,
        complete=complete,
        realized_duration_s=duration,
        availability="available",
        reason_codes=(),
        mean_v=mean_value,
        rms_ac_v=_rms_ac(segment, mean_value),
        vpp_v=_vpp(segment),
    )
