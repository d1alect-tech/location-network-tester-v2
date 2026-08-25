"""Общий строитель синтетической probe-pair сессии для CM/DM-тестов."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np

from lnt.cm_dm.capture_support import PARAM_PROBE_PAIR, PROBE_PAIR_TAG
from lnt.session_store import write_session
from lnt.types import (
    SCHEMA_VERSION,
    ChannelMeta,
    ChannelRole,
    ParameterValue,
    SessionManifest,
    SessionSource,
    SessionType,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

DM_TONE_AMPLITUDE_V: float = 0.5
CM_TONE_AMPLITUDE_V: float = 0.25
NOISE_SIGMA_V: float = 0.001
_NOISE_SEED: int = 20260826


def build_probe_pair_session(  # noqa: PLR0913 - поверхность повторяет параметры захвата probe-pair
    target: Path,
    *,
    session_id: str = "cm-dm-1",
    dm_tone_hz: float = 100_000.0,
    cm_tone_hz: float | None = None,
    gain: float = 1.0,
    sample_rate_hz: float = 2_000_000.0,
    duration_s: float = 0.5,
    calibration_params: Mapping[str, ParameterValue] | None = None,
) -> Path:
    """Пишет синтетическую cm_dm-сессию: DM-тон противофазен, CM-тон синфазен.

    CH1 = dm_tone + cm_tone + шум; CH2 = gain * (cm_tone - dm_tone) + шум.
    Противофазный DM-тон попадает в дифференциальную PSD, синфазный CM-тон —
    в синфазную. Без ``calibration_params`` в parameters пишется только тег
    ``probe_pair``; с ними — три калибровочных скаляра плюс тег.
    """
    now = datetime.now(UTC).isoformat()
    sample_count = round(duration_s * sample_rate_hz)
    t = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    dm_tone = DM_TONE_AMPLITUDE_V * np.sin(2.0 * np.pi * dm_tone_hz * t)
    common_tone = (
        CM_TONE_AMPLITUDE_V * np.sin(2.0 * np.pi * cm_tone_hz * t)
        if cm_tone_hz is not None
        else np.zeros(sample_count, dtype=np.float64)
    )
    rng = np.random.default_rng(_NOISE_SEED)
    ch1 = (dm_tone + common_tone + rng.normal(0.0, NOISE_SIGMA_V, sample_count)).astype(np.float32)
    ch2 = (gain * (common_tone - dm_tone) + rng.normal(0.0, NOISE_SIGMA_V, sample_count)).astype(
        np.float32,
    )
    parameters: dict[str, ParameterValue] = (
        dict(calibration_params) if calibration_params is not None else {}
    )
    parameters[PARAM_PROBE_PAIR] = PROBE_PAIR_TAG
    manifest = SessionManifest(
        schema_version=SCHEMA_VERSION,
        session_id=session_id,
        created_utc=now,
        completed_utc=now,
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.CM_DM,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
        sample_count=sample_count,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters=parameters,
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="hf probe",
            range_code=1,
            probe_multiplier=1.0,
        ),
        ch2=ChannelMeta(
            filename="ch2.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="hf probe",
            range_code=1,
            probe_multiplier=1.0,
        ),
        acquisition_telemetry=None,
        synthetic_truth=None,
        ch1_setup=None,
    )
    return write_session(session_dir=target, manifest=manifest, ch1=ch1, ch2=ch2)
