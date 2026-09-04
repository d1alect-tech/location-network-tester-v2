"""Анализ сессии: спектр + метрика иголок; артефакты metrics.json / spectrum.csv.

Тонкий фасад C4: типы — в ``lnt.analysis_types``, пейлоады — в
``lnt.analysis_payload``, рендер — в ``lnt.analysis_render``, запись — в
``lnt.analysis_write``. Здесь только движок ``analyze_session`` и реэкспорт
поверхности (импорты потребителей неизменны).
"""

from pathlib import Path

from lnt.analysis_payload import analysis_to_payload, line_quality_analysis_to_payload
from lnt.analysis_render import (
    MAX_RENDERED_HARMONIC_ORDER,
    MIN_RENDERED_RATIO,
    RENDERED_PEAKS,
    render_analysis,
    render_line_quality_analysis,
)
from lnt.analysis_types import (
    ANALYSIS_SCHEMA_VERSION,
    METRICS_FILENAME,
    SPECTRUM_FILENAME,
    SPECTRUM_INPUT_REFERRED_FILENAME,
    AnalysisResult,
    LineQualityAnalysis,
)
from lnt.analysis_write import write_analysis, write_line_quality_analysis
from lnt.errors import InputError
from lnt.input_reference import derive_input_reference
from lnt.line_quality import compute_line_quality
from lnt.needles import compute_needle_metrics, compute_needle_metrics_single
from lnt.session_store import load_session
from lnt.spectrum import compute_band_spectrum
from lnt.types import SessionType

__all__ = [
    "ANALYSIS_SCHEMA_VERSION",
    "MAX_RENDERED_HARMONIC_ORDER",
    "METRICS_FILENAME",
    "MIN_RENDERED_RATIO",
    "RENDERED_PEAKS",
    "SPECTRUM_FILENAME",
    "SPECTRUM_INPUT_REFERRED_FILENAME",
    "AnalysisResult",
    "LineQualityAnalysis",
    "analysis_to_payload",
    "analyze_measurement_session",
    "analyze_session",
    "line_quality_analysis_to_payload",
    "render_analysis",
    "render_line_quality_analysis",
    "write_analysis",
    "write_line_quality_analysis",
]


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
    spectrum = compute_band_spectrum(loaded.ch1, sample_rate_hz=manifest.sample_rate_hz, hold=True)
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


def analyze_measurement_session(session_dir: Path) -> AnalysisResult:
    """Анализ measurement/self-noise сессии с узким типом результата."""
    result = analyze_session(session_dir)
    if isinstance(result, LineQualityAnalysis):
        raise InputError(
            f"сессия {result.session_id} — line-quality; ожидалась measurement/self-noise сессия",
        )
    return result
