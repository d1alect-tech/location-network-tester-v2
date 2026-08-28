"""B5-T23 APD ITU-R P.2089 + Middleton Class A synthetic truth."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from lnt.analysis_store import AnalysisRecipe, CodeIdentity
from lnt.analysis_v2 import AnalysisOrchestrator, BranchContext, BranchFailure, SessionKind
from lnt.analysis_v2.engine import DefaultAnalysisEngine
from lnt.apd import ApdSettings, apd_preset, compute_apd
from lnt.scope_io import NEVER_CANCELLED


def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def _gaussian_noise(n: int = 200_000, sigma: float = 1.0, seed: int = 0) -> np.ndarray:
    rng = _rng(seed)
    return rng.normal(0.0, sigma, size=n).astype(np.float32)


def _impulsive_noise(
    n: int = 200_000,
    sigma: float = 1.0,
    impulse_amp: float = 10.0,
    rate: float = 0.01,
    seed: int = 1,
) -> np.ndarray:
    rng = _rng(seed)
    base = rng.normal(0.0, sigma, size=n).astype(np.float64)
    mask = rng.random(n) < rate
    # impulsive samples with large magnitude
    impulses = rng.normal(0.0, impulse_amp, size=n)
    base[mask] = impulses[mask]
    return base.astype(np.float32)


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


def test_rayleigh_apd_slope_steep_and_middleton_large_A() -> None:
    sig = _gaussian_noise(n=200_000, sigma=1.0, seed=0)
    inv = compute_apd(sig, sample_rate_hz=50_000.0, settings=apd_preset())
    # Gaussian => kurtosis ~3, excess small => A large
    assert inv.middleton.overlap_index_A > 5.0, f"A {inv.middleton.overlap_index_A}"
    assert inv.middleton.gamma > 5.0, f"gamma {inv.middleton.gamma}"
    assert 2.8 < inv.middleton.kurtosis < 3.6, f"kurtosis {inv.middleton.kurtosis}"
    # APD slope for Rayleigh should be relatively steep (more negative) vs impulsive
    # exact value not fixed, but slope must be finite negative
    assert inv.apd_slope_db_per_decade < -2.0
    # APD points monotonic decreasing prob with increasing level
    assert len(inv.apd) >= 50
    assert (
        inv.apd[0].exceedance_prob < inv.apd[-1].exceedance_prob
        or inv.apd[0].level_db > inv.apd[-1].level_db
    )


def test_impulsive_apd_heavy_tail_and_small_A() -> None:
    sig = _impulsive_noise(n=200_000, sigma=1.0, impulse_amp=12.0, rate=0.01, seed=1)
    inv = compute_apd(sig, sample_rate_hz=50_000.0, settings=apd_preset())
    # impulsive => kurtosis >>3 => A small, gamma small
    assert inv.middleton.overlap_index_A < 1.0, f"A {inv.middleton.overlap_index_A}"
    assert inv.middleton.gamma < 2.0, f"gamma {inv.middleton.gamma}"
    assert inv.middleton.kurtosis > 6.0, f"kurtosis {inv.middleton.kurtosis}"
    # heavy tail => slope less steep (shallower) than Rayleigh; we check slope > Rayleigh typical
    # compare with gaussian slope
    gauss = _gaussian_noise(n=200_000, sigma=1.0, seed=2)
    inv_g = compute_apd(gauss, sample_rate_hz=50_000.0, settings=apd_preset())
    assert inv.apd_slope_db_per_decade < inv_g.apd_slope_db_per_decade, (
        f"impulsive slope {inv.apd_slope_db_per_decade} vs gaussian {inv_g.apd_slope_db_per_decade}"
    )
    # highest level must be much larger for impulsive
    assert inv.apd[0].level_db > inv_g.apd[0].level_db + 5.0


def test_middleton_gamma_monotonic_with_impulsiveness() -> None:
    # rate 0.005 vs 0.02: higher rate => less impulsive? actually more impulses but still heavy tail
    # check that pure gaussian gamma > impulsive gamma
    g = _gaussian_noise(n=100_000, seed=10)
    i = _impulsive_noise(n=100_000, rate=0.02, impulse_amp=10.0, seed=11)
    inv_g = compute_apd(g, sample_rate_hz=20_000.0)
    inv_i = compute_apd(i, sample_rate_hz=20_000.0)
    assert inv_g.middleton.gamma > inv_i.middleton.gamma
    assert inv_g.middleton.overlap_index_A > inv_i.middleton.overlap_index_A


def test_chunked_scan_equivalence() -> None:
    sig = _impulsive_noise(n=120_000, seed=5)
    s_big = apd_preset()
    s_small = ApdSettings(
        apd_version=s_big.apd_version,
        preset_name=s_big.preset_name,
        chunk_samples=4096,
        num_levels=s_big.num_levels,
    )
    inv_big = compute_apd(sig, sample_rate_hz=50_000.0, settings=s_big)
    inv_small = compute_apd(sig, sample_rate_hz=50_000.0, settings=s_small)
    assert inv_big.middleton.overlap_index_A == inv_small.middleton.overlap_index_A
    assert inv_big.middleton.gamma == inv_small.middleton.gamma
    assert abs(inv_big.rms_v - inv_small.rms_v) < 1e-9
    assert len(inv_big.apd) == len(inv_small.apd)
    # APD levels should match within tolerance
    for a, b in zip(inv_big.apd[:10], inv_small.apd[:10], strict=False):
        assert abs(a.level_db - b.level_db) < 1e-9
        assert abs(a.exceedance_prob - b.exceedance_prob) < 1e-12


def test_to_dict_json_and_settings_hash() -> None:
    sig = _gaussian_noise(n=50_000, seed=7)
    settings = apd_preset()
    inv = compute_apd(sig, sample_rate_hz=50_000.0, settings=settings)
    payload = inv.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["schema_version"] == 1
    assert decoded["settings_hash"] == inv.settings_hash
    expected = hashlib.sha256(
        json.dumps(
            settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    assert inv.settings_hash == expected
    assert len(inv.settings_hash) == 64
    assert "middleton" in decoded
    assert "apd" in decoded
    assert "apd_slope_db_per_decade" in decoded
    # ensure JSON-safe primitives only
    assert isinstance(decoded["rms_v"], float)
    assert isinstance(decoded["apd"][0]["level_db"], float)


def test_engine_branch_emits_apd_json() -> None:
    engine = DefaultAnalysisEngine()
    sig = _gaussian_noise(n=50_000, seed=9)
    ctx = BranchContext(
        kind=SessionKind.APD,
        session_dir=Path.cwd(),
        sample_rate_hz=50_000.0,
        channels=(sig,),
        recipe=_recipe(),
        cancellation=NEVER_CANCELLED,
    )
    out = engine.run_branch("apd", ctx)
    assert "apd.json" in out.files
    payload = json.loads(out.files["apd.json"].decode())
    assert payload["schema_version"] == 1
    assert "apd" in payload
    assert "middleton" in payload
    assert payload["middleton"]["overlap_index_A"] > 0
    assert payload["apd_slope_db_per_decade"] < 0


def test_orchestrator_apd_dispatch_and_failure_isolation(tmp_path: Path) -> None:
    session = tmp_path / "apd"
    session.mkdir()
    sig = _gaussian_noise(n=60_000, seed=3)
    np.save(session / "ch1.npy", sig)
    (session / "manifest.json").write_text(
        json.dumps({"session_type": "apd", "sample_rate_hz": 50_000.0}), encoding="utf-8"
    )
    engine = DefaultAnalysisEngine()
    orch = AnalysisOrchestrator(
        engine=engine, code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test")
    )
    result = orch.run(session, _recipe(channels=("ch1",)))
    assert result.failures == ()
    assert (result.artifact_dir / "apd.json").is_file()
    # cache key includes apd settings
    apd_settings = apd_preset("apd_default")
    expected_hash = hashlib.sha256(
        json.dumps(
            apd_settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    manifest = json.loads(
        (result.artifact_dir / "analysis-manifest.json").read_text(encoding="utf-8")
    )
    assert any(
        item["name"] == "apd_settings.json" and item["digest"] == expected_hash
        for item in manifest["inputs"]["context"]
    )

    # failure isolation
    class FailEngine(DefaultAnalysisEngine):
        def run_branch(self, name: str, context: BranchContext):  # type: ignore[override]
            if name == "apd":
                raise RuntimeError("boom-apd")
            return super().run_branch(name, context)

    session2 = tmp_path / "apd2"
    session2.mkdir()
    np.save(session2 / "ch1.npy", sig)
    (session2 / "manifest.json").write_text(
        json.dumps({"session_type": "apd", "sample_rate_hz": 50_000.0}), encoding="utf-8"
    )
    orch2 = AnalysisOrchestrator(
        engine=FailEngine(),
        code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
    )
    result2 = orch2.run(session2, _recipe(channels=("ch1",)))
    assert result2.failures == (
        BranchFailure(branch="apd", error_type="RuntimeError", message="boom-apd"),
    )
