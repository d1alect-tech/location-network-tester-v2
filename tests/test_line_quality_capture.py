"""Контракт line-quality захвата: манифест, масштабирование пробника, ограничения."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt import acquire
from lnt.errors import InputError
from lnt.scope_io import CancelledResult
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMode,
    SessionType,
    TransformerLineProbe,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def captured_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    sample_count = 1_000
    raw = np.full(sample_count, 192, dtype=np.uint8)
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
def test_line_quality_capture_writes_transformer_manifest(tmp_path: Path) -> None:
    # Given/When: a line-quality device capture (single probe on the transformer).
    session = acquire.capture_session(
        out_dir=tmp_path / "line",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        session_type=SessionType.LINE_QUALITY,
        channel_mode=ChannelMode.CH1_ONLY,
    )
    assert not isinstance(session, CancelledResult)

    # Then: the manifest declares the transformer front-end on CH1 and no CH2.
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["session_type"] == "line_quality"
    assert manifest["ch2"] is None
    assert manifest["ch1_setup"] == {
        "kind": "transformer_line_probe_v1",
        "nominal_primary_v": 230.0,
        "nominal_secondary_v": 6.0,
        "probe_multiplier": 10.0,
    }
    assert manifest["ch1"]["role"] == "lf_transformer"
    assert manifest["ch1"]["front_end"] == "transformer 230:6"
    assert manifest["ch1"]["probe_multiplier"] == 10.0
    assert not (session / "ch2.npy").exists()


@pytest.mark.usefixtures("captured_raw")
def test_line_quality_capture_applies_probe_multiplier_to_volts(tmp_path: Path) -> None:
    # Given: raw ADC counts at +64 from center, range code 1, probe 10x.
    session = acquire.capture_session(
        out_dir=tmp_path / "line",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        session_type=SessionType.LINE_QUALITY,
        channel_mode=ChannelMode.CH1_ONLY,
    )
    assert not isinstance(session, CancelledResult)

    # When: the persisted CH1 waveform is loaded.
    ch1 = np.load(session / "ch1.npy")

    # Then: volts are secondary-side real volts (64/128 * 5.12 * 10 = 25.6 V).
    assert ch1[0] == pytest.approx(25.6, rel=1e-6)


@pytest.mark.usefixtures("captured_raw")
def test_line_quality_capture_rejects_dual_channel_mode(tmp_path: Path) -> None:
    # When/Then: the transformer occupies the only probe -- dual mode is invalid.
    with pytest.raises(InputError):
        acquire.capture_session(
            out_dir=tmp_path / "line",
            duration_s=0.001,
            sample_rate_hz=1_000_000.0,
            session_type=SessionType.LINE_QUALITY,
            channel_mode=ChannelMode.DUAL,
        )


@pytest.mark.usefixtures("captured_raw")
def test_line_quality_capture_rejects_baseline_reference(tmp_path: Path) -> None:
    # When/Then: baseline subtraction has no meaning for mains-quality capture.
    with pytest.raises(InputError):
        acquire.capture_session(
            out_dir=tmp_path / "line",
            duration_s=0.001,
            sample_rate_hz=1_000_000.0,
            session_type=SessionType.LINE_QUALITY,
            channel_mode=ChannelMode.CH1_ONLY,
            baseline_session="noise",
        )


@pytest.mark.usefixtures("captured_raw")
def test_line_quality_capture_accepts_explicit_transformer_setup(tmp_path: Path) -> None:
    # Given: an operator-declared transformer model with a 1x probe.
    setup = TransformerLineProbe(
        nominal_primary_v=230.0,
        nominal_secondary_v=9.0,
        probe_multiplier=1.0,
    )

    # When: capture persists the session.
    session = acquire.capture_session(
        out_dir=tmp_path / "line",
        duration_s=0.001,
        sample_rate_hz=1_000_000.0,
        session_type=SessionType.LINE_QUALITY,
        channel_mode=ChannelMode.CH1_ONLY,
        ch1_setup=setup,
    )
    assert not isinstance(session, CancelledResult)

    # Then: the manifest carries the explicit multiplier and scaling follows it.
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["ch1_setup"]["probe_multiplier"] == 1.0
    ch1 = np.load(session / "ch1.npy")
    assert ch1[0] == pytest.approx(2.56, rel=1e-6)
