"""Общий строитель синтетической line-quality сессии для тестов."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np

from lnt.session_store import write_session
from lnt.types import (
    CH1_MANIFEST_SCHEMA_VERSION,
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
    TransformerLineProbe,
)

if TYPE_CHECKING:
    from pathlib import Path

LINE_SAMPLE_RATE_HZ = 200_000.0
LINE_DURATION_S = 2.0


def write_line_quality_session(
    target: Path,
    *,
    session_id: str = "line-quality-fixture",
    h3_ratio: float = 0.05,
) -> Path:
    """Пишет на диск синтетическую line-quality сессию (50 Гц + H3)."""
    now = datetime.now(UTC).isoformat()
    sample_count = round(LINE_DURATION_S * LINE_SAMPLE_RATE_HZ)
    t = np.arange(sample_count, dtype=np.float64) / LINE_SAMPLE_RATE_HZ
    wave = np.sin(2.0 * np.pi * 50.0 * t) + h3_ratio * np.sin(2.0 * np.pi * 150.0 * t)
    manifest = SessionManifest(
        schema_version=CH1_MANIFEST_SCHEMA_VERSION,
        session_id=session_id,
        created_utc=now,
        completed_utc=now,
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.LINE_QUALITY,
        sample_rate_hz=LINE_SAMPLE_RATE_HZ,
        duration_s=LINE_DURATION_S,
        sample_count=sample_count,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters={},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.LF_TRANSFORMER,
            unit="V",
            front_end="transformer 230:6",
            range_code=1,
            probe_multiplier=10.0,
        ),
        ch2=None,
        acquisition_telemetry=None,
        synthetic_truth=None,
        ch1_setup=TransformerLineProbe(
            nominal_primary_v=230.0,
            nominal_secondary_v=6.0,
            probe_multiplier=10.0,
        ),
    )
    return write_session(
        session_dir=target,
        manifest=manifest,
        ch1=(15.0 * wave).astype(np.float32),
        ch2=None,
    )
