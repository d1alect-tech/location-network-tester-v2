"""Человекочитаемые сводки анализа v1 для stdout CLI.

C4: выделено из ``lnt.analysis``; тексты и порядок строк неизменны.
"""

from lnt.analysis_types import AnalysisResult, LineQualityAnalysis
from lnt.input_reference import InputReferenceStatus
from lnt.line_quality import LineHarmonic

RENDERED_PEAKS = 5
MAX_RENDERED_HARMONIC_ORDER = 40
MIN_RENDERED_RATIO = 0.001


def render_line_quality_analysis(result: LineQualityAnalysis) -> str:
    """Человекочитаемая сводка качества сети для stdout CLI."""
    metrics = result.line_quality
    lines = [
        f"Сессия: {result.session_id}",
        f"Источник: {result.source.value} / {result.session_type.value}",
        f"Запись: fs={result.sample_rate_hz:.0f} Гц, длительность {result.duration_s:.2f} с",
        f"Сеть: {metrics.fundamental_hz:.2f} Гц, циклов: {metrics.cycles_analyzed}",
        f"RMS: фундаментал {metrics.fundamental_rms_v:.3f} В, полный {metrics.total_rms_v:.3f} В",
        f"THD (H2–H{MAX_RENDERED_HARMONIC_ORDER}+): {metrics.thd_ratio * 100.0:.2f} %",
        f"Crest-factor: {metrics.crest_factor:.2f} (синус = 1.41)",
        f"Огибающая: CV={metrics.envelope_cv:.4f}",
        "Гармоники (топ):",
    ]
    top = sorted(metrics.harmonics, key=lambda harmonic: harmonic.ratio, reverse=True)
    top = [harmonic for harmonic in top[:RENDERED_PEAKS] if harmonic.ratio >= MIN_RENDERED_RATIO]
    if top:
        lines.extend(_render_harmonic_row(h) for h in sorted(top, key=lambda item: item.order))
    else:
        lines.append("  (значимых гармоник не найдено)")
    return "\n".join(lines)


def render_analysis(result: AnalysisResult) -> str:
    """Человекочитаемая сводка анализа для stdout CLI."""
    needle = result.needle
    if needle.line_frequency_hz is not None:
        line_text = f"Сеть: {needle.line_frequency_hz:.2f} Гц, циклов: {needle.cycles_analyzed}"
    else:
        line_text = f"Сеть: номинал (без CH2), окон: {needle.cycles_analyzed}"
    async_text = (
        f"P_async/P_sync={needle.async_sync_ratio:.3f}"
        if needle.async_sync_ratio is not None
        else "н/д (один канал)"
    )
    envelope_text = (
        f"CV={needle.lf_envelope_cv:.4f}" if needle.lf_envelope_cv is not None else "н/д"
    )
    lines = [
        f"Сессия: {result.session_id}",
        f"Источник: {result.source.value} / {result.session_type.value}",
        f"Профиль: {result.profile or '-'}",
        line_text,
        f"Запись: fs={result.sample_rate_hz:.0f} Гц, длительность {result.duration_s:.2f} с",
        f"Иголки: mu_pk={needle.needle_mean_v:.4f} В, sigma/mu={needle.needle_sigma_ratio:.3f}",
        f"Асинхронность: {async_text}",
        f"Огибающая CH2: {envelope_text}",
        "Пики спектра:",
    ]
    if result.spectrum.peaks:
        for peak in result.spectrum.peaks[:RENDERED_PEAKS]:
            q_text = f"{peak.q_factor:.1f}" if peak.q_factor is not None else "-"
            level = f"{peak.frequency_hz:9.0f} Гц  {peak.level_db:7.1f} дБ"
            lines.append(f"  {level}  Q={q_text}  (пром. {peak.prominence_db:.1f} дБ)")
    else:
        lines.append("  (выраженных пиков не найдено)")
    reference = result.ch1_input_reference
    match reference.status:
        case InputReferenceStatus.AVAILABLE:
            lines.append(
                ", ".join(
                    (
                        "CH1 input-reference: model-based excess PSD",
                        "floating_host_unverified",
                        f"qualified={reference.qualified_bin_count}/{reference.total_bin_count}",
                    ),
                ),
            )
        case InputReferenceStatus.UNAVAILABLE:
            lines.append(f"CH1 input-reference: unavailable ({reference.reason_code})")
    return "\n".join(lines)


def _render_harmonic_row(h: LineHarmonic) -> str:
    percent = h.ratio * 100.0
    return f"  H{h.order:<2} {h.frequency_hz:7.1f} Гц  {percent:6.2f} % ({h.amplitude_v:.3f} В)"
