"""F18: declared triad grid, exact-FFT-bin mapping и count cap."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f18_contract import (
    ARTIFACT_LIMIT,
    EXACT_BIN_RELATIVE_TOLERANCE,
    TRIAD_ABOVE_NYQUIST,
    TRIAD_OFF_GRID,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]
type Triad = tuple[float, float, float]

_ABOVE: Final = 0
_OFF_GRID: Final = 1
_MEASURABLE: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class F18TriadGrid:
    """Объявленные триады, их классификация и столбцы коэффициентов."""

    low_hz: Float64Array
    high_hz: Float64Array
    sum_hz: Float64Array
    measurable: BoolArray
    distinct_bins: Int64Array
    rows: Int64Array
    effective_high_hz: float
    declared_count: int
    dropped_count: int
    off_grid_count: int
    above_nyquist_count: int


def declared_triads(base_frequencies_hz: Sequence[float], maximum_triads: int) -> tuple[Triad, ...]:
    """Все неупорядоченные пары f1<=f2 с суммой; кап ограничивает ЧИСЛО, не диапазон."""
    if maximum_triads <= 0:
        raise ValueError("F18 maximum_triads must be positive")
    base = sorted(float(value) for value in base_frequencies_hz)
    if any(value <= 0.0 or not math.isfinite(value) for value in base):
        raise ValueError("F18 base frequencies must be finite and positive")
    triads = [(low, high, low + high) for first, low in enumerate(base) for high in base[first:]]
    return tuple(triads[: int(maximum_triads)])


def build_triad_grid(  # noqa: PLR0913 - полный declared input surface
    base_frequencies_hz: Sequence[float],
    *,
    segment_samples: int,
    sample_rate_hz: float,
    analysis_low_hz: float,
    analysis_high_hz: float,
    nyquist_fraction_max: float,
    maximum_triads: int,
) -> F18TriadGrid:
    """Классифицировать каждую declared триаду до единого FFT-прохода и суррогатов."""
    triads = declared_triads(base_frequencies_hz, maximum_triads)
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0 or segment_samples <= 0:
        raise ValueError("F18 triad grid needs a positive sample rate and segment length")
    if not 0.0 <= analysis_low_hz < analysis_high_hz:
        raise ValueError("F18 analysis band is outside its declared domain")
    effective_high_hz = min(float(analysis_high_hz), float(nyquist_fraction_max) * sample_rate_hz)
    triad_bins: tuple[tuple[int | None, ...], ...] = tuple(
        tuple(exact_bin(value, segment_samples, sample_rate_hz) for value in triad)
        for triad in triads
    )
    states = [
        _classify(triad, bins, analysis_low_hz, effective_high_hz)
        for triad, bins in zip(triads, triad_bins, strict=True)
    ]
    measurable = np.asarray([state == _MEASURABLE for state in states], dtype=np.bool_)
    distinct_bins, rows = _rows(triad_bins, measurable)
    return F18TriadGrid(
        low_hz=np.asarray([triad[0] for triad in triads], dtype=np.float64),
        high_hz=np.asarray([triad[1] for triad in triads], dtype=np.float64),
        sum_hz=np.asarray([triad[2] for triad in triads], dtype=np.float64),
        measurable=measurable,
        distinct_bins=distinct_bins,
        rows=rows,
        effective_high_hz=effective_high_hz,
        declared_count=len(triads),
        dropped_count=_dropped(base_frequencies_hz, maximum_triads),
        off_grid_count=states.count(_OFF_GRID),
        above_nyquist_count=states.count(_ABOVE),
    )


def exact_bin(frequency_hz: float, segment_samples: int, sample_rate_hz: float) -> int | None:
    """Вернуть индекс rfft-бина, только если частота попадает в него точно."""
    scaled = frequency_hz * segment_samples / sample_rate_hz
    index = round(scaled)
    if index < 1 or index > segment_samples // 2:
        return None
    if abs(scaled - index) > EXACT_BIN_RELATIVE_TOLERANCE * max(1.0, abs(float(index))):
        return None
    return index


def grid_reason_codes(grid: F18TriadGrid) -> set[str]:
    """Каждая отклонённая или обрезанная declared триада обязана быть объявлена."""
    reasons: set[str] = set()
    if grid.off_grid_count:
        reasons.add(TRIAD_OFF_GRID)
    if grid.above_nyquist_count:
        reasons.add(TRIAD_ABOVE_NYQUIST)
    if grid.dropped_count:
        reasons.add(ARTIFACT_LIMIT)
    return reasons


def _classify(triad: Triad, bins: tuple[int | None, ...], low_hz: float, high_hz: float) -> int:
    """Сначала Nyquist clamp, потом exact FFT bins: причины объявлены разными кодами."""
    low, high, total = triad
    if total > high_hz or low < low_hz or high > high_hz:
        return _ABOVE
    if any(index is None for index in bins):
        return _OFF_GRID
    return _MEASURABLE


def _rows(
    triad_bins: tuple[tuple[int | None, ...], ...], measurable: BoolArray
) -> tuple[Int64Array, Int64Array]:
    """Раз distinct-бины и (K,3) индексы столбцов; -1 у не измеряемых триад."""
    rows = np.full((measurable.size, 3), -1, dtype=np.int64)
    order: list[int] = []
    for triad_index in np.flatnonzero(measurable).tolist():
        bins = triad_bins[int(triad_index)]
        for column, value in enumerate(bins):
            index = -1 if value is None else int(value)
            if index not in order:
                order.append(index)
            rows[int(triad_index), column] = order.index(index)
    return np.asarray(order, dtype=np.int64), rows


def _dropped(base_frequencies_hz: Sequence[float], maximum_triads: int) -> int:
    total = len(base_frequencies_hz) * (len(base_frequencies_hz) + 1) // 2
    return max(0, total - int(maximum_triads))
