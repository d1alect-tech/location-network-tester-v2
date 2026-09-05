"""B4-T21 harmonics IEC 61000-4-7 synthetic truth."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lnt.analysis_store import AnalysisRecipe
from lnt.analysis_v2 import BranchContext, SessionKind
from lnt.analysis_v2.engine import DefaultAnalysisEngine
from lnt.harmonics import compute_harmonics
from lnt.scope_io import NEVER_CANCELLED


def _sine(duration_s: float, rate: float, freq: float, amp: float = 1.0) -> np.ndarray:
    t = np.arange(round(rate * duration_s), dtype=np.float64) / rate
    return (amp * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def _mix(duration_s: float, rate: float, components: list[tuple[float, float]]) -> np.ndarray:
    t = np.arange(round(rate * duration_s), dtype=np.float64) / rate
    sig = np.zeros_like(t)
    for freq, amp in components:
        sig += amp * np.sin(2.0 * np.pi * freq * t)
    return sig.astype(np.float32)


def test_pure_50hz_thd_near_zero() -> None:
    rate = 10000.0
    sig = _sine(2.4, rate, 50.0, 1.0)
    inv = compute_harmonics(sig, sample_rate_hz=rate)
    assert inv.window_count == 12
    for w in inv.windows:
        assert w.thd < 0.02, f"THD {w.thd}"
        assert 0.6 < w.fundamental_rms < 0.9  # ~0.707
        assert w.h_subgroups[0] > 0.6  # H1
        assert w.h_subgroups[1] < 0.02  # H2 near zero
        assert w.h_subgroups[2] < 0.02  # H3


def test_h3_10_percent() -> None:
    rate = 10000.0
    sig = _mix(2.4, rate, [(50.0, 1.0), (150.0, 0.1)])
    inv = compute_harmonics(sig, sample_rate_hz=rate)
    for w in inv.windows:
        # H3 amplitude 0.1/1.0 => RMS ratio 0.1 => subgroup ratio ~0.1
        h3 = w.h_subgroups[2]
        h1 = w.h_subgroups[0]
        ratio = h3 / h1 if h1 > 0 else 0
        assert 0.08 < ratio < 0.12, f"H3 ratio {ratio}"
        assert 0.09 < w.thd < 0.13


def test_h3_h5_combined_thd() -> None:
    rate = 10000.0
    sig = _mix(2.4, rate, [(50.0, 1.0), (150.0, 0.1), (250.0, 0.1)])
    inv = compute_harmonics(sig, sample_rate_hz=rate)
    for w in inv.windows:
        # THD = sqrt(0.1^2+0.1^2)=0.141
        assert 0.12 < w.thd < 0.16
        assert 0.08 < w.h_subgroups[2] / w.h_subgroups[0] < 0.12
        assert 0.08 < w.h_subgroups[4] / w.h_subgroups[0] < 0.12


def test_interharmonic_75hz_in_ihg() -> None:
    rate = 10000.0
    sig = _mix(2.4, rate, [(50.0, 1.0), (75.0, 0.1)])
    inv = compute_harmonics(sig, sample_rate_hz=rate)
    for w in inv.windows:
        # Interharmonic between H1 and H2 => IHG1 should capture energy
        ihg1 = w.ihg[0]
        h1 = w.h_subgroups[0]
        assert ihg1 / h1 > 0.08, f"IHG ratio {ihg1 / h1}"
        # THD should remain low (interharmonic not counted)
        assert w.thd < 0.05


def test_frequency_offset_sync() -> None:
    rate = 10000.0
    # 50.2 Hz offset: without sync leakage would inflate THD, with sync THD stays low
    sig = _sine(2.4, rate, 50.2, 1.0)
    inv = compute_harmonics(sig, sample_rate_hz=rate)
    # estimated grid should be near 50.2
    assert 49.5 < inv.estimated_grid_frequency_hz < 51.0
    for w in inv.windows:
        assert w.thd < 0.05, f"THD with offset {w.thd}"


def test_long_record_takes_first_2_4s() -> None:
    rate = 10000.0
    sig = _sine(5.0, rate, 50.0, 1.0)
    inv = compute_harmonics(sig, sample_rate_hz=rate)
    assert inv.record_duration_s == 2.4
    assert inv.window_count == 12
    assert len(inv.windows) == 12


def test_engine_branch_files() -> None:
    rate = 10000.0
    sig = _sine(2.4, rate, 50.0, 1.0)
    engine = DefaultAnalysisEngine()
    ctx = BranchContext(
        kind=SessionKind.HARMONICS,
        session_dir=Path.cwd(),
        sample_rate_hz=rate,
        channels=(sig,),
        recipe=AnalysisRecipe.from_mapping(
            {
                "schema_version": 1,
                "mode": "standard",
                "channels": ["ch1"],
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
        ),
        cancellation=NEVER_CANCELLED,
    )
    out = engine.run_branch("harmonics", ctx)
    assert "harmonics.json" in out.files
    assert "harmonic_spectra.json" in out.files
