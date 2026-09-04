"""Контракт RBW-метаданных спектра: window/enbw_hz из metrics.json наружу."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from lnt.analysis import METRICS_FILENAME, analyze_measurement_session, write_analysis
from lnt.simulate import simulate_session
from lnt.ui.payloads import spectrum_payload

if TYPE_CHECKING:
    from pathlib import Path


def test_spectrum_payload_exposes_window_and_enbw(tmp_path: Path) -> None:
    session_dir = simulate_session(
        out_dir=tmp_path / "sessions" / "synthetic",
        profile="quiet",
        duration_s=2.1,
        sample_rate_hz=20_000.0,
        seed=11,
    )
    write_analysis(session_dir, analyze_measurement_session(session_dir))
    metrics = json.loads((session_dir / METRICS_FILENAME).read_text(encoding="utf-8"))
    spectrum = metrics["spectrum"]
    assert spectrum["window"] == "hann"
    assert spectrum["enbw_hz"] == pytest.approx(1.5 * spectrum["resolution_hz"])
    payload = spectrum_payload(tmp_path / "sessions", session_dir.name, max_points=1_000)
    assert payload["window"] == "hann"
    assert payload["enbw_hz"] == pytest.approx(spectrum["enbw_hz"])
    assert payload["resolution_hz"] == pytest.approx(spectrum["resolution_hz"])
