"""Анализ сессии: спектр + метрика иголок; артефакты metrics.json / spectrum.csv."""

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from lnt.errors import InputError
from lnt.input_reference import (
    Ch1InputReference,
    InputReferenceStatus,
    derive_input_reference,
)
from lnt.line_quality import (
    LineHarmonic,
    LineQualityMetrics,
    compute_line_quality,
    line_quality_to_payload,
)
from lnt.needles import NeedleMetrics, compute_needle_metrics, compute_needle_metrics_single
from lnt.session_projection import project_analysis_safely
from lnt.session_store import load_session
from lnt.spectrum import BandSpectrum, compute_band_spectrum
from lnt.types import SessionSource, SessionType

METRICS_FILENAME = "metrics.json"
SPECTRUM_FILENAME = "spectrum.csv"
SPECTRUM_INPUT_REFERRED_FILENAME = "spectrum_input_referred.csv"
ANALYSIS_SCHEMA_VERSION = 2
RENDERED_PEAKS = 5
MAX_RENDERED_HARMONIC_ORDER = 40


def _legacy_input_reference() -> Ch1InputReference:
    """Создаёт provenance для вручную собранных legacy AnalysisResult в consumers/tests."""
    return Ch1InputReference(
        status=InputReferenceStatus.UNAVAILABLE,
        reason_code="manifest_schema_v1",
        model_kind=None,
        input_referred_excess_psd_v2_per_hz=None,
        qualified=None,
        baseline_session_id=None,
        model=None,
        qualification_rule_id=None,
        qualified_bin_count=0,
        total_bin_count=0,
        corrected_peaks=(),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisResult:
    """Полный результат анализа одной сессии."""

    session_id: str
    profile: str | None
    source: SessionSource
    session_type: SessionType
    sample_rate_hz: float
    duration_s: float
    needle: NeedleMetrics
    spectrum: BandSpectrum
    ch1_input_reference: Ch1InputReference = field(default_factory=_legacy_input_reference)


@dataclass(frozen=True, slots=True, kw_only=True)
class LineQualityAnalysis:
    """Результат анализа line-quality сессии (качество сети 50 Гц)."""

    session_id: str
    profile: str | None
    source: SessionSource
    session_type: SessionType
    sample_rate_hz: float
    duration_s: float
    line_quality: LineQualityMetrics


def analyze_session(session_dir: Path) -> AnalysisResult | LineQualityAnalysis:
    """Загружает сессию и считает метрики по её типу.

    Для measurement/self-noise — иголки + band-спектр CH1; для line-quality —
    частота/RMS/THD/гармоники сети по трансформаторному входу CH1.
    """
    loaded = load_session(session_dir)
    manifest = loaded.manifest
    if manifest.session_type is SessionType.LINE_QUALITY:
        return LineQualityAnalysis(
            session_id=manifest.session_id,
            profile=manifest.profile,
            source=manifest.source,
            session_type=manifest.session_type,
            sample_rate_hz=manifest.sample_rate_hz,
            duration_s=manifest.duration_s,
            line_quality=compute_line_quality(
                loaded.ch1,
                sample_rate_hz=manifest.sample_rate_hz,
                nominal_line_hz=manifest.line_frequency_hz,
            ),
        )
    if loaded.ch2 is not None:
        needle = compute_needle_metrics(
            loaded.ch1,
            loaded.ch2,
            sample_rate_hz=manifest.sample_rate_hz,
        )
    else:
        needle = compute_needle_metrics_single(
            loaded.ch1,
            sample_rate_hz=manifest.sample_rate_hz,
            line_frequency_hz=manifest.line_frequency_hz,
        )
    spectrum = compute_band_spectrum(loaded.ch1, sample_rate_hz=manifest.sample_rate_hz)
    ch1_input_reference = derive_input_reference(session_dir, loaded, spectrum)
    return AnalysisResult(
        session_id=manifest.session_id,
        profile=manifest.profile,
        source=manifest.source,
        session_type=manifest.session_type,
        sample_rate_hz=manifest.sample_rate_hz,
        duration_s=manifest.duration_s,
        needle=needle,
        spectrum=spectrum,
        ch1_input_reference=ch1_input_reference,
    )


def write_analysis(session_dir: Path, result: AnalysisResult) -> tuple[Path, Path]:
    """Пишет metrics.json и spectrum.csv в каталог сессии; возвращает пути."""
    metrics_path = session_dir / METRICS_FILENAME
    metrics_path.write_text(
        json.dumps(analysis_to_payload(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    spectrum_path = session_dir / SPECTRUM_FILENAME
    table = np.column_stack([result.spectrum.frequencies_hz, result.spectrum.psd_v2_per_hz])
    np.savetxt(
        spectrum_path,
        table,
        delimiter=",",
        header="frequency_hz,psd_v2_per_hz",
        comments="",
        fmt="%.9g",
    )
    _write_input_referred_spectrum(session_dir, result)
    project_analysis_safely(session_dir, result.session_id)
    return metrics_path, spectrum_path


def analyze_measurement_session(session_dir: Path) -> AnalysisResult:
    """Анализ measurement/self-noise сессии с узким типом результата."""
    result = analyze_session(session_dir)
    if isinstance(result, LineQualityAnalysis):
        raise InputError(
            f"сессия {result.session_id} — line-quality; ожидалась measurement/self-noise сессия",
        )
    return result


def write_line_quality_analysis(session_dir: Path, result: LineQualityAnalysis) -> Path:
    """Пишет metrics.json line-quality сессии; HF-артефакты не фабрикуются."""
    metrics_path = session_dir / METRICS_FILENAME
    metrics_path.write_text(
        json.dumps(line_quality_analysis_to_payload(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    project_analysis_safely(session_dir, result.session_id)
    return metrics_path


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


MIN_RENDERED_RATIO = 0.001


def _render_harmonic_row(h: LineHarmonic) -> str:
    percent = h.ratio * 100.0
    return f"  H{h.order:<2} {h.frequency_hz:7.1f} Гц  {percent:6.2f} % ({h.amplitude_v:.3f} В)"


def line_quality_analysis_to_payload(result: LineQualityAnalysis) -> dict[str, object]:
    """Канонический JSON-вид line-quality анализа (тот же, что metrics.json).

    Форма — надмножество обычного анализа: needle/spectrum явно null,
    чтобы фронтенд различал режимы по одному контракту.
    """
    unavailable = dataclasses.replace(_legacy_input_reference(), reason_code="line_quality_session")
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "session_id": result.session_id,
        "profile": result.profile,
        "source": result.source.value,
        "session_type": result.session_type.value,
        "sample_rate_hz": result.sample_rate_hz,
        "duration_s": result.duration_s,
        "needle": None,
        "spectrum": None,
        "line_quality": line_quality_to_payload(result.line_quality),
        "ch1_input_reference": {
            "status": unavailable.status.value,
            "reason_code": unavailable.reason_code,
            "model_kind": None,
            "baseline_session_id": None,
            "model": None,
            "qualification_rule_id": None,
            "qualified_bin_count": 0,
            "total_bin_count": 0,
            "corrected_peaks": [],
        },
    }


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
            qualified_count = reference.qualified_bin_count
            total_count = reference.total_bin_count
            lines.append(
                ", ".join(
                    (
                        "CH1 input-reference: model-based excess PSD",
                        "floating_host_unverified",
                        f"qualified={qualified_count}/{total_count}",
                    ),
                ),
            )
        case InputReferenceStatus.UNAVAILABLE:
            lines.append(f"CH1 input-reference: unavailable ({reference.reason_code})")
    return "\n".join(lines)


def analysis_to_payload(result: AnalysisResult) -> dict[str, object]:
    """Канонический JSON-вид анализа, тот же, что metrics.json."""
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "session_id": result.session_id,
        "profile": result.profile,
        "source": result.source.value,
        "session_type": result.session_type.value,
        "sample_rate_hz": result.sample_rate_hz,
        "duration_s": result.duration_s,
        "needle": dataclasses.asdict(result.needle),
        "line_quality": None,
        "spectrum": {
            "resolution_hz": result.spectrum.resolution_hz,
            "band_low_hz": result.spectrum.band_low_hz,
            "band_high_hz": result.spectrum.band_high_hz,
            "peaks": [dataclasses.asdict(peak) for peak in result.spectrum.peaks],
        },
        "ch1_input_reference": {
            "status": result.ch1_input_reference.status.value,
            "reason_code": result.ch1_input_reference.reason_code,
            "model_kind": result.ch1_input_reference.model_kind,
            "baseline_session_id": result.ch1_input_reference.baseline_session_id,
            "model": (
                dataclasses.asdict(result.ch1_input_reference.model)
                if result.ch1_input_reference.model is not None
                else None
            ),
            "qualification_rule_id": result.ch1_input_reference.qualification_rule_id,
            "qualified_bin_count": result.ch1_input_reference.qualified_bin_count,
            "total_bin_count": result.ch1_input_reference.total_bin_count,
            "corrected_peaks": [
                dataclasses.asdict(peak) for peak in result.ch1_input_reference.corrected_peaks
            ],
        },
    }


def _write_input_referred_spectrum(session_dir: Path, result: AnalysisResult) -> None:
    reference = result.ch1_input_reference
    output = session_dir / SPECTRUM_INPUT_REFERRED_FILENAME
    if reference.input_referred_excess_psd_v2_per_hz is None or reference.qualified is None:
        table = np.empty((0, 2), dtype=np.float64)
    else:
        table = np.column_stack(
            [
                result.spectrum.frequencies_hz[reference.qualified],
                reference.input_referred_excess_psd_v2_per_hz[reference.qualified],
            ],
        )
    np.savetxt(
        output,
        table,
        delimiter=",",
        header="frequency_hz,input_referred_excess_psd_v2_per_hz",
        comments="",
        fmt="%.9g",
    )
