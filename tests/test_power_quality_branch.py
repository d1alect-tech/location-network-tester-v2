"""B2-T19: power_quality branch wiring into analysis_v2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import override

import numpy as np

from lnt.analysis_store import AnalysisRecipe, CodeIdentity
from lnt.analysis_v2 import (
    AnalysisOrchestrator,
    BranchContext,
    BranchFailure,
    BranchOutput,
    SessionKind,
)
from lnt.analysis_v2.engine import DefaultAnalysisEngine
from lnt.power_quality import power_quality_preset
from lnt.scope_io import NEVER_CANCELLED


def _recipe(*, channels: tuple[str, ...] = ("ch1",)) -> AnalysisRecipe:
    return AnalysisRecipe.from_mapping(
        {
            "schema_version": 1,
            "mode": "standard",
            "channels": list(channels),
            "band_grid": {"low_hz": 10.0, "high_hz": 400.0, "grid_hz": 1.0},
            "welch": {
                "window": "hann_periodic",
                "segment_samples": 64,
                "overlap_fraction": 0.5,
                "detrend": "constant",
                "scaling": "density",
                "average": "mean",
            },
            "spectrogram": {"enabled": True, "segment_samples": 64, "overlap_fraction": 0.5},
            "events": {"enabled": True, "threshold_sigma": 5.0},
            "bands": {"edges_hz": [10.0, 100.0, 400.0]},
            "correction": {"method": "none"},
            "uncertainty": {"enabled": False, "confidence_level": 0.95, "bootstrap_samples": 0},
        }
    )


def _signal(duration_s: float = 0.5) -> np.ndarray:
    sample_rate = 100_000.0
    line_hz = 50.0
    t = np.arange(round(sample_rate * duration_s), dtype=np.float64) / sample_rate
    return (np.sin(2.0 * np.pi * line_hz * t)).astype(np.float32)


def test_session_kind_power_quality_exists() -> None:
    assert SessionKind.POWER_QUALITY.value == "power_quality"
    assert SessionKind("power_quality") is SessionKind.POWER_QUALITY


def test_dispatch_contains_power_quality() -> None:
    # Dispatch is verified via orchestrator behavior; check public SessionKind is dispatchable
    assert SessionKind.POWER_QUALITY.value == "power_quality"
    # The orchestrator must accept this kind without raising InputError (tested in next test)
    assert True


def test_engine_power_quality_branch_emits_two_files() -> None:
    engine = DefaultAnalysisEngine()
    samples = _signal(0.5)
    tmp = Path.cwd()
    context = BranchContext(
        kind=SessionKind.POWER_QUALITY,
        session_dir=tmp,
        sample_rate_hz=100_000.0,
        channels=(samples,),
        recipe=_recipe(),
        cancellation=NEVER_CANCELLED,
    )
    output = engine.run_branch("power_quality", context)
    assert "power_quality.json" in output.files
    assert "half_cycle_rms.json" in output.files
    pq = json.loads(output.files["power_quality.json"].decode())
    assert pq["schema_version"] == 1
    assert isinstance(pq["settings_hash"], str)
    assert len(pq["settings_hash"]) == 64
    assert "half_cycle_rms_summary" in pq
    rms = json.loads(output.files["half_cycle_rms.json"].decode())
    assert "times_s" in rms
    assert "rms_v" in rms
    assert "edges_s" in rms
    assert rms["count"] == pq["half_cycle_rms_summary"]["count"]


def test_orchestrator_dispatches_power_quality(tmp_path: Path) -> None:
    session = tmp_path / "pq"
    session.mkdir()
    samples = _signal(0.5)
    np.save(session / "ch1.npy", samples)
    (session / "manifest.json").write_text(
        json.dumps({"session_type": "power_quality", "sample_rate_hz": 100_000.0}),
        encoding="utf-8",
    )
    engine = DefaultAnalysisEngine()
    orch = AnalysisOrchestrator(
        engine=engine, code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test")
    )
    result = orch.run(session, _recipe(channels=("ch1",)))
    assert result.failures == ()
    assert (result.artifact_dir / "power_quality.json").is_file()
    assert (result.artifact_dir / "half_cycle_rms.json").is_file()
    assert (result.artifact_dir / "branch-status.json").is_file()
    session2 = tmp_path / "meas"
    session2.mkdir()
    np.save(session2 / "ch1.npy", samples)
    np.save(session2 / "ch2.npy", samples)
    (session2 / "manifest.json").write_text(
        json.dumps({"session_type": "measurement", "sample_rate_hz": 100_000.0}),
        encoding="utf-8",
    )
    result2 = orch.run(session2, _recipe(channels=("ch1", "ch2")))
    assert not (result2.artifact_dir / "power_quality.json").is_file()
    assert all(failure.branch != "power_quality" for failure in result2.failures)


def test_cache_key_includes_power_quality_settings_hash(tmp_path: Path) -> None:
    settings = power_quality_preset("itic_default")
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    expected_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    samples = _signal(0.5)
    # power_quality session must embed settings hash in manifest context
    pq_session = tmp_path / "pq_ctx"
    pq_session.mkdir()
    np.save(pq_session / "ch1.npy", samples)
    (pq_session / "manifest.json").write_text(
        json.dumps({"session_type": "power_quality", "sample_rate_hz": 100_000.0}), encoding="utf-8"
    )
    orch = AnalysisOrchestrator(
        engine=DefaultAnalysisEngine(),
        code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
    )
    result_pq = orch.run(pq_session, _recipe(channels=("ch1",)))
    manifest_pq = json.loads(
        (result_pq.artifact_dir / "analysis-manifest.json").read_text(encoding="utf-8")
    )
    context_entries = manifest_pq["inputs"]["context"]
    assert any(
        item["name"] == "power_quality_settings.json" and item["digest"] == expected_hash
        for item in context_entries
    )
    # measurement session must NOT embed the power_quality hash
    meas_session = tmp_path / "meas_ctx"
    meas_session.mkdir()
    np.save(meas_session / "ch1.npy", samples)
    np.save(meas_session / "ch2.npy", samples)
    (meas_session / "manifest.json").write_text(
        json.dumps({"session_type": "measurement", "sample_rate_hz": 100_000.0}), encoding="utf-8"
    )
    result_meas = orch.run(meas_session, _recipe(channels=("ch1", "ch2")))
    manifest_meas = json.loads(
        (result_meas.artifact_dir / "analysis-manifest.json").read_text(encoding="utf-8")
    )
    assert not any(
        item["name"] == "power_quality_settings.json" for item in manifest_meas["inputs"]["context"]
    )
    assert result_pq.artifact_key != result_meas.artifact_key


def test_power_quality_failure_isolated(tmp_path: Path) -> None:
    class FailingEngine(DefaultAnalysisEngine):
        @override
        def run_branch(self, name: str, context: BranchContext) -> BranchOutput:
            if name == "power_quality":
                raise RuntimeError("boom-power")
            return super().run_branch(name, context)

    session = tmp_path / "pq_fail"
    session.mkdir()
    np.save(session / "ch1.npy", _signal(0.5))
    (session / "manifest.json").write_text(
        json.dumps({"session_type": "power_quality", "sample_rate_hz": 100_000.0}),
        encoding="utf-8",
    )
    orch = AnalysisOrchestrator(
        engine=FailingEngine(),
        code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
    )
    result = orch.run(session, _recipe(channels=("ch1",)))
    assert result.failures == (
        BranchFailure(branch="power_quality", error_type="RuntimeError", message="boom-power"),
    )
    assert (session / "ch1.npy").is_file()
