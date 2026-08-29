from __future__ import annotations

import json
from typing import TYPE_CHECKING

from lnt.analysis import AnalysisResult
from lnt.analysis_v2 import DefaultAnalysisEngine
from lnt.ui.analysis_v2_wire import AnalyzeWriteResult
from lnt.ui.operations import LntBackend
from tests.analysis.test_orchestrator import _measurement_sine_session

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from lnt.analysis_v2.types import BranchContext, BranchOutput

_V2_JSON = (
    "harmonics.json",
    "notching.json",
    "apd.json",
    "burst.json",
    "trends.json",
    "audio_panel.json",
)
_RATE_HZ = 10_000.0
_DURATION_S = 2.4
_SAMPLE_COUNT = 24_000


def _measurement_session(path: Path) -> Path:
    session = _measurement_sine_session(path)
    (session / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": session.name,
                "created_utc": "2026-08-04T00:00:00Z",
                "completed_utc": "2026-08-04T00:00:02Z",
                "source": "synthetic",
                "session_type": "measurement",
                "sample_rate_hz": _RATE_HZ,
                "duration_s": _DURATION_S,
                "sample_count": _SAMPLE_COUNT,
                "line_frequency_hz": 50.0,
                "profile": "quiet",
                "baseline_session": None,
                "parameters": {"seed": 7},
                "ch1": {
                    "filename": "ch1.npy",
                    "role": "hf_probe",
                    "unit": "V",
                    "front_end": "synthetic",
                    "range_code": 1,
                    "probe_multiplier": 1.0,
                },
                "ch2": {
                    "filename": "ch2.npy",
                    "role": "lf_transformer",
                    "unit": "V",
                    "front_end": "synthetic",
                    "range_code": 1,
                    "probe_multiplier": 1.0,
                },
                "acquisition_telemetry": None,
                "synthetic_truth": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return session


def _artifact_dir(session: Path) -> Path:
    pointer = json.loads((session / ".lnt-default-analysis.json").read_text(encoding="utf-8"))
    return session / "analyses" / pointer["artifact_key"]


def test_analyze_and_write_keeps_v1_needle_metrics(tmp_path: Path) -> None:
    session = _measurement_session(tmp_path / "measurement")

    result = LntBackend().analyze_and_write(session)

    assert isinstance(result, AnalyzeWriteResult)
    assert isinstance(result.analysis, AnalysisResult)
    payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
    assert payload["needle"] is not None


def test_analyze_and_write_writes_v2_batch26_artifacts(tmp_path: Path) -> None:
    session = _measurement_session(tmp_path / "measurement")

    LntBackend().analyze_and_write(session)

    artifact_dir = _artifact_dir(session)
    for name in _V2_JSON:
        assert (artifact_dir / name).is_file()
    assert not (artifact_dir / "power_quality.json").exists()
    assert not (session / "cm_dm_spectrum.csv").exists()


def test_analyze_and_write_writes_default_pointer(tmp_path: Path) -> None:
    session = _measurement_session(tmp_path / "measurement")

    LntBackend().analyze_and_write(session)

    pointer = json.loads((session / ".lnt-default-analysis.json").read_text(encoding="utf-8"))
    assert pointer["recipe_id"]
    assert pointer["artifact_key"]
    assert (session / "analyses" / pointer["artifact_key"]).is_dir()


def test_branch_failure_returns_analysis_and_keeps_v1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _measurement_session(tmp_path / "measurement")
    original = DefaultAnalysisEngine.run_branch

    def boom(self: DefaultAnalysisEngine, name: str, context: BranchContext) -> BranchOutput:
        if name == "harmonics":
            raise RuntimeError("harmonics-boom")
        return original(self, name, context)

    monkeypatch.setattr(DefaultAnalysisEngine, "run_branch", boom)

    result = LntBackend().analyze_and_write(session)

    assert isinstance(result.analysis, AnalysisResult)
    assert any(item["branch"] == "harmonics" for item in result.branch_failures)
    assert (session / "metrics.json").is_file()
    payload = json.loads((session / "metrics.json").read_text(encoding="utf-8"))
    assert payload["needle"] is not None


def test_orchestrator_exception_returns_synthetic_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _measurement_session(tmp_path / "measurement")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("orchestrator-boom")

    monkeypatch.setattr("lnt.analysis_v2.orchestrator.AnalysisOrchestrator.run", boom)

    result = LntBackend().analyze_and_write(session)

    assert isinstance(result.analysis, AnalysisResult)
    assert result.branch_failures == (
        {
            "branch": "orchestrator",
            "error_type": "RuntimeError",
            "message": "orchestrator-boom",
        },
    )
    assert (session / "metrics.json").is_file()
