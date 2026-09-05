"""Spectrogram branch adapter for analysis v2."""

from __future__ import annotations

import io

import numpy as np

from lnt.spectrogram import StftSettings, build_overview

from .types import BranchContext, BranchOutput


def run_spectrogram(context: BranchContext) -> BranchOutput:
    """Build the compressed STFT overview artifact ``spectrogram.npz``."""
    overview = build_overview(
        context.session_dir / f"{context.recipe.channels[0]}.npy",
        sample_rate_hz=context.sample_rate_hz,
        settings=StftSettings.from_recipe(context.recipe.spectrogram),
        max_time_bins=256,
        max_frequency_bands=128,
        band_low_hz=max(context.recipe.band_grid.low_hz, 1e-9),
        band_high_hz=context.recipe.band_grid.high_hz,
    )
    buffer = io.BytesIO()
    max_hold_db = overview.max_hold_db
    # Отсутствие max-hold — законное состояние обзора (см. SpectrogramOverview):
    # ключ не пишется вовсе, и читатель трактует это как legacy-артефакт.
    if max_hold_db is None:
        np.savez_compressed(
            buffer,
            time_s=overview.time_s,
            frequency_hz=overview.frequency_hz,
            power_db=overview.power_db,
        )
    else:
        np.savez_compressed(
            buffer,
            time_s=overview.time_s,
            frequency_hz=overview.frequency_hz,
            power_db=overview.power_db,
            power_max_hold_db=max_hold_db,
        )
    return BranchOutput(files={"spectrogram.npz": buffer.getvalue()})
