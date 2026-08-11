"""Сравнение двух проанализированных сессий: дельты пиков и метрик иголок."""

from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.analysis import AnalysisResult, LineQualityAnalysis
from lnt.errors import InputError
from lnt.spectrum import BandSpectrum, SpectrumPeak, level_at_db

MAX_COMPARED_PEAKS: Final = 5
PEAK_MATCH_TOLERANCE_RATIO: Final = 0.02
PEAK_MATCH_MIN_BINS: Final = 2.0
ZERO_METRIC_EPS: Final = 1e-30


def ensure_comparable(result: AnalysisResult | LineQualityAnalysis) -> AnalysisResult:
    """Пропускает в сравнение только иголочные анализы (measurement/self-noise)."""
    if isinstance(result, LineQualityAnalysis):
        raise InputError(
            f"сессия {result.session_id}: сравнение line-quality сессий не поддерживается",
        )
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class PeakDelta:
    """Дельта уровня одного пика A между сессиями."""

    frequency_hz: float
    level_a_db: float
    level_b_db: float
    delta_db: float
    q_a: float | None
    q_b: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricDelta:
    """Пара значений одной метрики иголок (A и B).

    ``None`` — метрика недоступна (однокональная сессия без фазовой привязки).
    """

    name: str
    value_a: float | None
    value_b: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ComparisonResult:
    """Итог сравнения сессий A и B."""

    session_a_id: str
    session_b_id: str
    peak_deltas: tuple[PeakDelta, ...]
    metric_deltas: tuple[MetricDelta, ...]


class PeakDeltaPayload(TypedDict):
    """JSON-вид дельты одного пика."""

    frequency_hz: float
    level_a_db: float
    level_b_db: float
    delta_db: float
    q_a: float | None
    q_b: float | None


class MetricDeltaPayload(TypedDict):
    """JSON-вид дельты одной метрики."""

    name: str
    value_a: float | None
    value_b: float | None


class ComparisonPayload(TypedDict):
    """Канонический JSON-вид сравнения сессий."""

    session_a_id: str
    session_b_id: str
    peak_deltas: list[PeakDeltaPayload]
    metric_deltas: list[MetricDeltaPayload]


def compare_analyses(result_a: AnalysisResult, result_b: AnalysisResult) -> ComparisonResult:
    """Считает дельты пиков (на частотах пиков A) и метрик иголок."""
    peak_deltas = tuple(
        PeakDelta(
            frequency_hz=peak.frequency_hz,
            level_a_db=peak.level_db,
            level_b_db=level_at_db(result_b.spectrum, peak.frequency_hz),
            delta_db=level_at_db(result_b.spectrum, peak.frequency_hz) - peak.level_db,
            q_a=peak.q_factor,
            q_b=(match.q_factor if match is not None else None),
        )
        for peak in result_a.spectrum.peaks[:MAX_COMPARED_PEAKS]
        for match in (_find_matching_peak(result_b.spectrum, peak.frequency_hz),)
    )
    metric_deltas = (
        MetricDelta(
            name="needle_mean_v",
            value_a=result_a.needle.needle_mean_v,
            value_b=result_b.needle.needle_mean_v,
        ),
        MetricDelta(
            name="needle_sigma_ratio",
            value_a=result_a.needle.needle_sigma_ratio,
            value_b=result_b.needle.needle_sigma_ratio,
        ),
        MetricDelta(
            name="async_sync_ratio",
            value_a=result_a.needle.async_sync_ratio,
            value_b=result_b.needle.async_sync_ratio,
        ),
        MetricDelta(
            name="lf_envelope_cv",
            value_a=result_a.needle.lf_envelope_cv,
            value_b=result_b.needle.lf_envelope_cv,
        ),
    )
    return ComparisonResult(
        session_a_id=result_a.session_id,
        session_b_id=result_b.session_id,
        peak_deltas=peak_deltas,
        metric_deltas=metric_deltas,
    )


def comparison_to_payload(result: ComparisonResult) -> ComparisonPayload:
    """Возвращает канонический JSON-вид сравнения сессий."""
    return {
        "session_a_id": result.session_a_id,
        "session_b_id": result.session_b_id,
        "peak_deltas": [
            {
                "frequency_hz": delta.frequency_hz,
                "level_a_db": delta.level_a_db,
                "level_b_db": delta.level_b_db,
                "delta_db": delta.delta_db,
                "q_a": delta.q_a,
                "q_b": delta.q_b,
            }
            for delta in result.peak_deltas
        ],
        "metric_deltas": [
            {
                "name": delta.name,
                "value_a": delta.value_a,
                "value_b": delta.value_b,
            }
            for delta in result.metric_deltas
        ],
    }


def render_comparison(result: ComparisonResult) -> str:
    """Текстовая таблица дельт для stdout CLI (Δ = B - A)."""
    lines = [
        f"Сравнение: A={result.session_a_id}  B={result.session_b_id}",
        "Пики спектра (дельта = B - A):",
    ]
    if result.peak_deltas:
        lines.append(f"  {'частота':>10}  {'A, дБ':>8}  {'B, дБ':>8}  {'дельта':>7}  Q A->B")
        for delta in result.peak_deltas:
            levels = f"{delta.level_a_db:8.1f}  {delta.level_b_db:8.1f}  {delta.delta_db:+7.1f}"
            q_pair = f"{_q_text(delta.q_a)} -> {_q_text(delta.q_b)}"
            lines.append(f"  {delta.frequency_hz:8.0f} Гц  {levels}  {q_pair}")
    else:
        lines.append("  (у сессии A нет выраженных пиков)")
    lines.append("Метрики иголок:")
    for metric in result.metric_deltas:
        value_a = _value_text(metric.value_a)
        value_b = _value_text(metric.value_b)
        if metric.value_a is None or metric.value_b is None:
            percent = "н/д"
        else:
            percent = _percent_text(metric.value_a, metric.value_b)
        lines.append(f"  {metric.name:<20} {value_a} -> {value_b}  ({percent})")
    return "\n".join(lines)


def _value_text(value: float | None) -> str:
    return f"{value:>10.5f}" if value is not None else f"{'н/д':>10}"


def _find_matching_peak(spectrum: BandSpectrum, frequency_hz: float) -> SpectrumPeak | None:
    tolerance = max(
        PEAK_MATCH_MIN_BINS * spectrum.resolution_hz,
        PEAK_MATCH_TOLERANCE_RATIO * frequency_hz,
    )
    candidates = tuple(
        peak for peak in spectrum.peaks if abs(peak.frequency_hz - frequency_hz) <= tolerance
    )
    if not candidates:
        return None
    return min(candidates, key=lambda peak: abs(peak.frequency_hz - frequency_hz))


def _q_text(q_factor: float | None) -> str:
    return "-" if q_factor is None else f"{q_factor:.1f}"


def _percent_text(value_a: float, value_b: float) -> str:
    if abs(value_a) < ZERO_METRIC_EPS:
        return "n/a"
    return f"{((value_b - value_a) / value_a) * 100.0:+.1f}%"
