"""Детерминированное слежение за пиками между окнами и захватами."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from lnt.features.errors import FeatureSchemaError


class TrackPointState(StrEnum):
    """Доступность точки trajectory."""

    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"


class TrackState(StrEnum):
    """Состояние траектории после последнего окна."""

    ACTIVE = "active"
    ENDED = "ended"


@dataclass(frozen=True, slots=True)
class QualifiedPeak:
    """Квалифицированное наблюдение частоты пика."""

    band_name: str
    frequency_hz: float


@dataclass(frozen=True, slots=True, kw_only=True)
class PeakObservation:
    """Все квалифицированные пики одного окна или захвата."""

    window_id: str
    time_s: float
    peaks: tuple[QualifiedPeak, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackPoint:
    """Наблюдаемая или явно недоступная точка trajectory."""

    window_id: str
    time_s: float
    frequency_hz: float | None
    state: TrackPointState
    reason_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PeakTrack:
    """Стабильно идентифицированная последовательность пика."""

    track_id: str
    band_name: str
    points: tuple[TrackPoint, ...]
    state: TrackState


@dataclass(slots=True)
class _TrackBuilder:
    """Мутабельный аккумулятор последовательного алгоритма tracking."""

    band_name: str
    points: list[TrackPoint]
    active: bool = True


def track_peak_trajectories(
    observations: tuple[PeakObservation, ...], *, tolerance_hz: float
) -> tuple[PeakTrack, ...]:
    """Сопоставляет ближайшие пики в пределах допуска без интерполяции пропусков."""
    if not math.isfinite(tolerance_hz) or tolerance_hz <= 0.0:
        raise FeatureSchemaError("признаки: tolerance_hz должен быть конечным и > 0")
    builders: list[_TrackBuilder] = []
    for observation in observations:
        unmatched = set(range(len(observation.peaks)))
        for builder in builders:
            if not builder.active:
                continue
            last_frequency = builder.points[-1].frequency_hz
            candidates = tuple(
                (abs(peak.frequency_hz - last_frequency), index)
                for index, peak in enumerate(observation.peaks)
                if index in unmatched
                and peak.band_name == builder.band_name
                and last_frequency is not None
                and abs(peak.frequency_hz - last_frequency) <= tolerance_hz
            )
            if candidates:
                _, index = min(candidates)
                peak = observation.peaks[index]
                unmatched.remove(index)
                builder.points.append(_observed_point(observation, peak))
            else:
                builder.points.append(
                    TrackPoint(
                        window_id=observation.window_id,
                        time_s=observation.time_s,
                        frequency_hz=None,
                        state=TrackPointState.UNAVAILABLE,
                        reason_code="peak_not_observed",
                    )
                )
                builder.active = False
        for index in sorted(unmatched, key=lambda item: observation.peaks[item].frequency_hz):
            peak = observation.peaks[index]
            builders.append(
                _TrackBuilder(band_name=peak.band_name, points=[_observed_point(observation, peak)])
            )
    return tuple(
        PeakTrack(
            track_id=f"track-{index:04d}",
            band_name=builder.band_name,
            points=tuple(builder.points),
            state=TrackState.ACTIVE if builder.active else TrackState.ENDED,
        )
        for index, builder in enumerate(builders, start=1)
    )


def _observed_point(observation: PeakObservation, peak: QualifiedPeak) -> TrackPoint:
    return TrackPoint(
        window_id=observation.window_id,
        time_s=observation.time_s,
        frequency_hz=peak.frequency_hz,
        state=TrackPointState.OBSERVED,
        reason_code=None,
    )
