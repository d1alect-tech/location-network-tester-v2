from __future__ import annotations

import dataclasses
from dataclasses import replace

import numpy as np
import pytest

import lnt.characterization.clipping as clipping_module
from lnt.adc_calibration import apply_adc_calibration
from lnt.characterization.clipping import resolve_clipping
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
    SyntheticTruth,
)


def _channel(*, filename: str, front_end: str = "scope", range_code: int = 2) -> ChannelMeta:
    return ChannelMeta(
        filename=filename,
        role=ChannelRole.HF_PROBE,
        unit="V",
        front_end=front_end,
        range_code=range_code,
        probe_multiplier=10.0,
    )


def _telemetry(
    *, calibration_used: bool = False, ch1_counts: tuple[int, int] = (0, 0)
) -> AcquisitionTelemetry:
    return AcquisitionTelemetry(
        requested_samples=4,
        captured_samples=4,
        callback_count=1,
        block_lengths=(4,),
        callback_gaps_s=(),
        expected_block_interval_s=4e-6,
        short_block_count=0,
        ch1_clip_low_count=ch1_counts[0],
        ch1_clip_high_count=ch1_counts[1],
        ch2_clip_low_count=7,
        ch2_clip_high_count=11,
        calibration_used=calibration_used,
    )


def _truth() -> SyntheticTruth:
    return SyntheticTruth(
        needle_mean_v=0.25,
        needle_sigma_ratio=0.1,
        needle_jitter_us=3.5,
        ring_f0_hz=120_000.0,
        ring_q=4.0,
        async_rate_hz=733.0,
        lf_envelope_cv=0.05,
    )


def _manifest(
    *,
    source: SessionSource = SessionSource.DEVICE,
    telemetry: AcquisitionTelemetry | None = None,
    ch1: ChannelMeta | None = None,
    ch2: ChannelMeta | None = None,
    truth: SyntheticTruth | None = None,
) -> SessionManifest:
    return SessionManifest(
        schema_version=1,
        session_id="clipping-test",
        created_utc="2026-09-11T00:00:00Z",
        completed_utc="2026-09-11T00:00:01Z",
        source=source,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=1_000_000.0,
        duration_s=4e-6,
        sample_count=4,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        ch1=ch1 or _channel(filename="ch1.npy"),
        ch2=ch2,
        acquisition_telemetry=telemetry,
        synthetic_truth=truth,
    )


def test_device_nominal_rails_use_public_conversion_without_mutating_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_endpoints: list[np.ndarray] = []

    def tracked_conversion(
        raw: np.ndarray,
        *,
        range_code: int,
        probe_multiplier: float = 1.0,
        calibration: None = None,
    ) -> np.ndarray:
        source_endpoints.append(raw)
        return apply_adc_calibration(
            raw,
            range_code=range_code,
            probe_multiplier=probe_multiplier,
            calibration=calibration,
        )

    monkeypatch.setattr(clipping_module, "apply_adc_calibration", tracked_conversion)
    manifest = _manifest(telemetry=_telemetry(ch1_counts=(2, 3)))

    bounds = resolve_clipping(manifest, "ch1", 0.98)
    expected = apply_adc_calibration(
        np.array([0, 255], dtype=np.uint8),
        range_code=manifest.ch1.range_code,
        probe_multiplier=manifest.ch1.probe_multiplier,
    )

    assert bounds.low_v == pytest.approx(float(expected[0]) * 0.98)
    assert bounds.high_v == pytest.approx(float(expected[1]) * 0.98)
    assert bounds.reason_code is None
    assert bounds.telemetry_rail_count == 5
    assert bounds.classify(np.array([0.0], dtype=np.float32)) is False
    assert len(source_endpoints) == 1
    assert np.array_equal(source_endpoints[0], np.array([0, 255], dtype=np.uint8))
    with pytest.raises(dataclasses.FrozenInstanceError):
        bounds.__setattr__("low_v", 0.0)


def test_classification_includes_each_nominal_boundary() -> None:
    bounds = resolve_clipping(_manifest(telemetry=_telemetry()), "ch1", 0.98)
    assert bounds.low_v is not None
    assert bounds.high_v is not None

    assert bounds.classify(np.array([bounds.low_v, 0.0], dtype=np.float64)) is True
    assert bounds.classify(np.array([0.0, bounds.high_v], dtype=np.float64)) is True
    assert bounds.classify(np.array([bounds.low_v + 0.01, bounds.high_v - 0.01])) is False


def test_calibrated_capture_keeps_saved_volts_but_cannot_localize_telemetry_hits() -> None:
    samples_v = np.array([-0.75, 0.5, 3.25], dtype=np.float32)
    original = samples_v.copy()
    bounds = resolve_clipping(
        _manifest(telemetry=_telemetry(calibration_used=True, ch1_counts=(4, 2))),
        "ch1",
        0.98,
    )

    assert bounds.low_v is None
    assert bounds.high_v is None
    assert bounds.reason_code == "clipping_localization_unavailable"
    assert bounds.telemetry_rail_count == 6
    assert bounds.classify(samples_v) is None
    assert np.array_equal(samples_v, original)


def test_device_without_telemetry_has_unknown_localization() -> None:
    bounds = resolve_clipping(_manifest(), "ch1", 0.98)

    assert bounds.reason_code == "clipping_localization_unavailable"
    assert bounds.telemetry_rail_count is None
    assert bounds.classify(np.array([0.0], dtype=np.float32)) is None


def test_absent_ch2_is_reported_before_clipping_qualification() -> None:
    bounds = resolve_clipping(_manifest(telemetry=_telemetry()), "ch2", 0.98)

    assert bounds.reason_code == "channel_missing"
    assert bounds.telemetry_rail_count is None
    assert bounds.classify(np.array([0.0], dtype=np.float32)) is None


def test_ideal_synthetic_signal_declares_hardware_clipping_not_applicable() -> None:
    manifest = _manifest(
        source=SessionSource.SYNTHETIC,
        ch1=_channel(filename="ch1.npy", front_end="synthetic"),
        truth=_truth(),
    )

    bounds = resolve_clipping(manifest, "ch1", 0.98)

    assert bounds.reason_code == "not_applicable_synthetic"
    assert bounds.low_v is None
    assert bounds.high_v is None
    assert bounds.classify(np.array([-1e9, 1e9], dtype=np.float64)) is False


@pytest.mark.parametrize(
    "manifest",
    [
        _manifest(
            source=SessionSource.SYNTHETIC,
            ch1=_channel(filename="ch1.npy", front_end="synthetic"),
        ),
        _manifest(
            source=SessionSource.SYNTHETIC,
            ch1=_channel(filename="ch1.npy", front_end="scope"),
            truth=_truth(),
        ),
    ],
)
def test_incomplete_synthetic_provenance_is_not_hardware_clipping_proof(
    manifest: SessionManifest,
) -> None:
    bounds = resolve_clipping(manifest, "ch1", 0.98)

    assert bounds.reason_code == "clipping_localization_unavailable"
    assert bounds.classify(np.array([0.0], dtype=np.float32)) is None


def test_ch2_uses_its_own_metadata_and_telemetry_count() -> None:
    ch2 = replace(_channel(filename="ch2.npy"), range_code=4, probe_multiplier=1.0)
    manifest = _manifest(telemetry=_telemetry(ch1_counts=(2, 3)), ch2=ch2)

    bounds = resolve_clipping(manifest, "ch2", 0.98)

    assert bounds.telemetry_rail_count == 18
    assert bounds.reason_code is None
