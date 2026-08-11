from dataclasses import replace
from pathlib import Path

import pytest

from lnt.capture_preflight import (
    BaselineCompatibility,
    CaptureEnvironment,
    CapturePreflightRequest,
    FindingSeverity,
    run_capture_preflight,
)
from lnt.device_diagnostics import DeviceState
from lnt.types import (
    ChannelMode,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)


def rc_setup() -> FloatingDifferentialRcShunt:
    return FloatingDifferentialRcShunt(
        resistance_ohm=100.0,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis=ComponentValuesBasis.NOMINAL,
        reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    )


def request() -> CapturePreflightRequest:
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


def environment(
    *,
    device_state: DeviceState = DeviceState.READY,
    free_bytes: int = 1_000_000_000,
    root_writable: bool = True,
    baseline_compatibility: BaselineCompatibility = BaselineCompatibility.NOT_REQUESTED,
) -> CaptureEnvironment:
    return CaptureEnvironment(
        device_state=device_state,
        free_bytes=free_bytes,
        root_writable=root_writable,
        baseline_compatibility=baseline_compatibility,
    )


@pytest.mark.parametrize(
    ("capture_request", "expected_code"),
    [
        (replace(request(), session_type=SessionType.LINE_QUALITY), "mode_setup_mismatch"),
        (
            replace(
                request(),
                session_type=SessionType.LINE_QUALITY,
                channel_mode=ChannelMode.DUAL,
            ),
            "line_quality_requires_single_channel",
        ),
        (replace(request(), sample_rate_hz=1e20), "sample_count_overflow"),
        (replace(request(), duration_s=1e20), "sample_count_overflow"),
    ],
)
def test_invalid_request_is_blocked_with_distinct_code(
    capture_request: CapturePreflightRequest,
    expected_code: str,
) -> None:
    findings = run_capture_preflight(capture_request, environment())

    finding = next(item for item in findings if item.code == expected_code)
    assert finding.severity is FindingSeverity.BLOCK
    assert finding.recovery_action_ru


@pytest.mark.parametrize(
    ("capture_environment", "expected_code"),
    [
        (environment(device_state=DeviceState.HANDLE_BUSY), "device_handle_busy"),
        (environment(free_bytes=1), "insufficient_disk_space"),
        (environment(root_writable=False), "session_root_not_writable"),
        (
            environment(baseline_compatibility=BaselineCompatibility.INCOMPATIBLE),
            "baseline_incompatible",
        ),
    ],
)
def test_environment_failure_is_blocked_with_recovery(
    capture_environment: CaptureEnvironment,
    expected_code: str,
) -> None:
    findings = run_capture_preflight(
        replace(request(), baseline_requested=True),
        capture_environment,
    )

    finding = next(item for item in findings if item.code == expected_code)
    assert finding.severity is FindingSeverity.BLOCK
    assert finding.recovery_action_ru


def test_line_quality_unsafe_range_warns_without_changing_request() -> None:
    capture_request = CapturePreflightRequest(
        session_root=Path("sessions"),
        session_type=SessionType.LINE_QUALITY,
        channel_mode=ChannelMode.CH1_ONLY,
        ch1_setup=TransformerLineProbe(
            nominal_primary_v=230.0,
            nominal_secondary_v=6.0,
            probe_multiplier=10.0,
        ),
        sample_rate_hz=8_000_000.0,
        duration_s=2.4,
        range_v=1.0,
        probe_multiplier=10.0,
        baseline_requested=False,
    )

    findings = run_capture_preflight(capture_request, environment())

    finding = next(item for item in findings if item.code == "line_quality_clipping_likely")
    assert finding.severity is FindingSeverity.WARN
    assert "5" in finding.recovery_action_ru
    assert capture_request.range_v == 1.0


def test_weak_signal_choice_warns_with_distinct_code() -> None:
    findings = run_capture_preflight(
        replace(request(), range_v=5.0, probe_multiplier=10.0),
        environment(),
    )

    finding = next(item for item in findings if item.code == "weak_signal_resolution")
    assert finding.severity is FindingSeverity.WARN
    assert "0,5" in finding.recovery_action_ru


def test_healthy_self_noise_request_has_no_findings() -> None:
    capture_request = CapturePreflightRequest(
        session_root=Path("sessions"),
        session_type=SessionType.SELF_NOISE,
        channel_mode=ChannelMode.DUAL,
        ch1_setup=ScopeInputTerminated(termination_resistance_ohm=50.0),
        sample_rate_hz=8_000_000.0,
        duration_s=2.4,
        range_v=0.5,
        probe_multiplier=1.0,
        baseline_requested=False,
    )

    assert run_capture_preflight(capture_request, environment()) == ()
