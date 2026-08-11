from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt import acquire
from lnt.scope_io import CancelledResult
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMode,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    SessionType,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def captured_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    sample_count = 1_000
    raw = np.full(sample_count, 128, dtype=np.uint8)
    telemetry = AcquisitionTelemetry(
        requested_samples=sample_count,
        captured_samples=sample_count,
        callback_count=1,
        block_lengths=(sample_count,),
        callback_gaps_s=(),
        expected_block_interval_s=0.001,
        short_block_count=0,
        ch1_clip_low_count=0,
        ch1_clip_high_count=0,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=False,
    )

    def fake_run_capture(*_args: object, **_kwargs: object) -> tuple[object, object, object]:
        return raw, raw, telemetry

    monkeypatch.setattr(acquire, "open_real_scope", object)
    monkeypatch.setattr(acquire, "run_capture", fake_run_capture)


@pytest.mark.usefixtures("captured_raw")
def test_measurement_capture_writes_explicit_floating_rc_setup(tmp_path: Path) -> None:
    # Given: a real-device measurement request with declared RC component provenance.
    setup = FloatingDifferentialRcShunt(
        resistance_ohm=100.0,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis=ComponentValuesBasis.OPERATOR_MEASURED,
        reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    )

    # When: capture persists its session manifest.
    session = acquire.capture_session(
        out_dir=tmp_path / "measurement",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        baseline_session="../baseline",
        ch1_setup=setup,
    )
    assert not isinstance(session, CancelledResult)

    # Then: schema v2 carries only the explicit machine-readable transfer setup.
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["baseline_session"] == "../baseline"
    assert manifest["ch1_setup"] == {
        "kind": "floating_differential_rc_shunt_v1",
        "resistance_ohm": 100.0,
        "c1_f": 10e-9,
        "c2_f": 10e-9,
        "component_values_basis": "operator_measured",
        "reference_assumption": "floating_host_unverified",
    }


@pytest.mark.usefixtures("captured_raw")
def test_self_noise_capture_writes_explicit_terminated_setup(tmp_path: Path) -> None:
    # Given: a self-noise capture request.
    # When: capture chooses the self-noise setup before persisting its manifest.
    session = acquire.capture_session(
        out_dir=tmp_path / "baseline",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        session_type=SessionType.SELF_NOISE,
    )
    assert not isinstance(session, CancelledResult)

    # Then: the model is explicit and carries the scope termination resistance.
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ch1_setup"] == {
        "kind": "scope_input_terminated_v1",
        "termination_resistance_ohm": 50.0,
    }


@pytest.mark.usefixtures("captured_raw")
def test_single_channel_capture_omits_ch2(tmp_path: Path) -> None:
    # Given/When: a single-channel (CH1-only) device capture.
    session = acquire.capture_session(
        out_dir=tmp_path / "single",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        channel_mode=ChannelMode.CH1_ONLY,
    )
    assert not isinstance(session, CancelledResult)

    # Then: no ch2.npy on disk and manifest marks the session as CH1-only.
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ch2"] is None
    assert not (session / "ch2.npy").exists()
    assert (session / "ch1.npy").exists()


@pytest.mark.usefixtures("captured_raw")
def test_dual_channel_capture_keeps_ch2(tmp_path: Path) -> None:
    session = acquire.capture_session(
        out_dir=tmp_path / "dual",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        channel_mode=ChannelMode.DUAL,
    )
    assert not isinstance(session, CancelledResult)

    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ch2"] is not None
    assert (session / "ch2.npy").exists()
