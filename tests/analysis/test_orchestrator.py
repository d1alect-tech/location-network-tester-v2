from __future__ import annotations

# ruff: noqa: TC003 - behavior fixtures favor readable full contracts
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import override

import numpy as np
import pytest

from lnt.analysis_store import AnalysisRecipe, CodeIdentity
from lnt.analysis_v2 import (
    AnalysisCancelledError,
    AnalysisOrchestrator,
    BranchContext,
    BranchFailure,
    BranchOutput,
    SessionKind,
)
from lnt.scope_io import CancellationToken


def _recipe(*, channels: tuple[str, ...] = ("ch1", "ch2")) -> AnalysisRecipe:
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


def _session(path: Path, kind: SessionKind, *, channels: int = 2) -> Path:
    path.mkdir()
    np.save(path / "ch1.npy", np.linspace(-1, 1, 1024, dtype=np.float32))
    if channels == 2:
        np.save(path / "ch2.npy", np.linspace(1, -1, 1024, dtype=np.float32))
    (path / "manifest.json").write_text(
        json.dumps({"session_type": kind.value, "sample_rate_hz": 1000.0}), encoding="utf-8"
    )
    return path


@dataclass(slots=True)
class RecordingEngine:
    fail: frozenset[str] = frozenset()
    calls: list[tuple[str, SessionKind, int]] = field(default_factory=list)

    def run_branch(self, name: str, context: BranchContext) -> BranchOutput:
        kind = context.kind
        channel_count = len(context.channels)
        self.calls.append((name, kind, channel_count))
        if name in self.fail:
            raise RuntimeError(f"boom-{name}")
        return BranchOutput(files={f"{name}.json": json.dumps({"branch": name}).encode()})


class SlowEngine(RecordingEngine):
    @override
    def run_branch(self, name: str, context: BranchContext) -> BranchOutput:
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            context.checkpoint()
            time.sleep(0.01)
        return super().run_branch(name, context)


def _orchestrator(engine: RecordingEngine) -> AnalysisOrchestrator:
    return AnalysisOrchestrator(
        engine=engine,
        code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
    )


@pytest.mark.parametrize(
    ("kind", "channels", "expected"),
    [
        (SessionKind.MEASUREMENT, 2, {"psd", "spectrogram", "events", "features", "correction"}),
        (SessionKind.MEASUREMENT, 1, {"psd", "spectrogram", "events", "features", "correction"}),
        (SessionKind.SELF_NOISE, 1, {"psd", "spectrogram", "events", "features"}),
        (SessionKind.LINE_QUALITY, 1, {"line_quality"}),
    ],
)
def test_dispatches_session_kind_and_channel_recipe(
    tmp_path: Path, kind: SessionKind, channels: int, expected: set[str]
) -> None:
    engine = RecordingEngine()
    session = _session(tmp_path / kind.value, kind, channels=channels)

    result = _orchestrator(engine).run(
        session, _recipe(channels=("ch1",) if channels == 1 else ("ch1", "ch2"))
    )

    assert {name for name, _, _ in engine.calls} == expected
    assert result.failures == ()
    assert result.artifact_dir.is_dir()


def test_optional_failure_is_recorded_without_invalidating_other_outputs(tmp_path: Path) -> None:
    engine = RecordingEngine(fail=frozenset({"events"}))
    session = _session(tmp_path / "measurement", SessionKind.MEASUREMENT)

    result = _orchestrator(engine).run(session, _recipe())

    assert result.failures == (
        BranchFailure(branch="events", error_type="RuntimeError", message="boom-events"),
    )
    assert (result.artifact_dir / "psd.json").is_file()
    assert (session / "ch1.npy").is_file()


def test_valid_cache_hit_skips_engines_but_tamper_is_quarantined_and_recomputed(
    tmp_path: Path,
) -> None:
    engine = RecordingEngine()
    session = _session(tmp_path / "measurement", SessionKind.MEASUREMENT)
    orchestrator = _orchestrator(engine)
    first = orchestrator.run(session, _recipe())
    call_count = len(engine.calls)

    cached = orchestrator.run(session, _recipe())
    (first.artifact_dir / "psd.json").write_bytes(b"tampered")
    repaired = orchestrator.run(session, _recipe())

    assert cached.cache_hit is True
    assert len(engine.calls) == call_count * 2
    assert repaired.cache_hit is False
    assert (
        hashlib.sha256((repaired.artifact_dir / "psd.json").read_bytes()).hexdigest()
        != hashlib.sha256(b"tampered").hexdigest()
    )
    assert tuple((session / "analyses").glob(f"{first.artifact_key}.invalid-*"))


def test_cancellation_is_acknowledged_within_500_ms_and_publishes_no_partial(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path / "measurement", SessionKind.MEASUREMENT)
    started = time.monotonic()
    token = CancellationToken(is_cancelled=lambda: time.monotonic() - started >= 0.05)

    with pytest.raises(AnalysisCancelledError):
        _orchestrator(SlowEngine()).run(session, _recipe(), cancellation=token, chunk_seconds=0.02)

    assert time.monotonic() - started < 0.5
    assert not tuple((session / "analyses").glob("*.partial-*"))
