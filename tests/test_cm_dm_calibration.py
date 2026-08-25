"""T4: калибровка пары пробников CM/DM — оценка, совместимость, разрешение ссылки."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.cm_dm.calibration import (
    ResolvedProbePairCalibration,
    UnavailableProbePairCalibration,
    estimate_gain_ratio,
    resolve_probe_pair_calibration,
    validate_calibration_compatibility,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

SAMPLE_RATE_HZ = 1000.0
SAMPLE_COUNT = 4000
TONE_HZ = 50.0
GAIN = 0.8
NOISE_SIGMA_V = 1e-3

PUBLISHED_PARAMETERS: dict[str, float] = {
    "snr_db": 40.0,
    "gain_ratio_epsilon": GAIN,
    "correction_factor": 1.0 / GAIN,
    "rejection_depth_db": 60.0,
}


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
        "front_end": "probe pair calibration fixture",
        "range_code": 1,
        "probe_multiplier": 1.0,
    }


@dataclass(frozen=True, slots=True)
class ValidatorCase:
    reason_code: str | None
    session_type: str = "cm_dm_calibration"
    source: str = "device"
    sample_rate_hz: float = SAMPLE_RATE_HZ
    range_code: int = 1
    ch2_clip_high_count: int = 0
    parameters: Mapping[str, float] | None = None

    def mapping(self, session_id: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "session_id": session_id,
            "created_utc": "2026-08-25T00:00:00Z",
            "completed_utc": "2026-08-25T00:00:04Z",
            "source": self.source,
            "session_type": self.session_type,
            "sample_rate_hz": self.sample_rate_hz,
            "duration_s": SAMPLE_COUNT / SAMPLE_RATE_HZ,
            "sample_count": SAMPLE_COUNT,
            "line_frequency_hz": 50.0,
            "profile": None,
            "baseline_session": None,
            "parameters": dict(
                PUBLISHED_PARAMETERS if self.parameters is None else self.parameters
            ),
            "ch1": {**_channel("hf_probe"), "range_code": self.range_code},
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
                "ch2_clip_high_count": self.ch2_clip_high_count,
                "calibration_used": False,
            },
            "synthetic_truth": None,
        }


def _manifest_mapping(session_id: str, session_type: str) -> dict[str, object]:
    return ValidatorCase(reason_code=None, session_type=session_type).mapping(session_id)


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


def test_gain_ratio_recovered_from_scaled_copy() -> None:
    # Given: two pickups on the same conductor, CH2 wired with gain g = 0.8.
    ch1 = _tone() + _noise(11)
    ch2 = GAIN * ch1

    # When: the narrowband gain ratio is estimated over the 45-55 Hz band.
    result = estimate_gain_ratio(ch1, ch2, SAMPLE_RATE_HZ)

    # Then: epsilon recovers g and the CH2 correction factor is its inverse.
    assert math.isclose(result.gain_ratio_epsilon, GAIN, rel_tol=1e-2)
    assert math.isclose(result.correction_factor, 1.0 / GAIN, rel_tol=1e-2)


def test_identical_signals_gain_ratio_is_one() -> None:
    # Given: two identical pickups on the same conductor.
    ch1 = _tone() + _noise(12)

    # When: the gain ratio is estimated.
    result = estimate_gain_ratio(ch1, ch1.copy(), SAMPLE_RATE_HZ)

    # Then: no correction is needed and the band SNR is far above the gate.
    assert math.isclose(result.gain_ratio_epsilon, 1.0, rel_tol=1e-2)
    assert math.isclose(result.correction_factor, 1.0, rel_tol=1e-2)
    assert result.snr_db > 20.0


def test_rejection_depth_large_for_matched_and_small_for_mismatched() -> None:
    # Given: a matched pair (after correction) and a pair with quadrature phase skew.
    ch1 = _tone() + _noise(13)
    matched_ch2 = GAIN * (_tone() + _noise(14))
    mismatched_ch2 = GAIN * _tone(phase_rad=math.pi / 2)

    # When: each pair is calibrated.
    matched = estimate_gain_ratio(ch1, matched_ch2, SAMPLE_RATE_HZ)
    mismatched = estimate_gain_ratio(ch1, mismatched_ch2, SAMPLE_RATE_HZ)

    # Then: only the corrected matched pair rejects the conductor tone deeply.
    assert matched.rejection_depth_db > 20.0
    assert mismatched.rejection_depth_db < 10.0


def test_snr_estimate_flags_noisy_record() -> None:
    # Given: a line tone buried in strong broadband noise on both channels.
    noisy = 0.01 * _tone() + _noise(15, sigma=1.0)

    # When: the narrowband SNR is estimated for the buried record.
    result = estimate_gain_ratio(noisy, noisy.copy(), SAMPLE_RATE_HZ)

    # Then: the estimate falls below the compatibility gate of 20 dB.
    assert result.snr_db < 20.0


VALIDATOR_CASES = (
    ValidatorCase(reason_code=None),
    ValidatorCase(reason_code="calibration_session_type_mismatch", session_type="measurement"),
    ValidatorCase(reason_code="calibration_source_mismatch", source="synthetic"),
    ValidatorCase(
        reason_code="calibration_sample_rate_mismatch",
        sample_rate_hz=SAMPLE_RATE_HZ * 1.01,
    ),
    ValidatorCase(reason_code="calibration_range_code_mismatch", range_code=5),
    ValidatorCase(reason_code="calibration_clipping", ch2_clip_high_count=1),
    ValidatorCase(
        reason_code="calibration_snr_low",
        parameters={"snr_db": 10.0, "gain_ratio_epsilon": GAIN},
    ),
    ValidatorCase(
        reason_code="calibration_gain_ratio_implausible",
        parameters={"snr_db": 40.0, "gain_ratio_epsilon": 3.0},
    ),
)


@pytest.mark.parametrize("case", VALIDATOR_CASES, ids=lambda case: case.reason_code or "compatible")
def test_validate_reason_codes_each_case(case: ValidatorCase) -> None:
    # Given: a measurement manifest and a calibration manifest failing at most one rule.
    measurement = manifest_from_mapping(_manifest_mapping("meas", "measurement"))
    calibration = manifest_from_mapping(case.mapping("calib"))

    # When: cross-session compatibility is evaluated over manifests only.
    codes = validate_calibration_compatibility(calibration, measurement)

    # Then: exactly the expected machine reason is reported (none for the control).
    assert codes == ([] if case.reason_code is None else [case.reason_code])


def test_resolve_missing_ref_returns_reason(tmp_path: Path) -> None:
    # Given: a measurement manifest and no calibration reference at all.
    measurement = manifest_from_mapping(_manifest_mapping("meas", "measurement"))

    # When: resolution is requested without a reference.
    result = resolve_probe_pair_calibration(tmp_path, None, measurement)

    # Then: the typed unavailable carries the missing-reference reason.
    assert isinstance(result, UnavailableProbePairCalibration)
    assert result.reason_code == "missing_probe_pair_calibration"


def test_resolve_unreadable_path_returns_reason(tmp_path: Path) -> None:
    # Given: a reference pointing to a directory that does not exist.
    measurement = manifest_from_mapping(_manifest_mapping("meas", "measurement"))

    # When: resolution reaches the unreadable session boundary.
    result = resolve_probe_pair_calibration(tmp_path, "absent-calib", measurement)

    # Then: the typed unavailable carries the unreadable reason.
    assert isinstance(result, UnavailableProbePairCalibration)
    assert result.reason_code == "calibration_unreadable"


def test_resolve_happy_path(tmp_path: Path) -> None:
    # Given: real calibration and measurement session dirs on disk.
    ch1 = _tone() + _noise(16)
    _write_session(
        tmp_path / "calib-pair",
        _manifest_mapping("calib-pair", "cm_dm_calibration"),
        ch1,
        GAIN * ch1,
    )
    _write_session(
        tmp_path / "meas",
        _manifest_mapping("meas", "measurement"),
        ch1,
        ch1,
    )
    measurement = manifest_from_mapping(
        json.loads((tmp_path / "meas" / "manifest.json").read_text(encoding="utf-8")),
    )

    # When: the probe-pair calibration is resolved against the measurement.
    result = resolve_probe_pair_calibration(tmp_path, "calib-pair", measurement)

    # Then: the factors recomputed from the recorded pair match the fixture gain.
    assert isinstance(result, ResolvedProbePairCalibration)
    assert result.session_id == "calib-pair"
    assert math.isclose(result.gain_ratio_epsilon, GAIN, rel_tol=1e-2)
    assert math.isclose(result.correction_factor, 1.0 / GAIN, rel_tol=1e-2)
    assert result.rejection_depth_db > 20.0
