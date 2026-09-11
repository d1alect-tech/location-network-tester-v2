"""Prepare bounded characterization roots from immutable saved channels."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal, cast

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.bands import resolve_characterization_bands
from lnt.characterization.clipping import resolve_clipping
from lnt.characterization.envelopes import prepare_band_envelopes
from lnt.characterization.events import compute_root_events
from lnt.characterization.phase import (
    compute_phase_cycles,
    compute_phase_means,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store import CharacterizationRecipe
    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.clipping import ClippingBounds
    from lnt.characterization.envelope_models import BandEnvelopes
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase import PhaseCycles, PhaseMeans
    from lnt.session_store import LoadedSession
    from lnt.types import SessionManifest

type ChannelName = Literal["ch1", "ch2"]
type Float32Array = NDArray[np.float32]

__all__ = ["ChannelRoots", "SharedComputations", "prepare_shared_computations"]


@dataclass(frozen=True, slots=True, kw_only=True)
class ChannelRoots:
    """Saved channel reference and its reusable bounded roots."""

    name: ChannelName
    samples: Float32Array | None
    clipping: ClippingBounds | None
    phase_means: PhaseMeans | None
    root_events: RootEvents | None
    band_envelopes: BandEnvelopes | None
    reason: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SharedComputations:
    """Common inputs and roots prepared once for later descriptor families."""

    manifest: SessionManifest
    recipe: CharacterizationRecipe
    sample_rate_hz: float
    sample_count: int
    phase: PhaseCycles
    bands: tuple[ResolvedBand, ...]
    channels: tuple[ChannelRoots, ...]


def prepare_shared_computations(
    session: LoadedSession,
    recipe: CharacterizationRecipe,
    *,
    checkpoint: Callable[[], None] | None = None,
) -> SharedComputations:
    """Prepare each declared available channel without copying saved arrays."""
    _checkpoint(checkpoint)
    sample_rate_hz = session.manifest.sample_rate_hz
    phase = compute_phase_cycles(
        session.ch2 if "ch2" in recipe.channels else None,
        sample_rate_hz=sample_rate_hz,
        settings=recipe.phase,
        resources=recipe.resource_limits,
        checkpoint=checkpoint,
    )
    _checkpoint(checkpoint)
    bands = resolve_characterization_bands(recipe, sample_rate_hz)
    _checkpoint(checkpoint)
    channels: list[ChannelRoots] = []
    for raw_name in recipe.channels:
        name = cast("ChannelName", raw_name)
        samples = session.ch1 if name == "ch1" else session.ch2
        if samples is None:
            channels.append(_missing_channel(name))
            _checkpoint(checkpoint)
            continue
        clipping = resolve_clipping(
            session.manifest,
            name,
            recipe.events.clipping_fraction_of_range,
        )
        _checkpoint(checkpoint)
        phase_means = compute_phase_means(
            samples,
            phase,
            settings=recipe.phase,
            resources=recipe.resource_limits,
            checkpoint=checkpoint,
        )
        _checkpoint(checkpoint)
        root_events = compute_root_events(
            samples,
            sample_rate_hz=sample_rate_hz,
            recipe=recipe,
            clipping=clipping,
            checkpoint=checkpoint,
        )
        _checkpoint(checkpoint)
        band_envelopes = prepare_band_envelopes(
            samples,
            _envelope_phase(phase, int(samples.size)),
            recipe,
            sample_rate_hz=sample_rate_hz,
            checkpoint=checkpoint,
        )
        channels.append(
            ChannelRoots(
                name=name,
                samples=samples,
                clipping=clipping,
                phase_means=phase_means,
                root_events=root_events,
                band_envelopes=band_envelopes,
                reason=None,
            )
        )
        _checkpoint(checkpoint)
    result = SharedComputations(
        manifest=session.manifest,
        recipe=recipe,
        sample_rate_hz=sample_rate_hz,
        sample_count=session.manifest.sample_count,
        phase=phase,
        bands=bands,
        channels=tuple(channels),
    )
    _checkpoint(checkpoint)
    return result


def _missing_channel(name: ChannelName) -> ChannelRoots:
    return ChannelRoots(
        name=name,
        samples=None,
        clipping=None,
        phase_means=None,
        root_events=None,
        band_envelopes=None,
        reason="channel_missing",
    )


def _envelope_phase(phase: PhaseCycles, sample_count: int) -> PhaseCycles:
    if phase.sample_count == 0:
        return replace(phase, sample_count=sample_count)
    return phase


def _checkpoint(checkpoint: Callable[[], None] | None) -> None:
    if checkpoint is not None:
        checkpoint()
