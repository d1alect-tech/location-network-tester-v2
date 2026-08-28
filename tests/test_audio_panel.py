"""B3-T20: audio_panel 20Hz-3kHz bounded Welch PSD with up to 8 peaks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path  # noqa: TC003 - runtime fixture type

import numpy as np

from lnt.analysis_store import AnalysisRecipe
from lnt.analysis_v2 import BranchContext, SessionKind
from lnt.analysis_v2.engine import DefaultAnalysisEngine
from lnt.audio_panel import (
    AUDIO_HIGH_HZ,
    AUDIO_LOW_HZ,
    MAX_PEAKS,
    AudioPanelInventory,
    compute_audio_panel,
)
from lnt.scope_io import NEVER_CANCELLED


def _tone(sample_rate: float, freq: float, duration_s: float = 0.8) -> np.ndarray:
    count = int(sample_rate * duration_s)
    t = np.arange(count, dtype=np.float64) / sample_rate
    return (np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def test_constants() -> None:
    assert AUDIO_LOW_HZ == 20
    assert AUDIO_HIGH_HZ == 3000
    assert MAX_PEAKS == 8


def test_compute_audio_panel_detects_in_band_tones() -> None:
    sr = 48000.0
    sig = _tone(sr, 50.0) + 0.8 * _tone(sr, 1000.0) + 0.6 * _tone(sr, 2500.0)
    inv = compute_audio_panel(sig, sample_rate_hz=sr, chunk_samples=1_048_576)
    assert isinstance(inv, AudioPanelInventory)
    freqs = [p.frequency_hz for p in inv.peaks]
    assert any(abs(f - 50.0) < 15.0 for f in freqs), f"missing 50Hz in {freqs}"
    assert any(abs(f - 1000.0) < 15.0 for f in freqs), f"missing 1kHz in {freqs}"
    assert any(abs(f - 2500.0) < 20.0 for f in freqs), f"missing 2.5kHz in {freqs}"
    assert len(inv.peaks) <= MAX_PEAKS
    # sorted by prominence descending
    prominences = [p.prominence for p in inv.peaks]
    assert prominences == sorted(prominences, reverse=True)


def test_compute_audio_panel_excludes_out_of_band() -> None:
    sr = 48000.0
    sig = 1.5 * _tone(sr, 5000.0)
    inv = compute_audio_panel(sig, sample_rate_hz=sr, chunk_samples=1_048_576)
    freqs = [p.frequency_hz for p in inv.peaks]
    # 5kHz is out of 20-3000 band; should not appear
    assert all(abs(f - 5000.0) > 30.0 for f in freqs), f"5kHz leaked into band: {freqs}"


def test_compute_audio_panel_to_dict_json_safe_with_settings_hash() -> None:
    sr = 24000.0
    sig = _tone(sr, 440.0)
    inv = compute_audio_panel(sig, sample_rate_hz=sr, chunk_samples=262144)
    payload = inv.to_dict()
    # JSON roundtrip
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    loaded = json.loads(text)
    assert loaded["settings_hash"] == inv.settings_hash
    assert len(loaded["settings_hash"]) == 64
    assert loaded["peaks"] == [p.to_dict() for p in inv.peaks]
    # hash stable from settings dict
    expected = hashlib.sha256(
        json.dumps(
            inv.settings.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    assert inv.settings_hash == expected
    assert payload["schema_version"] == 1
    assert payload["low_hz"] == AUDIO_LOW_HZ
    assert payload["high_hz"] == AUDIO_HIGH_HZ


def test_compute_audio_panel_bounded_and_capped() -> None:
    sr = 100000.0
    freqs = [60, 120, 180, 240, 360, 480, 600, 900, 1100, 1500, 2000, 2800]
    parts = [_tone(sr, f) for f in freqs]
    sig = parts[0]
    for part in parts[1:]:
        sig = sig + part
    inv = compute_audio_panel(sig, sample_rate_hz=sr, chunk_samples=8192)
    assert len(inv.peaks) <= 8
    assert inv.band_rms_v >= 0.0
    assert inv.segment_count >= 1
    assert inv.resolution_hz > 0


def test_engine_audio_panel_branch_emits_file(tmp_path: Path) -> None:
    sr = 48000.0
    sig = _tone(sr, 440.0, duration_s=0.4)

    engine = DefaultAnalysisEngine()
    recipe = AnalysisRecipe.from_mapping(
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
    )
    ctx = BranchContext(
        kind=SessionKind.MEASUREMENT,
        session_dir=tmp_path,
        sample_rate_hz=sr,
        channels=(sig,),
        recipe=recipe,
        cancellation=NEVER_CANCELLED,
    )
    out = engine.run_branch("audio_panel", ctx)
    assert "audio_panel.json" in out.files
    payload = json.loads(out.files["audio_panel.json"].decode())
    assert payload["schema_version"] == 1
    assert isinstance(payload["settings_hash"], str)
    assert len(payload["settings_hash"]) == 64
