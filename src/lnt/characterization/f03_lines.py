"""Поконные линии F03: кандидаты IHG и субгармоник на синхронной сетке."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.harmonics.constants import DFT_BINS_PER_HARMONIC, EPS_LEVEL, H_MAX

type Float64Array = NDArray[np.float64]

_MIN_CONFLICT_LINES: Final = 2

#: Пол энергии: бин с RMS ниже порога вырожденности — численный ноль, а не линия.
#: Та же конвенция, что ``h1 < EPS_LEVEL`` в ``harmonics/detector.py:134``.
RMS_FLOOR_V: Final = EPS_LEVEL

__all__ = [
    "RMS_FLOOR_V",
    "Line",
    "candidate_bins",
    "detect_window_lines",
    "harmonic_bins",
    "rms_power_spectrum",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class Line:
    """Значимая линия одного синхронного окна."""

    peak_bin: int
    center_hz: float
    amplitude_v: float
    width_hz: float
    margin_db: float
    group_bins: tuple[int, ...]
    ambiguous: bool


def harmonic_bins(n_bins: int) -> frozenset[int]:
    """Бины гармоник ``k = 10h`` внутри спектра."""
    return frozenset(
        h * DFT_BINS_PER_HARMONIC for h in range(1, H_MAX + 1) if h * DFT_BINS_PER_HARMONIC < n_bins
    )


def candidate_bins(n_bins: int, subharmonic_orders: tuple[int, ...]) -> tuple[int, ...]:
    """IHG-бины между гармониками без ±1 бина каждой гармоники плюс субгармоники.

    Границы ``lo = 10h + 2 .. hi = 10(h+1) − 2`` дословно из ``detector.py:119-131``;
    субгармоника ``f1/order`` ложится в ближайший бин ``round(10/order)`` (F03-5).
    """
    out: set[int] = set()
    for h in range(1, H_MAX):
        lo = h * DFT_BINS_PER_HARMONIC + 2
        hi = min((h + 1) * DFT_BINS_PER_HARMONIC - 2, n_bins - 1)
        for k in range(lo, hi + 1):
            if k >= 0:
                out.add(k)
    harmonics = harmonic_bins(n_bins)
    for order in subharmonic_orders:
        k = round(DFT_BINS_PER_HARMONIC / float(order))
        if 0 <= k < n_bins and k not in harmonics:
            out.add(k)
    return tuple(sorted(out))


def rms_power_spectrum(resampled: Float64Array) -> Float64Array:
    """Мощность бинов в вольтах RMS: ``|X|·√2/N``, DC и Найквист поправлены.

    Конвенция дословно из ``harmonics/detector.py:99-105`` (F03-3).
    """
    n = int(resampled.size)
    spectrum = np.fft.rfft(resampled)
    rms = np.abs(spectrum).astype(np.float64) * math.sqrt(2.0) / float(n)
    rms[0] /= math.sqrt(2.0)
    if rms.size > 1 and n % 2 == 0:
        rms[-1] /= math.sqrt(2.0)
    return rms * rms


def _local_median(power: Float64Array, k: int, harmonics: frozenset[int], count: int) -> float:
    """Медиана ``count`` ближайших негармонических бинов (F03-6)."""
    pool: list[float] = []
    distance = 1
    while len(pool) < count and distance < int(power.size):
        for other in (k - distance, k + distance):
            if 0 <= other < int(power.size) and other not in harmonics and other != k:
                pool.append(float(power[other]))
                if len(pool) == count:
                    break
        distance += 1
    if not pool:
        return 0.0
    return float(np.median(np.asarray(pool)))


def _centroid_hz(group: tuple[int, ...], power: Float64Array, f1_hz: float) -> float:
    """Энергоцентроид группы в герцах измеренной сетки (F03-2, F03-7)."""
    total = float(np.sum(power[np.asarray(group)]))
    if total <= 0.0:
        return float(group[len(group) // 2]) * float(f1_hz) / DFT_BINS_PER_HARMONIC
    weighted = float(np.sum(np.asarray(group, dtype=np.float64) * power[np.asarray(group)]))
    return weighted / total * float(f1_hz) / DFT_BINS_PER_HARMONIC


def _half_edge(
    power: Float64Array,
    peak: int,
    half: float,
    harmonics: frozenset[int],
    step: int,
) -> float | None:
    """Граница половинной мощности линейной интерполяцией между бинами.

    Формула дословно из ``features/spectral.py:126-147``. Стена — гармонический
    бин или край спектра: утечка ушла за группу, граница неоднозначна (F03-11).
    """
    position = peak
    while 0 <= position + step < int(power.size):
        neighbor = position + step
        if neighbor in harmonics:
            return None
        if float(power[neighbor]) <= half:
            inside = float(power[position])
            outside = float(power[neighbor])
            if inside <= outside:
                return None
            fraction = (inside - half) / (inside - outside)
            return float(position) + fraction * float(step)
        position = neighbor
    return None


def _build_line(
    group: tuple[int, ...],
    power: Float64Array,
    f1_hz: float,
    window_s: float,
    harmonics: frozenset[int],
) -> Line:
    """Линия по связной группе значимых бинов: центроид, RSS-амплитуда, ширина."""
    peak = max(group, key=lambda k: float(power[k]))
    half = float(power[peak]) / 2.0
    left = _half_edge(power, peak, half, harmonics, -1)
    right = _half_edge(power, peak, half, harmonics, 1)
    bin_hz = float(f1_hz) / DFT_BINS_PER_HARMONIC
    if left is None or right is None:
        width = 1.0 / float(window_s)
        ambiguous = True
    else:
        width = max((right - left) * bin_hz, 1.0 / float(window_s))
        ambiguous = False
    amplitude = float(math.sqrt(max(float(np.sum(power[np.asarray(group)])), 0.0)))
    return Line(
        peak_bin=peak,
        center_hz=_centroid_hz(group, power, f1_hz),
        amplitude_v=amplitude,
        width_hz=width,
        margin_db=0.0,
        group_bins=group,
        ambiguous=ambiguous,
    )


def detect_window_lines(  # noqa: PLR0913 - объявленные гейты рецепта
    power: Float64Array,
    *,
    f1_hz: float,
    window_s: float,
    detection_margin_db: float,
    local_median_bin_count: int,
    subharmonic_orders: tuple[int, ...],
) -> tuple[tuple[Line, ...], bool]:
    """Значимые линии окна и флаг ``below_resolution``.

    Значимость: мощность выше пола ``RMS_FLOOR_V`` и на ``detection_margin_db``
    выше локальной медианы (F03-6). Линии ближе одного измеренного бина
    ``f1/10`` снимаются обе; энергия в гард-бинах ±1 гармоники тоже
    ``below_resolution`` (F03-10). Возвращает уцелевшие линии и флаг окна.
    """
    n_bins = int(power.size)
    harmonics = harmonic_bins(n_bins)
    floor_power = RMS_FLOOR_V * RMS_FLOOR_V
    candidates = candidate_bins(n_bins, subharmonic_orders)
    significant: list[int] = []
    margins: dict[int, float] = {}
    for k in candidates:
        level = float(power[k])
        if not level > floor_power:
            continue
        median = _local_median(power, k, harmonics, int(local_median_bin_count))
        if not median > 0.0:
            continue
        margin = 10.0 * float(np.log10(level / median))
        if margin >= float(detection_margin_db):
            significant.append(k)
            margins[k] = margin
    groups = _runs(significant)
    lines = [
        _with_margin(_build_line(group, power, f1_hz, window_s, harmonics), margins)
        for group in groups
    ]
    below = _guard_energy(
        power, harmonics, floor_power, detection_margin_db, local_median_bin_count
    )
    kept, conflict = _resolve_conflicts(lines, f1_hz)
    return kept, below or conflict


def _with_margin(line: Line, margins: dict[int, float]) -> Line:
    """Проставить запас пикового бина группы."""
    return Line(
        peak_bin=line.peak_bin,
        center_hz=line.center_hz,
        amplitude_v=line.amplitude_v,
        width_hz=line.width_hz,
        margin_db=margins.get(line.peak_bin, 0.0),
        group_bins=line.group_bins,
        ambiguous=line.ambiguous,
    )


def _runs(bins: list[int]) -> list[tuple[int, ...]]:
    """Связные прогоны значимых бинов; каждый прогон — одна линия."""
    groups: list[tuple[int, ...]] = []
    current: list[int] = []
    for k in bins:
        if current and k != current[-1] + 1:
            groups.append(tuple(current))
            current = []
        current.append(k)
    if current:
        groups.append(tuple(current))
    return groups


def _guard_energy(
    power: Float64Array,
    harmonics: frozenset[int],
    floor_power: float,
    detection_margin_db: float,
    local_median_bin_count: int,
) -> bool:
    """Энергия в гард-бинах ±1 гармоники: неразрешённая линия у гармоники."""
    for h in sorted(harmonics):
        for guard in (h - 1, h + 1):
            if not 0 <= guard < int(power.size) or guard in harmonics:
                continue
            level = float(power[guard])
            if not level > floor_power:
                continue
            median = _local_median(power, guard, harmonics, int(local_median_bin_count))
            if median > 0.0 and 10.0 * float(np.log10(level / median)) >= float(
                detection_margin_db
            ):
                return True
    return False


def _resolve_conflicts(lines: list[Line], f1_hz: float) -> tuple[tuple[Line, ...], bool]:
    """Пары линий ближе одного измеренного бина снимаются обе (F03-10)."""
    if len(lines) < _MIN_CONFLICT_LINES:
        return tuple(lines), False
    limit = float(f1_hz) / DFT_BINS_PER_HARMONIC
    bad = set()
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if abs(lines[i].center_hz - lines[j].center_hz) < limit:
                bad.add(i)
                bad.add(j)
    kept = tuple(line for index, line in enumerate(lines) if index not in bad)
    return kept, bool(bad)
