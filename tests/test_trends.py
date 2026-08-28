"""B6-T25 trends: Theil-Sen slope, CUSUM, crest, discard 2000, EEPROM."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

from lnt.analysis_store import AnalysisRecipe, CodeIdentity
from lnt.analysis_v2 import AnalysisOrchestrator, BranchContext, SessionKind
from lnt.analysis_v2.engine import DefaultAnalysisEngine
from lnt.scope_io import NEVER_CANCELLED
from lnt.trends import TrendsSettings, compute_trends, trends_preset
from lnt.trends.models import trends_settings_hash


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


def _sine_rms_series(sr: float = 1000.0, duration_s: float = 2.0) -> np.ndarray:
    t = np.arange(int(sr * duration_s), dtype=np.float64) / sr
    return (np.sin(2 * np.pi * 50.0 * t)).astype(np.float32)


def test_linear_slope_0_1() -> None:
    sr = 1000.0
    n = int(sr * 4.0)
    t = np.arange(n, dtype=np.float64) / sr
    # linear drift 0.1 per second plus 50Hz sine
    drift = 0.1 * t
    sig = (np.sin(2 * np.pi * 50.0 * t) + drift).astype(np.float32)
    inv = compute_trends(sig, sample_rate_hz=sr, settings=trends_preset())
    # slope of RMS series should be positive near 0.1 (tolerance wide due to RMS)
    assert inv.theil_sen_slope > 0.03
    assert inv.theil_sen_slope < 0.3


def test_step_change_detected() -> None:
    sr = 1000.0
    n = int(sr * 4.0)
    t = np.arange(n, dtype=np.float64) / sr
    sig = np.sin(2 * np.pi * 50.0 * t).astype(np.float64)
    # step after 75% so it survives 2000-sample discard (2s at 1kHz)
    step_at = 3 * n // 4
    sig[step_at:] += 2.0
    inv = compute_trends(sig.astype(np.float32), sample_rate_hz=sr, settings=trends_preset())
    assert len(inv.change_points) >= 1
    # change point near 3.0s absolute -> ~1.0s in effective (2-4s) => 0.4-1.6 effective, 2.4-3.6 absolute
    cps = [c for c in inv.change_points]
    assert any(abs(c.time_s - 1.0) < 0.6 for c in cps)


def test_crest_1_414() -> None:
    sr = 10000.0
    t = np.arange(int(sr * 1.0), dtype=np.float64) / sr
    sine = np.sin(2 * np.pi * 50.0 * t).astype(np.float32)
    inv = compute_trends(sine, sample_rate_hz=sr, settings=trends_preset())
    # pure sine crest = sqrt2 ~1.414 (tolerance due to discard + windowing)
    assert 1.2 <= inv.crest_factor <= 1.65
    assert inv.rms_v > 0.5


def test_discard_2000() -> None:
    sr = 1000.0
    n = 10000
    t = np.arange(n, dtype=np.float64) / sr
    sig = np.sin(2 * np.pi * 50.0 * t).astype(np.float64)
    sig[:2000] = 100.0  # spike in discard zone
    inv = compute_trends(sig.astype(np.float32), sample_rate_hz=sr, settings=trends_preset())
    assert inv.discard_samples == 2000
    assert inv.effective_sample_count == n - 2000
    # crest should be normal sine, not spike-inflated
    assert inv.crest_factor < 2.0
    assert inv.peak_v < 5.0


def test_chunked_equivalence_and_hash() -> None:
    sr = 1000.0
    sig = _sine_rms_series(sr, 2.0)
    big = trends_preset()
    small = TrendsSettings(
        trends_version=big.trends_version,
        preset_name=big.preset_name,
        chunk_samples=4096,
        discard_samples=big.discard_samples,
        theil_sen_max_pairs=256,
        cusum_threshold_sigma=big.cusum_threshold_sigma,
        min_segment_length=big.min_segment_length,
    )
    inv_big = compute_trends(sig, sample_rate_hz=sr, settings=big)
    inv_small = compute_trends(sig, sample_rate_hz=sr, settings=small)
    assert abs(inv_big.crest_factor - inv_small.crest_factor) < 1e-6
    assert abs(inv_big.theil_sen_slope - inv_small.theil_sen_slope) < 1e-6
    # hash stable SHA256 sort_keys
    h = hashlib.sha256(
        json.dumps(
            big.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    assert inv_big.settings_hash == h
    assert len(h) == 64
    d = inv_big.to_dict()
    json.dumps(d, ensure_ascii=False)
    assert d["eeprom_verified"] is True
    assert len(d["eeprom_readback_hash"]) == 64


def test_eeprom_readback_simulation() -> None:
    sr = 1000.0
    sig = _sine_rms_series(sr, 1.0)
    inv = compute_trends(sig, sample_rate_hz=sr, settings=trends_preset())
    # EEPROM hash is SHA256 of core dict chunked 1M
    assert inv.eeprom_verified is True
    core = {
        "schema_version": inv.schema_version,
        "settings_hash": inv.settings_hash,
        "settings": inv.settings.to_dict(),
        "sample_rate_hz": float(sr),
        "sample_count": inv.sample_count,
        "effective_sample_count": inv.effective_sample_count,
        "duration_s": inv.duration_s,
        "discard_samples": inv.discard_samples,
        "rms_v": inv.rms_v,
        "peak_v": inv.peak_v,
        "crest_factor": inv.crest_factor,
        "theil_sen_slope": inv.theil_sen_slope,
        "theil_sen_intercept": inv.theil_sen_intercept,
        "change_points": [c.to_dict() for c in inv.change_points],
    }
    payload = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    digest = hashlib.sha256()
    for s in range(0, len(payload), 1_048_576):
        digest.update(payload[s : s + 1_048_576])
    assert inv.eeprom_readback_hash == digest.hexdigest()


def test_engine_branch_emits_trends_json_and_orchestrator() -> None:
    sr = 1000.0
    sig = _sine_rms_series(sr, 1.5)
    with tempfile.TemporaryDirectory() as tmp:
        session = Path(tmp) / "ses"
        session.mkdir()
        manifest = {
            "session_type": "trends",
            "sample_rate_hz": sr,
            "channels": ["ch1"],
            "channel_count": 1,
        }
        (session / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        np.save(session / "ch1.npy", sig)
        engine = DefaultAnalysisEngine()
        recipe = _recipe()
        ctx = BranchContext(
            kind=SessionKind.TRENDS,
            session_dir=session,
            sample_rate_hz=sr,
            channels=(sig,),
            recipe=recipe,
            cancellation=NEVER_CANCELLED,
        )
        out = engine.run_branch("trends", ctx)
        assert "trends.json" in out.files
        payload = json.loads(out.files["trends.json"].decode())
        assert "crest_factor" in payload
        assert "settings_hash" in payload
        assert "eeprom_readback_hash" in payload
        # orchestrator
        orch = AnalysisOrchestrator(
            engine=engine,
            code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
        )
        result = orch.run(session, recipe, project_legacy=False)
        assert (result.artifact_dir / "trends.json").exists()
        # failure isolation
        session2 = Path(tmp) / "ses2"
        session2.mkdir()
        (session2 / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        np.save(session2 / "ch1.npy", sig)

        class Boom:
            def run_branch(self, name: str, ctx: BranchContext):  # type: ignore[no-untyped-def]
                if name == "trends":
                    raise RuntimeError("boom-trends")
                return engine.run_branch(name, ctx)

        orch2 = AnalysisOrchestrator(
            engine=Boom(),
            code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
        )  # type: ignore[arg-type]
        res2 = orch2.run(session2, recipe, project_legacy=False)
        assert any(f.branch == "trends" for f in res2.failures)


def test_theil_sen_deterministic_and_sampling_256() -> None:
    sr = 1000.0
    sig = _sine_rms_series(sr, 1.0)
    settings = trends_preset()
    assert settings.theil_sen_max_pairs == 256
    assert settings.discard_samples == 2000
    assert settings.chunk_samples == 1_048_576
    inv1 = compute_trends(sig, sample_rate_hz=sr, settings=settings)
    inv2 = compute_trends(sig, sample_rate_hz=sr, settings=settings)
    assert inv1.theil_sen_slope == inv2.theil_sen_slope
    assert inv1.eeprom_readback_hash == inv2.eeprom_readback_hash
    d = inv1.to_dict()
    h2 = hashlib.sha256(
        json.dumps(
            settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    assert trends_settings_hash(settings) == h2
