"""Числовые блоки ripple-среза: QC-границы, метрики, Welch и полосы.

Граница v1/v2: здесь только оркестрация готовой математики v1 —
``lnt.ripple.metrics`` и ``lnt.psd.engine.compute_welch``. Числа никогда не
фабрикуются: загрязнённые спаны получают ``null`` и типовые причины, а
исходный таймлайн не сжимается.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, cast

import numpy as np
from numpy.typing import NDArray

from lnt.psd.engine import compute_welch
from lnt.ripple.metrics import IntervalStats, interval_stats, mean_v, rms_ac_v, vpp_v

from .ripple_measurements import (
    band_available,
    band_unavailable,
    interval_payload,
    spectrum_available,
    spectrum_settings,
    spectrum_unavailable,
    time_domain_available,
    unavailable_scalars,
)

if TYPE_CHECKING:
    from lnt.psd.models import FrequencyBand, PsdResult
    from lnt.session_store import LoadedSession

    from .ripple_options import RippleOptions
    from .ripple_qc import SpanQc

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]

#: Коды, отравляющие каждый интервал спана целиком (не локализуемы по позициям).
SPAN_WIDE_CODES: Final = ("settling_unknown", "clipping_unknown", "clip_census_inconsistent")
#: Минимум отсчётов для публичных RMS/Vpp (как в ripple.metrics).
MIN_SPAN_SAMPLES: Final = 2


@dataclass(frozen=True, slots=True)
class SessionBlocks:
    """Числовые блоки одной сессии с собственными доступностями."""

    time_domain: dict[str, object]
    intervals: list[dict[str, object]]
    spectrum: dict[str, object]
    bands: list[dict[str, object]]

    @property
    def all_available(self) -> bool:
        """True, когда каждая ветка результата доступна целиком."""
        blocks = (self.time_domain, self.spectrum, *self.bands)
        return all(block["availability"] == "available" for block in blocks)

    @property
    def unavailable_reasons(self) -> tuple[str, ...]:
        """Объединение кодов причин недоступных веток без повторов."""
        collected: list[str] = []
        for block in (self.time_domain, self.spectrum, *self.bands):
            for code in cast("list[str]", block["reason_codes"]):
                if code not in collected:
                    collected.append(code)
        return tuple(collected)


def session_blocks(
    session: LoadedSession,
    options: RippleOptions,
    qc: SpanQc,
) -> SessionBlocks:
    """Вычисляет числовые блоки одной сессии по правилам QC."""
    ch1 = np.asarray(session.ch1)
    span = ch1[qc.sample_start_index : qc.sample_end_index_exclusive]
    sample_rate_hz = session.manifest.sample_rate_hz
    spectrum, bands = _spectrum_and_bands(qc, span, options)
    return SessionBlocks(
        time_domain=_time_domain(qc, span),
        intervals=_intervals(qc, span, sample_rate_hz, options),
        spectrum=spectrum,
        bands=bands,
    )


def _time_domain(qc: SpanQc, span: Float32Array) -> dict[str, object]:
    if qc.span_reason_codes:
        return unavailable_scalars(qc.span_reason_codes)
    if qc.span_count < MIN_SPAN_SAMPLES:
        return unavailable_scalars((*qc.span_reason_codes, "insufficient_samples"))
    values = np.asarray(span, dtype=np.float64)
    return time_domain_available(
        mean_v=mean_v(values),
        rms_ac_v=rms_ac_v(values),
        vpp_v=vpp_v(values),
    )


def _intervals(
    qc: SpanQc,
    span: Float32Array,
    sample_rate_hz: float,
    options: RippleOptions,
) -> list[dict[str, object]]:
    """Интервалы с исходными индексами; загрязнённые числа выбрасываются.

    Разбиение считается по подстановке не-конечных значений нулём: подстановка
    затрагивает только загрязнённые интервалы, чьи числа всё равно обнуляются;
    чистые интервалы считают по нетронутым значениям.
    """
    if qc.span_count == 0:
        return []
    sanitized = np.nan_to_num(np.asarray(span, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    stats = interval_stats(sanitized, sample_rate_hz, options.interval_window_s)
    offset = qc.sample_start_index
    span_wide = tuple(code for code in qc.span_reason_codes if code in SPAN_WIDE_CODES)
    items: list[dict[str, object]] = []
    for item in stats:
        absolute_start = offset + item.start_index
        absolute_end = offset + item.end_index_exclusive
        contamination = list(span_wide)
        if _hits_inside(qc.span_nonfinite_positions, absolute_start, absolute_end):
            contamination.append("nonfinite_samples")
        clip_low, clip_high = _interval_clip_census(qc, absolute_start, absolute_end)
        if clip_low or clip_high:
            contamination.append("clipped")
        resolved = _absolute(item, absolute_start, absolute_end)
        if contamination:
            resolved = _contaminated(resolved, tuple(contamination))
        items.append(
            interval_payload(resolved, clip_low_count=clip_low, clip_high_count=clip_high),
        )
    return items


def _absolute(
    item: IntervalStats,
    absolute_start: int,
    absolute_end: int,
) -> IntervalStats:
    """Переносит границы интервала в исходные индексы полной записи."""
    return replace(item, start_index=absolute_start, end_index_exclusive=absolute_end)


def _contaminated(item: IntervalStats, reasons: tuple[str, ...]) -> IntervalStats:
    """Копия интервала без чисел: таймлайн сохранён, фабрикация исключена."""
    return replace(
        item,
        availability="unavailable",
        reason_codes=(*reasons, *item.reason_codes),
        mean_v=None,
        rms_ac_v=None,
        vpp_v=None,
    )


def _count_inside(positions: tuple[int, ...], start: int, end: int) -> int:
    """Число отсортированных абсолютных позиций в полуинтервале [start, end)."""
    return bisect_left(positions, end) - bisect_left(positions, start)


def _hits_inside(positions: tuple[int, ...], start: int, end: int) -> bool:
    return _count_inside(positions, start, end) > 0


def _interval_clip_census(
    qc: SpanQc,
    start: int,
    end: int,
) -> tuple[int | None, int | None]:
    """Позиционный ценз интервала; null, когда положения неизвестны."""
    if qc.span_clip_low_positions is None or qc.span_clip_high_positions is None:
        return None, None
    return (
        _count_inside(qc.span_clip_low_positions, start, end),
        _count_inside(qc.span_clip_high_positions, start, end),
    )


def _spectrum_and_bands(
    qc: SpanQc,
    span: Float32Array,
    options: RippleOptions,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Спектр и хранимые полосы; полоса следует доступности спектра."""
    welch = options.welch
    band = welch.bands[0]
    settings = spectrum_settings(
        nperseg=welch.nperseg,
        max_chunk_samples=welch.max_chunk_samples,
        overlap_fraction=welch.overlap_fraction,
        window=welch.window,
        detector=welch.detector,
        resolution_hz=welch.resolution_hz,
        enbw_hz=welch.window_enbw_hz,
        segment_count=None,
    )
    reasons = qc.span_reason_codes
    if qc.span_count < welch.nperseg:
        reasons = (*reasons, "insufficient_samples")
    if reasons:
        unavailable = band_unavailable(
            band_id=band.name,
            low_hz=band.low_hz,
            high_hz=band.high_hz,
            reason_codes=reasons,
        )
        return spectrum_unavailable(settings=settings, reason_codes=reasons), [unavailable]
    result = compute_welch(span, settings=welch)
    settings["segment_count"] = result.segment_count
    hop = welch.nperseg - welch.noverlap
    used = welch.nperseg + (result.segment_count - 1) * hop
    spectrum = spectrum_available(
        settings=settings,
        used_sample_count=used,
        ignored_tail_samples=qc.span_count - used,
        frequency_hz=result.frequency_hz,
        psd_v2_per_hz=result.psd_v2_per_hz,
        asd_v_per_sqrt_hz=result.asd_v_per_sqrt_hz,
    )
    return spectrum, [_band(band=band, result=result, resolution_hz=welch.resolution_hz)]


