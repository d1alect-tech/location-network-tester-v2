"""T5: подготовка probe-pair параметров захвата и preflight WARN о калибровке."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.capture_preflight import (
    BaselineCompatibility,
    CaptureEnvironment,
    CapturePreflightRequest,
    FindingSeverity,
    run_capture_preflight,
)
from lnt.cm_dm.capture_support import prepare_probe_pair_capture
from lnt.device_diagnostics import DeviceState
from lnt.types import (
    ChannelMode,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    SessionType,
)

SAMPLE_RATE_HZ = 1000.0
SAMPLE_COUNT = 4000
TONE_HZ = 50.0
GAIN = 0.8
NOISE_SIGMA_V = 1e-3

PROBE_PAIR_KEYS = {
    "probe_pair",
    "probe_pair_correction_factor",
    "probe_pair_gain_ratio",
    "probe_pair_rejection_depth_db",
}


# --- fixture helpers, mimicking tests/test_cm_dm_calibration.py ---


def _tone(amplitude: float = 1.0, phase_rad: float = 0.0) -> np.ndarray:
    time_s = np.arange(SAMPLE_COUNT, dtype=np.float64) / SAMPLE_RATE_HZ
    return amplitude * np.sin(2.0 * np.pi * TONE_HZ * time_s + phase_rad)


def _noise(seed: int, sigma: float = NOISE_SIGMA_V) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, sigma, SAMPLE_COUNT)


def _channel(role: str) -> dict[str, object]:
    return {
        "filename": "ch1.npy" if role == "hf_probe" else "ch2.npy",
        "role": role,
        "unit": "V",
        "front_end": "probe pair capture support fixture",
        "range_code": 1,
        "probe_multiplier": 1.0,
    }


def _session_mapping(session_id: str, session_type: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "session_id": session_id,
        "created_utc": "2026-08-25T00:00:00Z",
        "completed_utc": "2026-08-25T00:00:04Z",
        "source": "device",
        "session_type": session_type,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "duration_s": SAMPLE_COUNT / SAMPLE_RATE_HZ,
        "sample_count": SAMPLE_COUNT,
        "line_frequency_hz": 50.0,
        "profile": None,
        "baseline_session": None,
        "parameters": {
            "snr_db": 40.0,
            "gain_ratio_epsilon": GAIN,
            "correction_factor": 1.0 / GAIN,
            "rejection_depth_db": 60.0,
        },
        "ch1": _channel("hf_probe"),
        "ch2": _channel("lf_transformer"),
        "acquisition_telemetry": {
            "requested_samples": SAMPLE_COUNT,
            "captured_samples": SAMPLE_COUNT,
            "callback_count": 1,
            "block_lengths": [SAMPLE_COUNT],
            "callback_gaps_s": [],
            "expected_block_interval_s": SAMPLE_COUNT / SAMPLE_RATE_HZ,
            "short_block_count": 0,
            "ch1_clip_low_count": 0,
            "ch1_clip_high_count": 0,
            "ch2_clip_low_count": 0,
            "ch2_clip_high_count": 0,
            "calibration_used": False,
        },
        "synthetic_truth": None,
    }


def _write_session(
    session_dir: Path,
    mapping: dict[str, object],
    ch1: np.ndarray,
    ch2: np.ndarray,
) -> None:
    session_dir.mkdir()
    np.save(session_dir / "ch1.npy", ch1.astype(np.float32))
    np.save(session_dir / "ch2.npy", ch2.astype(np.float32))
    serialized = manifest_to_mapping(manifest_from_mapping(mapping))
    (session_dir / "manifest.json").write_text(
        json.dumps(serialized, indent=2) + "\n",
        encoding="utf-8",
    )


# --- capture_support ---


def test_prepared_parameters_full_when_calibration_resolves(tmp_path: Path) -> None:
    # Given: real calibration and measurement session dirs on disk.
    ch1 = _tone() + _noise(21)
    _write_session(
        tmp_path / "calib-pair",
        _session_mapping("calib-pair", "cm_dm_calibration"),
        ch1,
        GAIN * ch1,
    )
    _write_session(tmp_path / "meas", _session_mapping("meas", "measurement"), ch1, ch1)
    measurement = manifest_from_mapping(
        json.loads((tmp_path / "meas" / "manifest.json").read_text(encoding="utf-8")),
    )

    # When: probe-pair capture parameters are prepared against the calibration.
    prepared = prepare_probe_pair_capture(tmp_path, "calib-pair", measurement)

    # Then: exactly the four JSON-scalar keys are published with float factors.
    assert prepared.available is True
    assert prepared.reason_code is None
    assert set(prepared.parameters) == PROBE_PAIR_KEYS
    assert prepared.parameters["probe_pair"] == "cm_dm"
    correction = prepared.parameters["probe_pair_correction_factor"]
    gain_ratio = prepared.parameters["probe_pair_gain_ratio"]
    rejection = prepared.parameters["probe_pair_rejection_depth_db"]
    assert isinstance(correction, float)
    assert isinstance(gain_ratio, float)
    assert isinstance(rejection, float)
    assert math.isclose(gain_ratio, GAIN, rel_tol=1e-2)
    assert math.isclose(correction, 1.0 / GAIN, rel_tol=1e-2)
    assert rejection > 20.0


def test_prepared_parameters_minimal_when_ref_missing(tmp_path: Path) -> None:
    # Given: a measurement manifest and no calibration reference at all.
    measurement = manifest_from_mapping(_session_mapping("meas", "measurement"))

    # When: preparation runs without a reference.
    prepared = prepare_probe_pair_capture(tmp_path, None, measurement)

    # Then: capture proceeds with only the probe_pair tag and the typed reason.
    assert prepared.available is False
    assert prepared.reason_code == "missing_probe_pair_calibration"
    assert set(prepared.parameters) == {"probe_pair"}
    assert prepared.parameters["probe_pair"] == "cm_dm"


def test_prepared_parameters_minimal_when_unreadable(tmp_path: Path) -> None:
    # Given: a reference pointing to a directory that does not exist.
    measurement = manifest_from_mapping(_session_mapping("meas", "measurement"))

    # When: preparation reaches the unreadable session boundary.
    prepared = prepare_probe_pair_capture(tmp_path, "absent-calib", measurement)

    # Then: capture proceeds with only the probe_pair tag and the unreadable reason.
    assert prepared.available is False
    assert prepared.reason_code == "calibration_unreadable"
    assert set(prepared.parameters) == {"probe_pair"}
    assert prepared.parameters["probe_pair"] == "cm_dm"


# --- capture_preflight probe-pair warning ---


def rc_setup() -> FloatingDifferentialRcShunt:
    return FloatingDifferentialRcShunt(
        resistance_ohm=100.0,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis=ComponentValuesBasis.NOMINAL,
        reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    )


def request() -> CapturePreflightRequest:
    """Здоровый measurement-запрос БЕЗ нового поля (дефолт None)."""
    return CapturePreflightRequest(
        session_root=Path("sessions"),
        session_type=SessionType.MEASUREMENT,
        channel_mode=ChannelMode.DUAL,
        ch1_setup=rc_setup(),
        sample_rate_hz=8_000_000.0,
        duration_s=2.4,
        range_v=5.0,
        probe_multiplier=1.0,
        baseline_requested=False,
    )


def environment() -> CaptureEnvironment:
    return CaptureEnvironment(
        device_state=DeviceState.READY,
        free_bytes=1_000_000_000,
        root_writable=True,
        baseline_compatibility=BaselineCompatibility.NOT_REQUESTED,
    )


@pytest.mark.parametrize(
    ("available", "expected_warning"),
    [(False, True), (None, False), (True, False)],
)
def test_preflight_warns_only_when_explicitly_unavailable(
    available: bool | None,
    expected_warning: bool,
) -> None:
    # Given: healthy requests differing only in explicit probe-pair availability.
    capture_request = replace(request(), probe_pair_calibration_available=available)

    # When: preflight runs over a ready environment.
    findings = run_capture_preflight(capture_request, environment())

    # Then: the single WARN appears iff availability is explicitly False.
    warnings = [item for item in findings if item.code == "probe_pair_calibration_missing"]
    assert bool(warnings) is expected_warning
    if expected_warning:
        assert len(findings) == 1
        assert warnings[0].severity is FindingSeverity.WARN
        assert "--probe-pair-calibrate" in warnings[0].recovery_action_ru


def test_existing_preflight_requests_untouched() -> None:
    # Given: requests built without the new field — healthy and weak-signal.
    healthy = request()
    weak_signal = replace(request(), probe_multiplier=10.0)

    # When: preflight runs over a ready environment.
    healthy_findings = run_capture_preflight(healthy, environment())
    weak_findings = run_capture_preflight(weak_signal, environment())

    # Then: findings tuples match the pre-change baselines with zero drift.
    assert healthy_findings == ()
    assert tuple((item.code, item.severity) for item in weak_findings) == (
        ("weak_signal_resolution", FindingSeverity.WARN),
    )
