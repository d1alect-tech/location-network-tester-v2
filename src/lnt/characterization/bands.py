"""Shared declared and effective characterization frequency bands."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from lnt.errors import InputError
from lnt.features.bands import (
    BandDefinition,
    BandSet,
    EstimandDirection,
    FrequencyUnit,
)

if TYPE_CHECKING:
    from lnt.analysis_store.recipe_v2 import CharacterizationRecipe


@dataclass(frozen=True, slots=True)
class ResolvedBand:
    """One declared band and its sample-rate-supported interval."""

    requested: BandDefinition
    effective: BandDefinition | None
    reason_code: str | None


def resolve_characterization_bands(
    recipe: CharacterizationRecipe,
    sample_rate_hz: float,
) -> tuple[ResolvedBand, ...]:
    """Resolve validated F13 recipe bands against the shared Nyquist limit."""
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise InputError(
            "characterization: частота дискретизации должна быть конечной и положительной"
        )

    f13 = next(family for family in recipe.families if family.id == "f13_band_envelope_coactivity")
    pairs = cast("tuple[tuple[int | float, int | float], ...]", f13.value("bands_hz"))
    requested_bands = BandSet(
        bands=tuple(
            BandDefinition(
                name=f"band_{index:04d}",
                low=float(low),
                high=float(high),
                unit=FrequencyUnit.HZ,
                direction=EstimandDirection.DESCRIPTIVE,
            )
            for index, (low, high) in enumerate(pairs, start=1)
        )
    ).bands
    maximum_hz = recipe.stft.nyquist_fraction_max * sample_rate_hz
    return tuple(_resolve_band(requested, maximum_hz) for requested in requested_bands)


def band_index(frequency_hz: float, bands: tuple[ResolvedBand, ...]) -> int | None:
    """Return the original requested index containing a supported frequency."""
    last_index = len(bands) - 1
    for index, band in enumerate(bands):
        effective = band.effective
        if (
            effective is not None
            and effective.low_hz <= frequency_hz
            and (
                frequency_hz < effective.high_hz
                or (index == last_index and frequency_hz == effective.high_hz)
            )
        ):
            return index
    return None


def _resolve_band(requested: BandDefinition, maximum_hz: float) -> ResolvedBand:
    effective_high_hz = min(requested.high_hz, maximum_hz)
    if effective_high_hz <= requested.low_hz:
        return ResolvedBand(
            requested=requested,
            effective=None,
            reason_code="band_above_nyquist",
        )
    effective = requested
    if effective_high_hz < requested.high_hz:
        effective = BandDefinition(
            name=requested.name,
            low=requested.low_hz,
            high=effective_high_hz,
            unit=FrequencyUnit.HZ,
            direction=EstimandDirection.DESCRIPTIVE,
        )
    return ResolvedBand(requested=requested, effective=effective, reason_code=None)
