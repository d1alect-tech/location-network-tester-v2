"""Квалификация фона ripple: измерение не может быть фоном самому себе.

Истина контрактная: ``baseline_identity_reasons`` — чистая функция над
манифестами; одинаковый ``session_id`` (в том числе тот же разрешённый
каталог) означает самосравнение, а не фон.
"""

from __future__ import annotations

from lnt.analysis_v2.ripple_baseline import (
    REASON_SELF_BASELINE,
    baseline_identity_reasons,
)
from lnt.analysis_v2.ripple_options import BaselineAttachment
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
)

_FS_HZ = 10_000.0
_COUNT = 29_000


def _manifest(session_id: str) -> SessionManifest:
    return SessionManifest(
        schema_version=1,
        session_id=session_id,
        created_utc="2026-10-20T00:00:00Z",
        completed_utc="2026-10-20T00:00:03Z",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=_FS_HZ,
        duration_s=_COUNT / _FS_HZ,
        sample_count=_COUNT,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters={},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="ripple baseline fixture",
            range_code=10,
            probe_multiplier=1.0,
        ),
        ch2=None,
        acquisition_telemetry=AcquisitionTelemetry(
            requested_samples=_COUNT,
            captured_samples=_COUNT,
            callback_count=1,
            block_lengths=(_COUNT,),
            callback_gaps_s=(),
            expected_block_interval_s=_COUNT / _FS_HZ,
            short_block_count=0,
            ch1_clip_low_count=0,
            ch1_clip_high_count=0,
            ch2_clip_low_count=0,
            ch2_clip_high_count=0,
            calibration_used=False,
        ),
        synthetic_truth=None,
    )


def _reasons(measurement: SessionManifest, baseline: SessionManifest) -> tuple[str, ...]:
    return baseline_identity_reasons(
        measurement=measurement,
        baseline=baseline,
        attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
    )


def test_self_baseline_rejected_by_session_id() -> None:
    manifest = _manifest("same-session")

    assert REASON_SELF_BASELINE in _reasons(manifest, manifest)


def test_distinct_synthetic_session_stays_qualified() -> None:
    measurement = _manifest("measurement")
    baseline = _manifest("baseline")

    assert _reasons(measurement, baseline) == ()
