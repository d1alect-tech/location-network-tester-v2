"""Маркеры спектра B3: уточнённый readout, гармоники H2–H40, мощность полосы.

Readout уточняется параболической интерполяцией по трём бинам в шкале дБ:
вершина параболы даёт поправку частоты в пределах ±0.5 бина и компенсацию
scalloping уровня вверх от ближайшего бина. Крайние бины сетки отдаются
без поправки. Гармоники и мощность полосы повторяют BandRms-норму
плотностного PSD (интеграл PSD по полосе), движок усреднения не затрагивается.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError

Float64Array = NDArray[np.float64]

MAX_HARMONIC_ORDER = 40
_FIRST_HARMONIC_ORDER = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class HarmonicMarker:
    """Строка таблицы гармоник: порядок, частота-кратное, уточнённый уровень."""

    order: int
    frequency_hz: float
    level_db: float


def refined_level_db(
    frequencies_hz: Float64Array,
    psd_v2_per_hz: Float64Array,
    frequency_hz: float,
) -> float:
    """Уровень PSD (дБ отн. 1 В²/Гц) с параболической поправкой вершины."""
    index = _nearest_index(frequencies_hz, frequency_hz)
    psd_db = 10.0 * np.log10(np.maximum(psd_v2_per_hz, 1e-30))
    if index == 0 or index >= psd_db.size - 1:
        return float(psd_db[index])
    _, gain_db = _parabolic_correction(
        float(psd_db[index - 1]), float(psd_db[index]), float(psd_db[index + 1])
    )
    return float(psd_db[index]) + gain_db


def refined_frequency_hz(
    frequencies_hz: Float64Array,
    psd_v2_per_hz: Float64Array,
    frequency_hz: float,
) -> float:
    """Частота вершины пика рядом с заданной (поправка в пределах ±0.5 бина)."""
    index = _nearest_index(frequencies_hz, frequency_hz)
    if index == 0 or index >= frequencies_hz.size - 1:
        return float(frequencies_hz[index])
    psd_db = 10.0 * np.log10(np.maximum(psd_v2_per_hz, 1e-30))
    delta_bins, _ = _parabolic_correction(
        float(psd_db[index - 1]), float(psd_db[index]), float(psd_db[index + 1])
    )
    step_hz = float(frequencies_hz[index + 1] - frequencies_hz[index])
    if not math.isfinite(step_hz) or step_hz <= 0.0:
        return float(frequencies_hz[index])
    return float(frequencies_hz[index]) + delta_bins * step_hz


def harmonic_table(
    frequencies_hz: Float64Array,
    psd_v2_per_hz: Float64Array,
    fundamental_hz: float,
    *,
    max_order: int = MAX_HARMONIC_ORDER,
) -> tuple[HarmonicMarker, ...]:
    """Строит таблицу гармоник H2–H40 от основной частоты (уровни уточнены)."""
    if not math.isfinite(fundamental_hz) or fundamental_hz <= 0.0:
        return ()
    if frequencies_hz.size == 0 or max_order < _FIRST_HARMONIC_ORDER:
        return ()
    low_hz = float(frequencies_hz[0])
    high_hz = float(frequencies_hz[-1])
    markers: list[HarmonicMarker] = []
    for order in range(_FIRST_HARMONIC_ORDER, max_order + 1):
        harmonic_hz = order * fundamental_hz
        if harmonic_hz < low_hz or harmonic_hz > high_hz:
            continue
        level_db = refined_level_db(frequencies_hz, psd_v2_per_hz, harmonic_hz)
        if not math.isfinite(level_db):
            continue
        markers.append(HarmonicMarker(order=order, frequency_hz=harmonic_hz, level_db=level_db))
    return tuple(markers)


def band_rms_v(
    frequencies_hz: Float64Array,
    psd_v2_per_hz: Float64Array,
    *,
    resolution_hz: float,
    low_hz: float,
    high_hz: float,
) -> float:
    """СКЗ напряжения в полосе: sqrt(Σ PSD · df) — та же норма, что BandRms."""
    if not math.isfinite(resolution_hz) or resolution_hz <= 0.0:
        raise InputError(f"разрешение сетки обязано быть > 0, получено {resolution_hz!r}")
    if not low_hz < high_hz:
        raise InputError(f"пустая полоса мощности: {low_hz!r}..{high_hz!r}")
    mask = (frequencies_hz >= low_hz) & (frequencies_hz <= high_hz)
    if int(mask.sum()) == 0:
        raise InputError(f"полоса {low_hz:.0f}..{high_hz:.0f} Гц вне сетки спектра")
    power_v2 = float(np.sum(np.maximum(psd_v2_per_hz[mask], 0.0)) * resolution_hz)
    return math.sqrt(max(power_v2, 0.0))


def _nearest_index(frequencies_hz: Float64Array, frequency_hz: float) -> int:
    if frequencies_hz.size == 0:
        raise InputError("пустая сетка частот спектра")
    return int(np.argmin(np.abs(frequencies_hz - frequency_hz)))


def _parabolic_correction(db_minus: float, db_center: float, db_plus: float) -> tuple[float, float]:
    """Возвращает (поправка_бинов ±0.5, добавка_дБ) вершины параболы в дБ."""
    if not all(math.isfinite(value) for value in (db_minus, db_center, db_plus)):
        return (0.0, 0.0)
    denominator = db_minus - 2.0 * db_center + db_plus
    if denominator >= 0.0:
        return (0.0, 0.0)
    delta_bins = 0.5 * (db_minus - db_plus) / denominator
    delta_bins = max(-0.5, min(0.5, delta_bins))
    gain_db = -0.25 * (db_minus - db_plus) * delta_bins
    return (delta_bins, max(gain_db, 0.0))
