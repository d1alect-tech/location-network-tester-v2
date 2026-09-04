"""Канонические JSON-пейлоады анализа v1 (тот же вид, что metrics.json).

C4: выделено из ``lnt.analysis`` без изменения формата и порядка ключей.
"""

import dataclasses

from lnt.analysis_types import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisResult,
    LineQualityAnalysis,
    legacy_input_reference,
)
from lnt.line_quality import line_quality_to_payload


def line_quality_analysis_to_payload(result: LineQualityAnalysis) -> dict[str, object]:
    """Канонический JSON-вид line-quality анализа (тот же, что metrics.json).

    Форма — надмножество обычного анализа: needle/spectrum явно null,
    чтобы фронтенд различал режимы по одному контракту.
    """
    unavailable = dataclasses.replace(legacy_input_reference(), reason_code="line_quality_session")
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
            "window": result.spectrum.window,
            "enbw_hz": result.spectrum.enbw_hz,
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
