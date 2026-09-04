"""Детектор качества питания: события отклонений и ступени RVC по кривой ITIC.

Полупериоды вне полосы 90..110 % от опорного номинала группируются в события
(короткие внутриполосные промежутки склеиваются настраиваемым допуском).
Границы событий уточняются до долей полупериода по энергетической доле краевого
окна; вердикт выставляется по огибающей ITIC 2000 на уточнённой длительности.
Номинал самоссылочный — робастная медиана RMS записи (шкала пробника неизвестна).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.errors import InputError
from lnt.power_quality.constants import (
    ITIC_ENVELOPE,
    ITIC_STEADY_BAND,
    POWER_QUALITY_VERSION,
    SEMI_F47_ENVELOPE,
    SEMI_F47_STEADY_BAND,
)
from lnt.power_quality.models import (
    EventKind,
    HalfCycleSummaryDict,
    IticRegion,
    PowerQualityInventory,
    RvcDirection,
    RvcEvent,
    Tolerance,
    VoltageEvent,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.power_quality.rms_series import Float64Array, HalfCycleRmsSeries
    from lnt.power_quality.settings import PowerQualitySettings

EPSILON: Final = 1e-9
_MIN_PLATEAU_VALUES: Final = 3

_KIND_REGION: Final[dict[EventKind, IticRegion]] = {
    EventKind.DROPOUT: IticRegion.DROPOUT,
    EventKind.SAG: IticRegion.SAG,
    EventKind.SWELL: IticRegion.SWELL,
}


def detect_power_quality(
    rms_series: HalfCycleRmsSeries, *, settings: PowerQualitySettings
) -> PowerQualityInventory:
    """Инвентаризирует события отклонений и ступени RVC детерминированно."""
    rms = rms_series.rms_v
    if rms.size == 0:
        raise InputError("качество питания: ряд полупериодов пуст")
    nominal = float(np.median(rms))
    if not math.isfinite(nominal) or nominal <= 0.0:
        raise InputError("качество питания: номинальный RMS вырожден")
    ratios = rms / nominal
    flagged = (ratios < settings.band_low_pct / 100.0) | (ratios > settings.band_high_pct / 100.0)
    context = _Context(
        edges_s=rms_series.edges_s, ratios=ratios, flagged=flagged, settings=settings
    )
    events = tuple(
        _build_event(context, run, nominal=nominal)
        for run in _merged_runs(flagged, settings.merge_gap_half_cycles)
    )
    return PowerQualityInventory(
        schema_version=POWER_QUALITY_VERSION,
        settings_hash=_settings_hash(settings),
        settings=settings,
        half_cycle_rms_summary=_summary(rms, nominal),
        events=events,
        rvc_events=_detect_rvc(ratios, rms_series.edges_s, settings),
    )


def _merged_runs(flagged: NDArray[np.bool_], max_gap: int) -> list[tuple[int, int]]:
    """Склеивает индексные интервалы вне полосы с допуском коротких промежутков."""
    indices = np.flatnonzero(flagged)
    if indices.size == 0:
        return []
    runs: list[list[int]] = [[int(indices[0]), int(indices[0])]]
    for index in indices[1:]:
        if int(index) - runs[-1][1] - 1 <= max_gap:
            runs[-1][1] = int(index)
        else:
            runs.append([int(index), int(index)])
    return [(start, end) for start, end in runs]


@dataclass(frozen=True, slots=True)
class _Context:
    """Общие данные анализа полупериодов, разделяемые построителями событий."""

    edges_s: Float64Array
    ratios: NDArray[np.float64]
    flagged: NDArray[np.bool_]
    settings: PowerQualitySettings


def _build_event(context: _Context, run: tuple[int, int], *, nominal: float) -> VoltageEvent:
    """Классифицирует один прогон: род, глубина, границы с долями полупериода."""
    start_index, end_index = run
    values = context.ratios[start_index : end_index + 1][
        context.flagged[start_index : end_index + 1]
    ]
    low, high = float(np.min(values)), float(np.max(values))
    downward = (1.0 - low) > (high - 1.0)
    extreme = low if downward else high
    plateau = float(np.median(values[1:-1])) if values.size >= _MIN_PLATEAU_VALUES else extreme
    start_time = _edge_time(context, start_index, plateau, leaving=False)
    end_time = _edge_time(context, end_index, plateau, leaving=True)
    kind = (
        EventKind.DROPOUT
        if downward and extreme * 100.0 < context.settings.dropout_max_pct
        else (EventKind.SAG if downward else EventKind.SWELL)
    )
    low_frac, high_frac = _envelope(end_time - start_time)
    tolerated = low_frac - EPSILON <= extreme <= high_frac + EPSILON
    return VoltageEvent(
        start_time_s=start_time,
        end_time_s=end_time,
        duration_s=end_time - start_time,
        kind=kind,
        depth_pct=(1.0 - extreme) * 100.0 if downward else (extreme - 1.0) * 100.0,
        nominal_rms_v=nominal,
        verdict=Tolerance.IN_TOLERANCE if tolerated else Tolerance.OUT_OF_TOLERANCE,
        itic_region=_KIND_REGION[kind],
    )


def _edge_time(context: _Context, index: int, plateau: float, *, leaving: bool) -> float:
    """Уточняет край события до доли полупериода по энергетической доле окна."""
    edges_s, ratios, flagged = context.edges_s, context.ratios, context.flagged
    width = float(edges_s[index + 1] - edges_s[index])
    observed = float(ratios[index]) ** 2
    if leaving:
        neighbour = (
            1.0 if index + 1 >= ratios.size or flagged[index + 1] else float(ratios[index + 1])
        )
        normal_fraction = _split_fraction(observed, plateau**2, neighbour**2)
        return float(edges_s[index]) + (1.0 - normal_fraction) * width
    neighbour = 1.0 if index == 0 or flagged[index - 1] else float(ratios[index - 1])
    fraction = _split_fraction(observed, neighbour**2, plateau**2)
    return float(edges_s[index]) + (1.0 - fraction) * width


def _split_fraction(observed_sq: float, base_sq: float, alt_sq: float) -> float:
    """Доля окна в состоянии ``alt``; при вырожденном знаменателе — ноль."""
    denominator = alt_sq - base_sq
    if abs(denominator) <= EPSILON:
        return 0.0
    return min(max((observed_sq - base_sq) / denominator, 0.0), 1.0)


def _envelope(duration_s: float) -> tuple[float, float]:
    """Огибающая ITIC 2000: допуски (нижний, верхний) для данной длительности."""
    for duration_limit, low_frac, high_frac in ITIC_ENVELOPE:
        if duration_s <= duration_limit + EPSILON:
            return (low_frac, high_frac)
    return ITIC_STEADY_BAND


def semi_f47_envelope(duration_s: float) -> tuple[float, float]:
    """Огибающая SEMI-F47: допуски (нижний, верхний) для данной длительности."""
    for duration_limit, low_frac, high_frac in SEMI_F47_ENVELOPE:
        if duration_s <= duration_limit + EPSILON:
            return (low_frac, high_frac)
    return SEMI_F47_STEADY_BAND


def evaluate_tolerance(duration_s: float, ratio: float, *, curve: str = "itic") -> Tolerance:
    """Вердикт по кривой ITIC/SEMI-F47; при нехватке данных — unavailable."""
    if not math.isfinite(duration_s) or not math.isfinite(ratio):
        return Tolerance.UNAVAILABLE
    if duration_s < 0.0:
        return Tolerance.UNAVAILABLE
    if curve not in ("itic", "semi_f47"):
        return Tolerance.UNAVAILABLE
    low, high = semi_f47_envelope(duration_s) if curve == "semi_f47" else _envelope(duration_s)
    tolerated = low - EPSILON <= ratio <= high + EPSILON
    return Tolerance.IN_TOLERANCE if tolerated else Tolerance.OUT_OF_TOLERANCE


def _detect_rvc(
    ratios: NDArray[np.float64], edges_s: Float64Array, settings: PowerQualitySettings
) -> tuple[RvcEvent, ...]:
    """Находит подтверждённые ступени между соседними полупериодными RMS."""
    threshold = settings.rvc_step_threshold_pct / 100.0
    tolerance = settings.rvc_sustain_tolerance_pct / 100.0
    span = settings.rvc_sustain_cycles * 2
    steps: list[RvcEvent] = []
    index = 1
    while index < ratios.size:
        delta = float(ratios[index] - ratios[index - 1])
        window = ratios[index : min(index + span, ratios.size)]
        sustained = (
            abs(delta) >= threshold
            and window.size > 0
            and float(np.max(np.abs(window - ratios[index]))) <= tolerance
        )
        if sustained:
            steps.append(
                RvcEvent(
                    step_time_s=float(edges_s[index]),
                    delta_pct=delta * 100.0,
                    direction=RvcDirection.UP if delta > 0.0 else RvcDirection.DOWN,
                    sustained_cycles=max(1, int(window.size) // 2),
                )
            )
            index += int(window.size)
            continue
        index += 1
    return tuple(steps)


def _summary(rms: NDArray[np.float64], nominal: float) -> HalfCycleSummaryDict:
    """Сводка ряда полупериодных RMS для инвентаря."""
    return {
        "count": int(rms.size),
        "nominal_rms_v": nominal,
        "min": float(np.min(rms)),
        "max": float(np.max(rms)),
    }


def _settings_hash(settings: PowerQualitySettings) -> str:
    """SHA-256 канонического JSON полных настроек (как в событиях)."""
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
