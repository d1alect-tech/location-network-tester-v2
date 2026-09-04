"""Запись артефактов анализа v1: metrics.json / spectrum.csv.

C4: выделено из ``lnt.analysis``; формат файлов и байты неизменны.
"""

import json
from pathlib import Path

import numpy as np

from lnt.analysis_payload import analysis_to_payload, line_quality_analysis_to_payload
from lnt.analysis_types import (
    METRICS_FILENAME,
    SPECTRUM_FILENAME,
    SPECTRUM_INPUT_REFERRED_FILENAME,
    AnalysisResult,
    LineQualityAnalysis,
)
from lnt.session_projection import project_analysis_safely


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


def write_line_quality_analysis(session_dir: Path, result: LineQualityAnalysis) -> Path:
    """Пишет metrics.json line-quality сессии; HF-артефакты не фабрикуются."""
    metrics_path = session_dir / METRICS_FILENAME
    metrics_path.write_text(
        json.dumps(line_quality_analysis_to_payload(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    project_analysis_safely(session_dir, result.session_id)
    return metrics_path


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