def _band(
    *,
    band: FrequencyBand,
    result: PsdResult,
    resolution_hz: float,
) -> dict[str, object]:
    """Полоса по фактической сетке: положительные центры, DC исключён.

    Прямоугольная сумма ``sqrt(sum(PSD[mask]) * df)``; ENBW второй раз не
    умножается. ``compute_welch`` уже отдаёт V^2/Hz и не сглаживает PSD.
    """
    frequency = result.frequency_hz
    mask = (frequency >= band.low_hz) & (frequency <= band.high_hz) & (frequency > 0.0)
    selected = frequency[mask]
    if selected.size == 0:
        return band_unavailable(
            band_id=band.name,
            low_hz=band.low_hz,
            high_hz=band.high_hz,
            reason_codes=("no_positive_frequency_center",),
        )
    rms_v = math.sqrt(float(np.sum(result.psd_v2_per_hz[mask])) * resolution_hz)
    if not math.isfinite(rms_v):
        return band_unavailable(
            band_id=band.name,
            low_hz=band.low_hz,
            high_hz=band.high_hz,
            reason_codes=("numerical_overflow",),
        )
    return band_available(
        band_id=band.name,
        low_hz=band.low_hz,
        high_hz=band.high_hz,
        first_center_hz=float(selected[0]),
        last_center_hz=float(selected[-1]),
        bin_count=int(selected.size),
        rms_v=rms_v,
    )
