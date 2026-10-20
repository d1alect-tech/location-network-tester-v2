"""QC выбранного спана ripple-среза: ценз, установление, непрерывность.

Правила контракта 2026-10-20 (B1): клиппинг и не-конечные отсчёты никогда не
удаляются и не сжимают таймлайн; загрязнённые публичные спаны получают
недоступность с кодом, чистые точные под-спаны остаются доступными только
при известном положении попаданий.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.adc_calibration import apply_adc_calibration
from lnt.errors import InputError
from lnt.types import SessionSource

from .ripple_options import SettlingDeclaration

if TYPE_CHECKING:
    from lnt.ripple.adapter import AdapterSpec
    from lnt.session_store import LoadedSession
    from lnt.types import SessionManifest

SETTLING_BASIS_PRECONNECTED: Final = "capture_start_assuming_preconnected"
SETTLING_BASIS_UNKNOWN: Final = "settling_unknown"
CONTINUITY_SYNTHETIC: Final = "synthetic_exact"
CONTINUITY_HOST_UNVERIFIED: Final = "host_contiguous_unverified"
CONTINUITY_REASON_HOST: Final = "host_contiguous_unverified"

#: Оценки, при которых положения рельсов не локализуемы: спан целиком грязен.
_UNLOCALIZED_ASSESSMENTS: Final = frozenset(
    {
        "clipping_unknown",
        "rail_hits_present_unlocalizable",
        "clip_census_inconsistent",
    }
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClipCensus:
    """Ценз рельсов: счётчики, область действия и (не)известные позиции.

    ``low_positions``/``high_positions`` — абсолютные индексы внутри
    выбранного спана; ``None`` означает «попадания есть, но не локализуемы»,
    пустой кортеж — попаданий нет. Счётчики относятся к полной записи.
    """

    low_count: int | None
    high_count: int | None
    scope: str | None
    assessment: str
    low_positions: tuple[int, ...] | None
    high_positions: tuple[int, ...] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SpanQc:
    """Решение QC по исходному таймлайну; числа не фабрикуются."""

    sample_start_index: int
    sample_end_index_exclusive: int
    excluded_prefix_samples: int
    settling_prefix_samples_nominal: int
    settling_basis: str
    continuity_status: str
    continuity_reason_codes: tuple[str, ...]
    dropped_samples: int | None
    clipping_assessment: str
    clip_count_scope: str | None
    clip_low_count: int | None
    clip_high_count: int | None
    nonfinite_count: int
    record_nonfinite_count: int
    span_reason_codes: tuple[str, ...]
    span_nonfinite_positions: tuple[int, ...]
    span_clip_low_positions: tuple[int, ...] | None
    span_clip_high_positions: tuple[int, ...] | None

    @property
    def span_count(self) -> int:
        """Длина выбранного спана в исходных индексах."""
        return self.sample_end_index_exclusive - self.sample_start_index


def span_qc(
    *,
    session: LoadedSession,
    adapter: AdapterSpec,
    settling: SettlingDeclaration,
) -> SpanQc:
    """Считает ценз и границы спана для одной сессии ripple-среза."""
    manifest = session.manifest
    ch1 = np.asarray(session.ch1)
    total = int(ch1.size)
    prefix, settling_basis = _settling_prefix(
        adapter=adapter,
        settling=settling,
        sample_rate_hz=manifest.sample_rate_hz,
    )
    start = min(prefix, total)
    reasons: list[str] = []
    if start >= total:
        reasons.append("empty_span")
    if settling_basis == SETTLING_BASIS_UNKNOWN:
        reasons.append("settling_unknown")
    record_nonfinite_count = int(np.count_nonzero(~np.isfinite(ch1)))
    nonfinite_positions = _nonfinite_positions(ch1, start, total)
    if nonfinite_positions:
        reasons.append("nonfinite_samples")
    census = _clip_census(
        ch1=ch1,
        manifest=manifest,
        start=start,
    )
    if census.low_positions or census.high_positions:
        reasons.append("clipped")
    elif census.assessment in _UNLOCALIZED_ASSESSMENTS:
        reasons.append("clipping_unknown")
        if census.assessment == "clip_census_inconsistent":
            reasons.append("clip_census_inconsistent")
    synthetic = manifest.source is SessionSource.SYNTHETIC
    continuity_status = CONTINUITY_SYNTHETIC if synthetic else CONTINUITY_HOST_UNVERIFIED
    continuity_reasons = () if synthetic else (CONTINUITY_REASON_HOST,)
    return SpanQc(
        sample_start_index=start,
        sample_end_index_exclusive=total,
        excluded_prefix_samples=start,
        settling_prefix_samples_nominal=prefix,
        settling_basis=settling_basis,
        continuity_status=continuity_status,
        continuity_reason_codes=continuity_reasons,
        dropped_samples=0 if synthetic else None,
        clipping_assessment=census.assessment,
        clip_count_scope=census.scope,
        clip_low_count=census.low_count,
        clip_high_count=census.high_count,
        nonfinite_count=len(nonfinite_positions),
        record_nonfinite_count=record_nonfinite_count,
        span_reason_codes=tuple(reasons),
        span_nonfinite_positions=nonfinite_positions,
        span_clip_low_positions=census.low_positions,
        span_clip_high_positions=census.high_positions,
    )


def _settling_prefix(
    *,
    adapter: AdapterSpec,
    settling: SettlingDeclaration,
    sample_rate_hz: float,
) -> tuple[int, str]:
    """Префикс установления существует только при объявленной процедуре."""
    if settling is SettlingDeclaration.PRECONNECTED and adapter.transfer_available:
        prefix = adapter.settle_samples(sample_rate_hz)
        if prefix is None:
            raise InputError(
                "ripple: transfer_available без модели установления — инвариант адаптера"
            )
        return prefix, SETTLING_BASIS_PRECONNECTED
    return 0, SETTLING_BASIS_UNKNOWN


def _nonfinite_positions(ch1: np.ndarray, start: int, total: int) -> tuple[int, ...]:
    """Абсолютные индексы не-конечных отсчётов внутри выбранного спана."""
    if start >= total:
        return ()
    finite = np.isfinite(ch1[start:total])
    return tuple(int(value) + start for value in np.flatnonzero(~finite))


def _clip_census(
    *,
    ch1: np.ndarray,
    manifest: SessionManifest,
    start: int,
) -> ClipCensus:
    """Ценз клиппинга: агрегат телеметрии сверяется с конверсией рельсов.

    Синтетика — ценз неприменим. Без телеметрии — ``clipping_unknown``.
    Калиброванный путь не сохраняет коэффициенты: нулевой агрегат сертифицирует
    запись, ненулевой не локализуем. Некалиброванный путь восстанавливает
    конечные точки той же float32-конверсией; расхождение с агрегатом —
    ``clip_census_inconsistent`` и отказ от чисел (fail closed).
    """
    if manifest.source is SessionSource.SYNTHETIC:
        return ClipCensus(
            low_count=None,
            high_count=None,
            scope=None,
            assessment="not_applicable_synthetic",
            low_positions=(),
            high_positions=(),
        )
    telemetry = manifest.acquisition_telemetry
    if telemetry is None:
        return ClipCensus(
            low_count=None,
            high_count=None,
            scope=None,
            assessment="clipping_unknown",
            low_positions=None,
            high_positions=None,
        )
    aggregate_low = telemetry.ch1_clip_low_count
    aggregate_high = telemetry.ch1_clip_high_count
    if telemetry.calibration_used:
        clipped = aggregate_low + aggregate_high > 0
        return ClipCensus(
            low_count=aggregate_low,
            high_count=aggregate_high,
            scope="aggregate_saved_record_telemetry",
            assessment="rail_hits_present_unlocalizable" if clipped else "no_rail_hits",
            low_positions=None if clipped else (),
            high_positions=None if clipped else (),
        )
    low_endpoint, high_endpoint = _reconstructed_endpoints(manifest)
    low_mask = np.asarray(ch1 <= low_endpoint)
    high_mask = np.asarray(ch1 >= high_endpoint)
    low_positions = tuple(int(value) for value in np.flatnonzero(low_mask))
    high_positions = tuple(int(value) for value in np.flatnonzero(high_mask))
    if len(low_positions) != aggregate_low or len(high_positions) != aggregate_high:
        return ClipCensus(
            low_count=aggregate_low,
            high_count=aggregate_high,
            scope="aggregate_saved_record_telemetry",
            assessment="clip_census_inconsistent",
            low_positions=None,
            high_positions=None,
        )
    span_low = tuple(position for position in low_positions if position >= start)
    span_high = tuple(position for position in high_positions if position >= start)
    assessment = (
        "rail_hits_present_localized" if low_positions or high_positions else "no_rail_hits"
    )
    return ClipCensus(
        low_count=aggregate_low,
        high_count=aggregate_high,
        scope="float32_endpoints_from_manifest_conversion",
        assessment=assessment,
        low_positions=span_low,
        high_positions=span_high,
    )


def _reconstructed_endpoints(manifest: SessionManifest) -> tuple[float, float]:
    """Конечные точки рельсов АЦП той же float32-конверсией из манифеста."""
    rails = apply_adc_calibration(
        np.array([0, 255], dtype=np.uint8),
        range_code=manifest.ch1.range_code,
        probe_multiplier=manifest.ch1.probe_multiplier,
    )
    return float(rails[0]), float(rails[1])
