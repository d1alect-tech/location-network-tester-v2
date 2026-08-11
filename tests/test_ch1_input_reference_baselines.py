from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest

from lnt.analysis import analysis_to_payload, analyze_measurement_session
from tests.ch1_contract_fixtures import (
    Ch1SessionSpec,
    ToneCaptureSpec,
    floating_measurement_setup,
    make_tone_captures,
    self_noise_setup,
    write_v2_session,
)

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE_RATE_HZ = 200_000.0
DURATION_S = 2.1


@dataclass(frozen=True, slots=True, kw_only=True)
class BaselineCase:
    reason_code: str
    measurement_changes: dict[str, object]
    baseline_changes: dict[str, object]
    baseline_sample_count: int | None = None
    persisted_reason_code: str | None = None


BASELINE_CASES = (
    BaselineCase(
        reason_code="missing_explicit_baseline",
        measurement_changes={"baseline_session": None},
        baseline_changes={},
    ),
    BaselineCase(
        reason_code="baseline_session_type_mismatch",
        measurement_changes={},
        baseline_changes={"session_type": "measurement"},
        persisted_reason_code="baseline_unreadable",
    ),
    BaselineCase(
        reason_code="baseline_source_mismatch",
        measurement_changes={},
        baseline_changes={"source": "synthetic"},
    ),
    BaselineCase(
        reason_code="baseline_sample_rate_mismatch",
        measurement_changes={},
        baseline_changes={"sample_rate_hz": SAMPLE_RATE_HZ * 1.01},
    ),
    BaselineCase(
        reason_code="baseline_range_code_mismatch",
        measurement_changes={},
        baseline_changes={"range_code": 5},
    ),
    BaselineCase(
        reason_code="baseline_unit_mismatch",
        measurement_changes={},
        baseline_changes={"unit": "mV"},
    ),
    BaselineCase(
        reason_code="baseline_probe_multiplier_mismatch",
        measurement_changes={},
        baseline_changes={"probe_multiplier": 10.0},
    ),
    BaselineCase(
        reason_code="baseline_adc_calibration_mismatch",
        measurement_changes={},
        baseline_changes={"calibration_used": True},
    ),
    BaselineCase(
        reason_code="baseline_frequency_grid_mismatch",
        measurement_changes={},
        baseline_changes={"duration_s": 1_024 / SAMPLE_RATE_HZ},
        baseline_sample_count=1_024,
    ),
    BaselineCase(
        reason_code="baseline_ch1_setup_mismatch",
        measurement_changes={},
        baseline_changes={"ch1_setup": floating_measurement_setup()},
        persisted_reason_code="baseline_unreadable",
    ),
    BaselineCase(
        reason_code="measurement_ch1_clipping",
        measurement_changes={"ch1_clip_high_count": 1},
        baseline_changes={},
    ),
    BaselineCase(
        reason_code="baseline_ch1_clipping",
        measurement_changes={},
        baseline_changes={"ch1_clip_low_count": 1},
    ),
)


@pytest.mark.parametrize("case", BASELINE_CASES, ids=lambda case: case.reason_code)
def test_input_reference_is_reason_coded_unavailable_when_baseline_is_incompatible(
    tmp_path: Path,
    case: BaselineCase,
) -> None:
    # Given: an explicit measurement/baseline pair with exactly one failed compatibility rule.
    captures = make_tone_captures(
        ToneCaptureSpec(
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            tone_frequency_hz=10_000.0,
            source_amplitude_v=0.2,
            transfer_gain=0.03,
            baseline_sigma_v=0.0002,
        ),
    )
    measurement_spec = replace(
        Ch1SessionSpec(
            session_id="measurement",
            session_type="measurement",
            source="device",
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            ch1_setup=floating_measurement_setup(),
            baseline_session="../baseline",
        ),
        **case.measurement_changes,
    )
    baseline_spec = replace(
        Ch1SessionSpec(
            session_id="baseline",
            session_type="self_noise",
            source="device",
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            ch1_setup=self_noise_setup(),
            baseline_session=None,
        ),
        **case.baseline_changes,
    )
    baseline_ch1 = captures.scope_baseline[: case.baseline_sample_count]
    baseline_ch2 = captures.ch2[: case.baseline_sample_count]
    write_v2_session(tmp_path / "baseline", spec=baseline_spec, ch1=baseline_ch1, ch2=baseline_ch2)
    write_v2_session(
        tmp_path / "measurement",
        spec=measurement_spec,
        ch1=captures.scope_measurement,
        ch2=captures.ch2,
    )

    # When: input referral is requested from the public analysis entry point.
    payload = analysis_to_payload(analyze_measurement_session(tmp_path / "measurement"))

    # Then: the raw analysis remains valid but no noise is zero-filled or amplified.
    assert payload["ch1_input_reference"] == {
        "status": "unavailable",
        "reason_code": case.persisted_reason_code or case.reason_code,
        "model_kind": "floating_differential_rc_shunt_v1",
        "baseline_session_id": None,
        "model": None,
        "qualification_rule_id": None,
        "qualified_bin_count": 0,
        "total_bin_count": 0,
        "corrected_peaks": [],
    }


def test_input_reference_keeps_raw_analysis_when_explicit_baseline_path_is_unreadable(
    tmp_path: Path,
) -> None:
    # Given: a v2 measurement whose explicitly linked baseline directory does not exist.
    captures = make_tone_captures(
        ToneCaptureSpec(
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            tone_frequency_hz=10_000.0,
            source_amplitude_v=0.2,
            transfer_gain=0.03,
            baseline_sigma_v=0.0002,
        ),
    )
    measurement = tmp_path / "measurement"
    write_v2_session(
        measurement,
        spec=Ch1SessionSpec(
            session_id="measurement",
            session_type="measurement",
            source="device",
            sample_rate_hz=SAMPLE_RATE_HZ,
            duration_s=DURATION_S,
            ch1_setup=floating_measurement_setup(),
            baseline_session="../missing-baseline",
        ),
        ch1=captures.scope_measurement,
        ch2=captures.ch2,
    )

    # When: raw analysis reaches the explicit-but-unreadable baseline boundary.
    result = analyze_measurement_session(measurement)
    payload = analysis_to_payload(result)

    # Then: raw spectrum survives and input referral reports a stable machine reason.
    reference = payload["ch1_input_reference"]
    assert result.spectrum.psd_v2_per_hz.size > 0
    assert isinstance(reference, dict)
    assert reference["status"] == "unavailable"
    assert reference["reason_code"] == "baseline_unreadable"
