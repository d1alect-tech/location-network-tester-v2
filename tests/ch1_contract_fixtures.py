from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

Float32Array = NDArray[np.float32]

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class Ch1SessionSpec:
    session_id: str
    session_type: str
    source: str
    sample_rate_hz: float
    duration_s: float
    ch1_setup: dict[str, object]
    baseline_session: str | None
    range_code: int = 1
    unit: str = "V"
    probe_multiplier: float = 1.0
    calibration_used: bool = False
    ch1_clip_low_count: int = 0
    ch1_clip_high_count: int = 0
    include_acquisition_telemetry: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class ToneCaptureSpec:
    sample_rate_hz: float
    duration_s: float
    tone_frequency_hz: float
    source_amplitude_v: float
    transfer_gain: float
    baseline_sigma_v: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ToneCaptures:
    source: Float32Array
    scope_measurement: Float32Array
    scope_baseline: Float32Array
    ch2: Float32Array


def floating_measurement_setup() -> dict[str, object]:
    return {
        "kind": "floating_differential_rc_shunt_v1",
        "resistance_ohm": 100.0,
        "c1_f": 10e-9,
        "c2_f": 10e-9,
        "component_values_basis": "nominal",
        "reference_assumption": "floating_host_unverified",
    }


def self_noise_setup() -> dict[str, object]:
    return {
        "kind": "scope_input_terminated_v1",
        "termination_resistance_ohm": 50.0,
    }


def make_tone_captures(spec: ToneCaptureSpec) -> ToneCaptures:
    sample_count = round(spec.sample_rate_hz * spec.duration_s)
    time_s = np.arange(sample_count, dtype=np.float64) / spec.sample_rate_hz
    source = spec.source_amplitude_v * np.sin(2.0 * np.pi * spec.tone_frequency_hz * time_s)
    baseline = np.random.default_rng(6022).normal(0.0, spec.baseline_sigma_v, sample_count)
    scope_measurement = baseline + spec.transfer_gain * source
    ch2 = 3.0 * np.sin(2.0 * np.pi * 50.0 * time_s)
    return ToneCaptures(
        source=source.astype(np.float32),
        scope_measurement=scope_measurement.astype(np.float32),
        scope_baseline=baseline.astype(np.float32),
        ch2=ch2.astype(np.float32),
    )


def write_v2_session(
    session_dir: Path,
    *,
    spec: Ch1SessionSpec,
    ch1: Float32Array,
    ch2: Float32Array,
) -> None:
    session_dir.mkdir()
    np.save(session_dir / "ch1.npy", ch1)
    np.save(session_dir / "ch2.npy", ch2)
    manifest = {
        "schema_version": 2,
        "session_id": spec.session_id,
        "created_utc": "2026-08-04T00:00:00Z",
        "completed_utc": "2026-08-04T00:00:02Z",
        "source": spec.source,
        "session_type": spec.session_type,
        "sample_rate_hz": spec.sample_rate_hz,
        "duration_s": spec.duration_s,
        "sample_count": int(ch1.size),
        "line_frequency_hz": 50.0,
        "profile": None,
        "baseline_session": spec.baseline_session,
        "parameters": {},
        "ch1": {
            "filename": "ch1.npy",
            "role": "hf_probe",
            "unit": spec.unit,
            "front_end": "legacy label must not select the setup",
            "range_code": spec.range_code,
            "probe_multiplier": spec.probe_multiplier,
        },
        "ch2": {
            "filename": "ch2.npy",
            "role": "lf_transformer",
            "unit": "V",
            "front_end": "transformer 230:6",
            "range_code": 1,
            "probe_multiplier": 1.0,
        },
        "acquisition_telemetry": (
            {
                "requested_samples": int(ch1.size),
                "captured_samples": int(ch1.size),
                "callback_count": 1,
                "block_lengths": [int(ch1.size)],
                "callback_gaps_s": [],
                "expected_block_interval_s": spec.duration_s,
                "short_block_count": 0,
                "ch1_clip_low_count": spec.ch1_clip_low_count,
                "ch1_clip_high_count": spec.ch1_clip_high_count,
                "ch2_clip_low_count": 0,
                "ch2_clip_high_count": 0,
                "calibration_used": spec.calibration_used,
            }
            if spec.include_acquisition_telemetry
            else None
        ),
        "synthetic_truth": None,
        "ch1_setup": spec.ch1_setup,
    }
    (session_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
