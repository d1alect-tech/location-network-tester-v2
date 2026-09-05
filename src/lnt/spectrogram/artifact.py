"""NPZ + JSON metadata сериализация обзора спектрограммы."""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, TypedDict

import numpy as np

from lnt.spectrogram.errors import SpectrogramArtifactError, SpectrogramCancelledError
from lnt.spectrogram.models import CancellationToken, SpectrogramOverview, StftSettings

if TYPE_CHECKING:
    from pathlib import Path


class ArtifactMetadata(TypedDict):
    """JSON metadata schema 1 внутри NPZ."""

    schema: int
    settings: dict[str, int | str]
    db_reference: float
    floor_db: float
    ceiling_db: float


def save_overview(
    path: Path,
    overview: SpectrogramOverview,
    *,
    cancellation: CancellationToken | None = None,
) -> None:
    """Атомарно сохраняет float32 dB, axes, coverage и JSON metadata в NPZ."""
    _check_cancelled(cancellation)
    temporary = path.with_name(f"{path.name}.partial-{uuid.uuid4().hex}")
    metadata: ArtifactMetadata = {
        "schema": 1,
        "settings": {
            "version": overview.settings.version,
            "window": overview.settings.window,
            "segment_samples": overview.settings.segment_samples,
            "hop_samples": overview.settings.hop_samples,
            "detrend": overview.settings.detrend,
            "scaling": overview.settings.scaling,
        },
        "db_reference": overview.db_reference,
        "floor_db": overview.floor_db,
        "ceiling_db": overview.ceiling_db,
    }
    metadata_array = np.asarray(json.dumps(metadata, sort_keys=True))
    max_hold_db = overview.max_hold_db
    try:
        with temporary.open("xb") as stream:
            # Отсутствие max-hold — законное состояние обзора (см. SpectrogramOverview):
            # ключ не пишется вовсе, и читатель трактует это как legacy-артефакт.
            if max_hold_db is None:
                np.savez(
                    stream,
                    power_db=overview.power_db,
                    coverage=overview.coverage,
                    time_s=overview.time_s,
                    frequency_hz=overview.frequency_hz,
                    frequency_edges_hz=overview.frequency_edges_hz,
                    metadata=metadata_array,
                )
            else:
                np.savez(
                    stream,
                    power_db=overview.power_db,
                    power_max_hold_db=max_hold_db,
                    coverage=overview.coverage,
                    time_s=overview.time_s,
                    frequency_hz=overview.frequency_hz,
                    frequency_edges_hz=overview.frequency_edges_hz,
                    metadata=metadata_array,
                )
            stream.flush()
            os.fsync(stream.fileno())
        _check_cancelled(cancellation)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_overview(path: Path) -> SpectrogramOverview:
    """Строго читает schema 1 и отклоняет shape/dtype/NaN несогласованность."""
    try:
        with np.load(path, allow_pickle=False) as archive:
            power_db = np.asarray(archive["power_db"], dtype=np.float32)
            coverage = np.asarray(archive["coverage"], dtype=np.uint32)
            time_s = np.asarray(archive["time_s"], dtype=np.float64)
            frequency_hz = np.asarray(archive["frequency_hz"], dtype=np.float64)
            edges = np.asarray(archive["frequency_edges_hz"], dtype=np.float64)
            metadata = json.loads(str(archive["metadata"]))
            hold_present = "power_max_hold_db" in archive
            hold_db = (
                np.asarray(archive["power_max_hold_db"], dtype=np.float32)
                if hold_present
                else np.full(power_db.shape, np.nan, dtype=np.float32)
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise SpectrogramArtifactError(path, "npz_or_metadata") from error
    if not isinstance(metadata, dict) or metadata.get("schema") != 1:
        raise SpectrogramArtifactError(path, "schema")
    if power_db.shape != coverage.shape or power_db.shape != (frequency_hz.size, time_s.size):
        raise SpectrogramArtifactError(path, "shape")
    if hold_db.shape != power_db.shape:
        raise SpectrogramArtifactError(path, "shape")
    if not np.array_equal(np.isnan(power_db), coverage == 0):
        raise SpectrogramArtifactError(path, "coverage")
    if hold_present and not np.array_equal(np.isnan(hold_db), coverage == 0):
        raise SpectrogramArtifactError(path, "coverage")
    try:
        raw = metadata["settings"]
        settings = StftSettings.parse(
            version=int(raw["version"]),
            window=str(raw["window"]),
            segment_samples=int(raw["segment_samples"]),
            hop_samples=int(raw["hop_samples"]),
            detrend=str(raw["detrend"]),
            scaling=str(raw["scaling"]),
        )
        reference = float(metadata["db_reference"])
        floor = float(metadata["floor_db"])
        ceiling = float(metadata["ceiling_db"])
    except (KeyError, TypeError, ValueError) as error:
        raise SpectrogramArtifactError(path, "metadata_fields") from error
    linear = np.full(power_db.shape, np.nan, dtype=np.float64)
    available = coverage > 0
    linear[available] = reference * np.power(10.0, power_db[available] / 10.0)
    hold_linear = np.full(power_db.shape, np.nan, dtype=np.float64)
    hold_linear[available] = reference * np.power(10.0, hold_db[available] / 10.0)
    return SpectrogramOverview(
        power_db=power_db,
        linear_power=linear,
        max_hold_db=hold_db,
        max_hold_linear=hold_linear,
        coverage=coverage,
        time_s=time_s,
        frequency_hz=frequency_hz,
        frequency_edges_hz=edges,
        settings=settings,
        db_reference=reference,
        floor_db=floor,
        ceiling_db=ceiling,
    )


def _check_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation is not None and cancellation.cancelled():
        raise SpectrogramCancelledError
