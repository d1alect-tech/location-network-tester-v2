"""Нормализованные измерительные блоки payload ``ripple.json`` v1.

Числовые серии и скаляры здесь всегда конечны; недоступные ветки несут
``null`` и пустые серии, без NaN/Infinity. Схема заморожена аудитом
2026-10-20: тайм-домен, интервалы, спектр и хранимые полосы.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from collections.abc import Mapping

    from lnt.ripple.metrics import IntervalStats

Float64Array = NDArray[np.float64]


def time_domain_available(
    *,
    mean_v: float,
    rms_ac_v: float,
    vpp_v: float,
) -> dict[str, object]:
    """Доступные time-domain метрики наблюдаемого (не DUT) плана."""
    return {
        "availability": "available",
        "reason_codes": [],
        "mean_v": float(mean_v),
        "rms_ac_v": float(rms_ac_v),
        "vpp_v": float(vpp_v),
    }


def unavailable_scalars(reason_codes: tuple[str, ...]) -> dict[str, object]:
    """Недоступные метрики: числа null, причины типовые, без фабрикации."""
    return {
        "availability": "unavailable",
        "reason_codes": list(reason_codes),
        "mean_v": None,
        "rms_ac_v": None,
        "vpp_v": None,
    }


def interval_payload(
    stats: IntervalStats,
    *,
    clip_low_count: int | None,
    clip_high_count: int | None,
) -> dict[str, object]:
    """Один интервал: исходные границы, полнота, ценз и метрики."""
    return {
        "start_index": int(stats.start_index),
        "end_index_exclusive": int(stats.end_index_exclusive),
        "sample_count": int(stats.sample_count),
        "complete": bool(stats.complete),
        "realized_duration_s": float(stats.realized_duration_s),
        "availability": stats.availability,
        "reason_codes": list(stats.reason_codes),
        "clip_low_count": clip_low_count,
        "clip_high_count": clip_high_count,
        "mean_v": stats.mean_v,
        "rms_ac_v": stats.rms_ac_v,
        "vpp_v": stats.vpp_v,
    }


def spectrum_settings(  # noqa: PLR0913 - один аргумент на поле замороженной схемы
    *,
    nperseg: int,
    max_chunk_samples: int,
    overlap_fraction: float,
    window: str,
    detector: str,
    resolution_hz: float,
    enbw_hz: float,
    segment_count: int | None,
) -> dict[str, object]:
    """Явные настройки Welch: запрошенная политика и реализованный прогон."""
    return {
        "nperseg": int(nperseg),
        "max_chunk_samples": int(max_chunk_samples),
        "overlap_fraction": float(overlap_fraction),
        "window": window,
        "detector": detector,
        "detrend": "constant",
        "scaling": "density",
        "resolution_hz": float(resolution_hz),
        "enbw_hz": float(enbw_hz),
        "segment_count": segment_count,
    }


def spectrum_available(  # noqa: PLR0913 - поля блоков схемы передаются явно
    *,
    settings: Mapping[str, object],
    used_sample_count: int,
    ignored_tail_samples: int,
    frequency_hz: Float64Array,
    psd_v2_per_hz: Float64Array,
    asd_v_per_sqrt_hz: Float64Array,
) -> dict[str, object]:
    """Доступный спектр: плотности сохранены как есть, без сглаживания."""
    return {
        "availability": "available",
        "reason_codes": [],
        "settings": dict(settings),
        "used_sample_count": int(used_sample_count),
        "ignored_tail_samples": int(ignored_tail_samples),
        "frequency_hz": [float(value) for value in frequency_hz],
        "psd_v2_per_hz": [float(value) for value in psd_v2_per_hz],
        "asd_v_per_sqrt_hz": [float(value) for value in asd_v_per_sqrt_hz],
    }


def spectrum_unavailable(
    *,
    settings: Mapping[str, object],
    reason_codes: tuple[str, ...],
) -> dict[str, object]:
    """Недоступный спектр: серии пусты, статус явный."""
    return {
        "availability": "unavailable",
        "reason_codes": list(reason_codes),
        "settings": dict(settings),
        "used_sample_count": None,
        "ignored_tail_samples": None,
        "frequency_hz": [],
        "psd_v2_per_hz": [],
        "asd_v_per_sqrt_hz": [],
    }


def band_available(  # noqa: PLR0913 - один аргумент на поле замороженной схемы
    *,
    band_id: str,
    low_hz: float,
    high_hz: float,
    first_center_hz: float,
    last_center_hz: float,
    bin_count: int,
    rms_v: float,
) -> dict[str, object]:
    """Доступная полоса: прямоугольная сумма PSD * df, без второго ENBW."""
    return {
        "id": band_id,
        "low_hz": float(low_hz),
        "high_hz": float(high_hz),
        "first_center_hz": float(first_center_hz),
        "last_center_hz": float(last_center_hz),
        "bin_count": int(bin_count),
        "availability": "available",
        "reason_codes": [],
        "rms_v": float(rms_v),
    }


def band_unavailable(
    *,
    band_id: str,
    low_hz: float,
    high_hz: float,
    reason_codes: tuple[str, ...],
) -> dict[str, object]:
    """Недоступная полоса: запрошенные границы сохранены, числа null."""
    return {
        "id": band_id,
        "low_hz": float(low_hz),
        "high_hz": float(high_hz),
        "first_center_hz": None,
        "last_center_hz": None,
        "bin_count": None,
        "availability": "unavailable",
        "reason_codes": list(reason_codes),
        "rms_v": None,
    }
