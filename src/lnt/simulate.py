"""Синтетическая сессия на диске: generate -> манифест -> атомарная запись."""

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from lnt.errors import InputError
from lnt.manifest import validated_label
from lnt.session_store import write_session
from lnt.signals import generate
from lnt.types import (
    SCHEMA_VERSION,
    ChannelMeta,
    ChannelMode,
    ChannelRole,
    ParameterValue,
    SeriesPosition,
    SessionManifest,
    SessionSource,
    SessionType,
)

CH1_FILENAME = "ch1.npy"
CH2_FILENAME = "ch2.npy"
LINE_FREQUENCY_HZ = 50.0


def simulate_session(  # noqa: PLR0913 -- сборочная точка сессии: все параметры kw-only с дефолтами
    *,
    out_dir: Path,
    profile: str,
    duration_s: float,
    sample_rate_hz: float,
    seed: int,
    label: str | None = None,
    series: SeriesPosition | None = None,
    channel_mode: ChannelMode = ChannelMode.DUAL,
) -> Path:
    """Генерирует профиль и атомарно пишет полноценную сессию в ``out_dir``."""
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        raise InputError("длительность должна быть конечной и положительной")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("частота дискретизации должна быть конечной и положительной")
    if seed < 0:
        raise InputError("seed должен быть неотрицательным")
    normalized_label = validated_label(label)
    session = generate(
        profile=profile,
        duration_s=duration_s,
        sample_rate_hz=sample_rate_hz,
        rng=np.random.default_rng(seed),
        line_frequency_hz=LINE_FREQUENCY_HZ,
    )
    parameters: dict[str, ParameterValue] = {"seed": seed}
    if normalized_label is not None:
        parameters["label"] = normalized_label
    if series is not None:
        parameters.update(series.as_parameters())
    id_suffix = series.id_suffix() if series is not None else ""
    now = datetime.now(UTC).isoformat()
    manifest = SessionManifest(
        schema_version=SCHEMA_VERSION,
        session_id=f"syn-{profile}-seed{seed}{id_suffix}",
        created_utc=now,
        completed_utc=now,
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
        sample_count=session.ch1.size,
        line_frequency_hz=LINE_FREQUENCY_HZ,
        profile=profile,
        baseline_session=None,
        parameters=parameters,
        ch1=ChannelMeta(
            filename=CH1_FILENAME,
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="synthetic",
            range_code=1,
            probe_multiplier=1.0,
        ),
        ch2=(
            ChannelMeta(
                filename=CH2_FILENAME,
                role=ChannelRole.LF_TRANSFORMER,
                unit="V",
                front_end="synthetic",
                range_code=1,
                probe_multiplier=1.0,
            )
            if channel_mode is ChannelMode.DUAL
            else None
        ),
        acquisition_telemetry=None,
        synthetic_truth=session.truth,
    )
    return write_session(
        session_dir=out_dir,
        manifest=manifest,
        ch1=session.ch1,
        ch2=(session.ch2 if channel_mode is ChannelMode.DUAL else None),
    )
