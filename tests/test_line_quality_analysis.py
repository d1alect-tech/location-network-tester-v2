"""Диспетчер анализа line-quality сессии: metrics.json, артефакты, рендер."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from lnt.analysis import (
    AnalysisResult,
    LineQualityAnalysis,
    analyze_session,
    render_line_quality_analysis,
    write_line_quality_analysis,
)
from lnt.types import SessionType
from tests.line_quality_fixtures import write_line_quality_session

if TYPE_CHECKING:
    from pathlib import Path


def _line_session(tmp_path: Path) -> Path:
    return write_line_quality_session(tmp_path / "line", session_id="line-analysis-test")


def test_analyze_session_dispatches_line_quality(tmp_path: Path) -> None:
    # Given: a persisted line-quality session.
    session_dir = _line_session(tmp_path)

    # When: the generic entry point analyzes it.
    result = analyze_session(session_dir)

    # Then: the result is the line-quality analysis with correct THD.
    assert isinstance(result, LineQualityAnalysis)
    assert not isinstance(result, AnalysisResult)
    assert result.session_type is SessionType.LINE_QUALITY
    assert result.line_quality.thd_ratio == pytest.approx(0.05, rel=0.05)
    assert result.line_quality.fundamental_hz == pytest.approx(50.0, abs=0.05)


def test_write_line_quality_analysis_produces_only_metrics_json(tmp_path: Path) -> None:
    # Given: an analyzed line-quality session.
    session_dir = _line_session(tmp_path)
    result = analyze_session(session_dir)
    assert isinstance(result, LineQualityAnalysis)

    # When: artifacts are written.
    metrics_path = write_line_quality_analysis(session_dir, result)

    # Then: metrics.json carries the line_quality section and null legacy sections.
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["session_type"] == "line_quality"
    assert payload["needle"] is None
    assert payload["spectrum"] is None
    assert payload["line_quality"]["thd_ratio"] == pytest.approx(0.05, rel=0.05)
    assert payload["line_quality"]["harmonics"][0]["order"] == 2
    assert payload["ch1_input_reference"]["status"] == "unavailable"
    assert payload["ch1_input_reference"]["reason_code"] == "line_quality_session"
    # And: no HF spectrum artifacts are fabricated.
    assert not (session_dir / "spectrum.csv").exists()
    assert not (session_dir / "spectrum_input_referred.csv").exists()


def test_render_line_quality_analysis_mentions_key_metrics(tmp_path: Path) -> None:
    # Given: an analyzed line-quality session.
    session_dir = _line_session(tmp_path)
    result = analyze_session(session_dir)
    assert isinstance(result, LineQualityAnalysis)

    # When: the CLI summary is rendered.
    text = render_line_quality_analysis(result)

    # Then: the operator sees frequency, RMS, THD and the top harmonics.
    assert "THD" in text
    assert "50.00" in text
    assert "H3" in text
    assert "Гц" in text
