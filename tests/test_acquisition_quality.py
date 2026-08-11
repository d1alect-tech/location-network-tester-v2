import numpy as np
import pytest

from lnt.acquisition_quality import (
    QUALITY_THRESHOLDS_V1,
    AcquisitionQualityInput,
    ChannelQualityInput,
    QualityCode,
    assess_acquisition_quality,
)
from lnt.types import AcquisitionTelemetry, ChannelMode, SessionType


def telemetry(
    *,
    ch1_clip_high_count: int = 0,
    callback_gaps_s: tuple[float, ...] = (0.01,),
    short_block_count: int = 0,
    captured_samples: int = 1_000,
) -> AcquisitionTelemetry:
    return AcquisitionTelemetry(
        requested_samples=1_000,
        captured_samples=captured_samples,
        callback_count=2,
        block_lengths=(500, 500),
        callback_gaps_s=callback_gaps_s,
        expected_block_interval_s=0.01,
        short_block_count=short_block_count,
        ch1_clip_low_count=0,
        ch1_clip_high_count=ch1_clip_high_count,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=False,
    )


def channel(samples: np.ndarray, range_v: float = 5.0, probe: float = 1.0) -> ChannelQualityInput:
    return ChannelQualityInput(
        samples_v=np.asarray(samples, dtype=np.float32),
        range_v=range_v,
        probe_multiplier=probe,
    )


def test_clipped_capture_reports_rail_hits_and_looser_guidance() -> None:
    result = assess_acquisition_quality(
        AcquisitionQualityInput(
            telemetry=telemetry(ch1_clip_high_count=3),
            session_type=SessionType.MEASUREMENT,
            channel_mode=ChannelMode.CH1_ONLY,
            ch1=channel(np.array([0.0, 5.1])),
        )
    )

    assert QualityCode.CLIPPING in {finding.code for finding in result.findings}
    assert result.channels[0].clip_count == 3
    assert result.channels[0].suggested_range_v is None


def test_under_range_reports_lsb_usage_and_tighter_guidance() -> None:
    result = assess_acquisition_quality(
        AcquisitionQualityInput(
            telemetry=telemetry(),
            session_type=SessionType.MEASUREMENT,
            channel_mode=ChannelMode.CH1_ONLY,
            ch1=channel(np.array([-0.02, 0.02]), range_v=5.0),
        )
    )

    quality = result.channels[0]
    assert QualityCode.UNDER_RANGE in {finding.code for finding in result.findings}
    assert quality.effective_lsb_count == pytest.approx(0.5, rel=0.1)
    assert quality.suggested_range_v == 0.5


def test_callback_gap_and_short_block_have_distinct_findings() -> None:
    result = assess_acquisition_quality(
        AcquisitionQualityInput(
            telemetry=telemetry(
                callback_gaps_s=(0.01, 0.03),
                short_block_count=1,
                captured_samples=900,
            ),
            session_type=SessionType.MEASUREMENT,
            channel_mode=ChannelMode.CH1_ONLY,
            ch1=channel(np.array([-2.0, 2.0])),
        )
    )

    codes = {finding.code for finding in result.findings}
    assert {
        QualityCode.CALLBACK_GAP,
        QualityCode.SHORT_BLOCK,
        QualityCode.INCOMPLETE_CAPTURE,
    } <= codes


def test_healthy_two_channel_capture_has_channel_specific_ranges() -> None:
    result = assess_acquisition_quality(
        AcquisitionQualityInput(
            telemetry=telemetry(),
            session_type=SessionType.MEASUREMENT,
            channel_mode=ChannelMode.DUAL,
            ch1=channel(np.array([-2.0, 2.0]), range_v=5.0),
            ch2=channel(np.array([-3.0, 3.0]), range_v=5.0),
        )
    )

    assert result.findings == ()
    assert tuple(item.channel for item in result.channels) == ("ch1", "ch2")


def test_line_quality_probe_multiplier_is_applied_once() -> None:
    result = assess_acquisition_quality(
        AcquisitionQualityInput(
            telemetry=telemetry(),
            session_type=SessionType.LINE_QUALITY,
            channel_mode=ChannelMode.CH1_ONLY,
            ch1=channel(np.array([-16.4, 16.4]), range_v=5.0, probe=10.0),
        )
    )

    quality = result.channels[0]
    assert quality.peak_range_ratio == pytest.approx(16.4 / 51.2)
    assert QualityCode.CLIPPING not in {finding.code for finding in result.findings}


def test_thresholds_are_frozen_and_versioned() -> None:
    assert QUALITY_THRESHOLDS_V1.quality_thresholds_version == 1
    assert hash(QUALITY_THRESHOLDS_V1)
