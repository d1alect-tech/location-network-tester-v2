from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest

from lnt.analysis import analyze_measurement_session, write_analysis
from lnt.input_reference import derive_input_reference
from lnt.session_store import LoadedSession, load_session
from lnt.spectrum import compute_band_spectrum
from lnt.types import SessionType
from tests.ch1_contract_fixtures import (
    Ch1SessionSpec,
    ToneCaptures,
    ToneCaptureSpec,
    floating_measurement_setup,
    make_tone_captures,
    self_noise_setup,
    write_v2_session,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class MissingTelemetryCase:
    reason_code: str
    measurement_has_telemetry: bool
    baseline_has_telemetry: bool


MISSING_TELEMETRY_CASES = (
    MissingTelemetryCase(
        reason_code="measurement_telemetry_missing",
        measurement_has_telemetry=False,
        baseline_has_telemetry=True,
    ),
    MissingTelemetryCase(
        reason_code="baseline_telemetry_missing",
        measurement_has_telemetry=True,
        baseline_has_telemetry=False,
    ),
)


def _captures() -> ToneCaptures:
    return make_tone_captures(
        ToneCaptureSpec(
            sample_rate_hz=200_000.0,
            duration_s=2.1,
            tone_frequency_hz=10_000.0,
            source_amplitude_v=0.2,
            transfer_gain=0.03,
            baseline_sigma_v=0.0002,
        ),
    )


@pytest.mark.parametrize("case", MISSING_TELEMETRY_CASES, ids=lambda case: case.reason_code)
def test_device_session_without_telemetry_keeps_raw_artifacts_and_reason_codes(
    tmp_path: Path,
    case: MissingTelemetryCase,
) -> None:
    # Given: a valid persisted device v2 measurement/baseline pair with one telemetry object absent.
    captures = _captures()
    baseline = tmp_path / "baseline"
    measurement = tmp_path / "measurement"
    write_v2_session(
        baseline,
        spec=Ch1SessionSpec(
            session_id="baseline",
            session_type="self_noise",
            source="device",
            sample_rate_hz=200_000.0,
            duration_s=2.1,
            ch1_setup=self_noise_setup(),
            baseline_session=None,
            include_acquisition_telemetry=case.baseline_has_telemetry,
        ),
        ch1=captures.scope_baseline,
        ch2=captures.ch2,
    )
    write_v2_session(
        measurement,
        spec=Ch1SessionSpec(
            session_id="measurement",
            session_type="measurement",
            source="device",
            sample_rate_hz=200_000.0,
            duration_s=2.1,
            ch1_setup=floating_measurement_setup(),
            baseline_session="../baseline",
            include_acquisition_telemetry=case.measurement_has_telemetry,
        ),
        ch1=captures.scope_measurement,
        ch2=captures.ch2,
    )

    # When: analysis and artifacts are produced from the valid raw capture.
    result = analyze_measurement_session(measurement)
    _, raw_spectrum = write_analysis(measurement, result)

    # Then: raw artifacts remain scope-plane while corrected output is header-only and reason-coded.
    assert result.needle.cycles_analyzed > 0
    assert result.spectrum.psd_v2_per_hz.size > 0
    assert result.ch1_input_reference.reason_code == case.reason_code
    assert raw_spectrum.read_text(encoding="utf-8").splitlines()[0] == "frequency_hz,psd_v2_per_hz"
    assert (measurement / "spectrum_input_referred.csv").read_text(encoding="utf-8") == (
        "frequency_hz,input_referred_excess_psd_v2_per_hz\n"
    )


def test_direct_nonmeasurement_session_object_is_not_input_referred(tmp_path: Path) -> None:
    # Given: a valid persisted measurement rebuilt in memory with a contradictory session type.
    captures = _captures()
    measurement = tmp_path / "measurement"
    write_v2_session(
        measurement,
        spec=Ch1SessionSpec(
            session_id="measurement",
            session_type="measurement",
            source="device",
            sample_rate_hz=200_000.0,
            duration_s=2.1,
            ch1_setup=floating_measurement_setup(),
            baseline_session=None,
        ),
        ch1=captures.scope_measurement,
        ch2=captures.ch2,
    )
    loaded = load_session(measurement)
    contradictory = LoadedSession(
        session_dir=measurement,
        manifest=replace(loaded.manifest, session_type=SessionType.SELF_NOISE),
        ch1=loaded.ch1,
        ch2=loaded.ch2,
    )
    spectrum = compute_band_spectrum(
        contradictory.ch1,
        sample_rate_hz=contradictory.manifest.sample_rate_hz,
    )

    # When: input referral receives the directly constructed non-measurement object.
    reference = derive_input_reference(measurement, contradictory, spectrum)

    # Then: defense in depth refuses correction before any baseline inference.
    assert reference.reason_code == "measurement_session_type_mismatch"
