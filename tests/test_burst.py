"""B5-T24 burst EFT 5/50нс 5к/100кГц 15/300мс: envelope Hilbert, chunked, branch."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

from lnt.analysis_store import AnalysisRecipe, CodeIdentity
from lnt.analysis_v2 import AnalysisOrchestrator, BranchContext, SessionKind
from lnt.analysis_v2.engine import DefaultAnalysisEngine
from lnt.burst import BurstSettings, burst_preset, detect_bursts
from lnt.scope_io import NEVER_CANCELLED


def _recipe(channels: tuple[str, ...] = ("ch1",)) -> AnalysisRecipe:
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


def _quiet(duration_s: float = 1.2, sr: float = 1_000_000.0) -> np.ndarray:
    rng = np.random.default_rng(1)
    n = int(sr * duration_s)
    return rng.normal(0, 0.05, size=n).astype(np.float32)


def _burst_train(
    duration_s: float = 1.2,
    sr: float = 1_000_000.0,
    amp: float = 5.0,
    offset_s: float = 0.1,
    period_s: float = 0.3,
    burst_ms: float = 15.0,
) -> np.ndarray:
    n = int(sr * duration_s)
    base = _quiet(duration_s, sr).astype(np.float64)
    burst_samp = int(burst_ms * 1e-3 * sr)
    k = 0
    while True:
        start = int((offset_s + k * period_s) * sr)
        end = min(n, start + burst_samp)
        if start >= n:
            break
        tt = np.arange(end - start, dtype=np.float64) / sr
        # 5kHz repetition inside burst + noise
        base[start:end] = amp * (1.0 + 0.3 * np.sin(2.0 * np.pi * 5000.0 * tt))
        k += 1
    return base.astype(np.float32)


def test_quiet_zero_bursts() -> None:
    sig = _quiet()
    inv = detect_bursts(sig, sample_rate_hz=1_000_000.0, settings=burst_preset())
    assert inv.burst_count == 0
    assert inv.bursts_per_second == 0.0
    assert inv.sequence_count == 0
    assert inv.bursts == ()


def test_single_burst_detected() -> None:
    sig = _burst_train(duration_s=0.6, amp=5.0, offset_s=0.2, period_s=10.0)
    inv = detect_bursts(sig, sample_rate_hz=1_000_000.0, settings=burst_preset())
    assert inv.burst_count == 1
    b = inv.bursts[0]
    # 15ms ± wide due to Hilbert tails
    assert 10.0 <= b.duration_ms <= 55.0
    assert 0.05 <= b.peak_envelope_v <= 20.0
    assert 0.05 <= b.start_time_s <= 0.35
    assert inv.sequence_count == 1


def test_burst_train_5kHz_rep_count_and_period() -> None:
    sig = _burst_train(duration_s=1.2, amp=5.0, offset_s=0.1, period_s=0.3)
    inv = detect_bursts(sig, sample_rate_hz=1_000_000.0, settings=burst_preset())
    assert inv.burst_count == 4
    assert 3.0 <= inv.bursts_per_second <= 4.0
    # period ≈300ms, sequence groups all
    assert inv.sequence_count == 1
    seq = inv.sequences[0]
    assert seq.burst_count == 4
    assert 250.0 <= seq.period_ms <= 350.0
    # bursts spaced ~300ms
    for i in range(len(inv.bursts) - 1):
        gap = inv.bursts[i + 1].start_time_s - inv.bursts[i].start_time_s
        assert 0.25 <= gap <= 0.35


def test_gap_separates_sequences() -> None:
    sig = _burst_train(duration_s=2.0, amp=5.0, offset_s=0.1, period_s=0.3)
    # add extra gap by removing middle bursts via zeroing 0.6-1.2 region
    # instead create two clusters with 0.8 gap
    sr = 1_000_000.0
    n = int(sr * 2.0)
    base = _quiet(2.0, sr).astype(np.float64)
    # cluster1: 0.1,0.4
    for off in [0.1, 0.4]:
        s = int(off * sr)
        e = s + int(0.015 * sr)
        base[s:e] = 5.0
    # cluster2: 1.3,1.6 (gap 0.9s)
    for off in [1.3, 1.6]:
        s = int(off * sr)
        e = s + int(0.015 * sr)
        base[s:e] = 5.0
    inv = detect_bursts(base.astype(np.float32), sample_rate_hz=sr, settings=burst_preset())
    assert inv.burst_count == 4
    assert inv.sequence_count == 2
    assert inv.sequences[0].burst_count == 2
    assert inv.sequences[1].burst_count == 2


def test_amplitude_threshold() -> None:
    high = _burst_train(duration_s=0.6, amp=5.0)
    low = _burst_train(duration_s=0.6, amp=0.2)
    inv_high = detect_bursts(high, sample_rate_hz=1_000_000.0, settings=burst_preset())
    inv_low = detect_bursts(low, sample_rate_hz=1_000_000.0, settings=burst_preset())
    assert inv_high.burst_count >= 1
    assert inv_low.burst_count == 0


def test_chunked_equivalence_and_json_hash() -> None:
    sig = _burst_train(duration_s=1.2, amp=5.0)
    s_big = burst_preset()
    s_small = BurstSettings(
        burst_version=s_big.burst_version,
        preset_name=s_big.preset_name,
        threshold_factor=s_big.threshold_factor,
        min_burst_duration_ms=s_big.min_burst_duration_ms,
        max_burst_duration_ms=s_big.max_burst_duration_ms,
        burst_duration_ms=s_big.burst_duration_ms,
        burst_period_ms=s_big.burst_period_ms,
        chunk_samples=4096,
    )
    inv_big = detect_bursts(sig, sample_rate_hz=1_000_000.0, settings=s_big)
    inv_small = detect_bursts(sig, sample_rate_hz=1_000_000.0, settings=s_small)
    assert inv_big.burst_count == inv_small.burst_count
    # hash stable
    h1 = s_big.to_dict()
    h2 = hashlib.sha256(
        json.dumps(h1, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert inv_big.settings_hash == h2
    # to_dict JSON-safe
    d = inv_big.to_dict()
    json.dumps(d, ensure_ascii=False)


def test_engine_branch_emits_burst_json_and_orchestrator() -> None:
    sr = 1_000_000.0
    sig = _burst_train(duration_s=0.6, amp=5.0)
    with tempfile.TemporaryDirectory() as tmp:
        session = Path(tmp) / "ses"
        session.mkdir()
        manifest = {
            "session_type": "burst",
            "sample_rate_hz": sr,
            "channels": ["ch1"],
            "channel_count": 1,
        }
        (session / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        np.save(session / "ch1.npy", sig)
        engine = DefaultAnalysisEngine()
        recipe = _recipe()
        context = BranchContext(
            kind=SessionKind.BURST,
            session_dir=session,
            sample_rate_hz=sr,
            channels=(sig,),
            recipe=recipe,
            cancellation=NEVER_CANCELLED,
        )
        out = engine.run_branch("burst", context)
        assert "burst.json" in out.files
        payload = json.loads(out.files["burst.json"].decode())
        assert payload["burst_count"] >= 1
        assert "settings_hash" in payload
        # orchestrator + failure isolation
        orch = AnalysisOrchestrator(
            engine=engine,
            code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
        )
        result = orch.run(session, recipe, project_legacy=False)
        assert (result.artifact_dir / "burst.json").exists()
        # failure isolation: boom-burst -> BranchFailure on fresh session
        session2 = Path(tmp) / "ses2"
        session2.mkdir()
        (session2 / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        np.save(session2 / "ch1.npy", sig)

        class Boom:
            def run_branch(self, name: str, ctx: BranchContext):  # type: ignore[no-untyped-def]
                if name == "burst":
                    raise RuntimeError("boom-burst")
                return engine.run_branch(name, ctx)

        orch2 = AnalysisOrchestrator(
            engine=Boom(),
            code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
        )  # type: ignore[arg-type]
        res2 = orch2.run(session2, recipe, project_legacy=False)
        assert any(f.branch == "burst" for f in res2.failures)
