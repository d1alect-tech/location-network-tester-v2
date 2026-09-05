"""B4-T22: нотчинг IEEE 519 — глубина, площадь, jitter лишних нулей."""

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
from lnt.notching import NotchingSettings, detect_notching, notching_preset
from lnt.scope_io import NEVER_CANCELLED


def _sine(
    duration_s: float = 0.5, sample_rate: float = 100_000.0, peak_v: float = 325.0
) -> np.ndarray:
    t = np.arange(round(sample_rate * duration_s), dtype=np.float64) / sample_rate
    return (peak_v * np.sin(2.0 * np.pi * 50.0 * t)).astype(np.float32)


def _sine_with_notches(
    duration_s: float = 0.5,
    sample_rate: float = 100_000.0,
    peak_v: float = 325.0,
    depth_v: float = 100.0,
    width_us: float = 200.0,
    count: int = 3,
) -> np.ndarray:
    arr = _sine(duration_s, sample_rate, peak_v).astype(np.float64)
    width_samples = max(1, round(width_us * 1e-6 * sample_rate))
    step = int(arr.size // (count + 1))
    # offset to peaks (quarter period = 5ms at 50Hz) to avoid zero-crossing blind spot
    peak_offset = round(sample_rate * 0.005)
    for k in range(count):
        centre = (k + 1) * step + peak_offset
        if centre >= arr.size - width_samples:
            centre = (k + 1) * step  # fallback if near end
        lo = max(0, centre - width_samples // 2)
        hi = min(arr.size, lo + width_samples)
        # reduce magnitude toward zero
        peak_sign = np.sign(arr[lo:hi])
        mag = np.abs(arr[lo:hi])
        new_mag = np.maximum(mag - depth_v, 0.0)
        # fix zero_mask assignment via direct slice
        segment = arr[lo:hi].copy()
        segment = peak_sign * new_mag
        zero_mask = peak_sign == 0
        if np.any(zero_mask):
            segment[zero_mask] = -depth_v * 0.1
        arr[lo:hi] = segment
    return arr.astype(np.float32)


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


def test_clean_sine_zero_notches() -> None:
    sig = _sine(duration_s=0.6)
    inv = detect_notching(sig, sample_rate_hz=100_000.0, settings=notching_preset())
    assert inv.notch_count == 0
    assert inv.spurious_crossings == 0
    assert inv.notches_per_second == 0.0
    assert inv.notches == ()


def test_single_notch_depth_and_width() -> None:
    sig = _sine_with_notches(duration_s=0.4, depth_v=100.0, width_us=200.0, count=1)
    inv = detect_notching(sig, sample_rate_hz=100_000.0, settings=notching_preset())
    assert inv.notch_count == 1
    n = inv.notches[0]
    # глубина 100 В +-30% (из-за сглаживания LF)
    assert 60.0 <= n.depth_v <= 130.0
    # длительность ~200 мкс +-80
    assert 120.0 <= n.duration_us <= 320.0
    # площадь ~ depth*width
    assert 8000.0 <= n.area_v_us <= 30000.0


def test_multiple_notches_count_per_second() -> None:
    sig = _sine_with_notches(duration_s=1.0, depth_v=100.0, width_us=200.0, count=5)
    inv = detect_notching(sig, sample_rate_hz=100_000.0, settings=notching_preset())
    assert inv.notch_count == 5
    # 5 за 1 сек => 5 1/с
    assert 4.5 <= inv.notches_per_second <= 5.5


def test_area_depth_synthetic_known() -> None:
    sig = _sine_with_notches(duration_s=0.5, depth_v=80.0, width_us=300.0, count=2)
    inv = detect_notching(sig, sample_rate_hz=100_000.0, settings=notching_preset())
    assert inv.notch_count == 2
    for n in inv.notches:
        assert 50.0 <= n.depth_v <= 110.0
        assert n.area_v_us > 8000.0
        # area ≈ depth * duration
        assert n.area_v_us <= n.depth_v * n.duration_us * 1.2


def test_chunked_scan_equivalence() -> None:
    sig = _sine_with_notches(duration_s=0.6, depth_v=100.0, width_us=200.0, count=3)
    s_big = notching_preset()
    s_small = NotchingSettings(
        notching_version=s_big.notching_version,
        preset_name=s_big.preset_name,
        lowpass_hz=s_big.lowpass_hz,
        threshold_pct=s_big.threshold_pct,
        min_width_us=s_big.min_width_us,
        chunk_samples=4096,
    )
    inv_big = detect_notching(sig, sample_rate_hz=100_000.0, settings=s_big)
    inv_small = detect_notching(sig, sample_rate_hz=100_000.0, settings=s_small)
    assert inv_big.notch_count == inv_small.notch_count
    assert inv_big.spurious_crossings == inv_small.spurious_crossings


def test_to_dict_json_and_settings_hash() -> None:
    sig = _sine(duration_s=0.4)
    settings = notching_preset()
    inv = detect_notching(sig, sample_rate_hz=100_000.0, settings=settings)
    payload = inv.to_dict()
    # JSON-safe
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["schema_version"] == 1
    assert decoded["settings_hash"] == inv.settings_hash
    expected_hash = hashlib.sha256(
        json.dumps(
            settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    assert inv.settings_hash == expected_hash
    assert len(inv.settings_hash) == 64


def test_engine_branch_emits_notching_json() -> None:
    engine = DefaultAnalysisEngine()
    sig = _sine(duration_s=0.4)
    tmp = Path.cwd()
    ctx = BranchContext(
        kind=SessionKind.NOTCHING,
        session_dir=tmp,
        sample_rate_hz=100_000.0,
        channels=(sig,),
        recipe=_recipe(),
        cancellation=NEVER_CANCELLED,
    )
    out = engine.run_branch("notching", ctx)
    assert "notching.json" in out.files
    payload = json.loads(out.files["notching.json"].decode())
    assert payload["schema_version"] == 1
    assert "notches" in payload
    assert "notches_per_second" in payload


def test_orchestrator_notching_dispatch(tmp_path: Path) -> None:
    session = tmp_path / "notch"
    session.mkdir()
    sig = _sine(duration_s=0.5)
    np.save(session / "ch1.npy", sig)
    (session / "manifest.json").write_text(
        json.dumps({"session_type": "notching", "sample_rate_hz": 100_000.0}), encoding="utf-8"
    )
    engine = DefaultAnalysisEngine()
    orch = AnalysisOrchestrator(
        engine=engine, code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test")
    )
    result = orch.run(session, _recipe(channels=("ch1",)))
    assert result.failures == ()
    assert (result.artifact_dir / "notching.json").is_file()

    # failure isolation
    class FailEngine(DefaultAnalysisEngine):
        @override
        def run_branch(self, name: str, context: BranchContext) -> BranchOutput:
            if name == "notching":
                raise RuntimeError("boom-notching")
            return super().run_branch(name, context)

    session2 = tmp_path / "notch2"
    session2.mkdir()
    np.save(session2 / "ch1.npy", sig)
    (session2 / "manifest.json").write_text(
        json.dumps({"session_type": "notching", "sample_rate_hz": 100_000.0}), encoding="utf-8"
    )
    orch2 = AnalysisOrchestrator(
        engine=FailEngine(),
        code_identity=CodeIdentity(lnt="test", numpy=np.__version__, scipy="test"),
    )
    result2 = orch2.run(session2, _recipe(channels=("ch1",)))
    assert result2.failures == (
        BranchFailure(branch="notching", error_type="RuntimeError", message="boom-notching"),
    )
