"""Bounded records for phase-residual band envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.phase_model import PhaseMeans

type Float64Array = NDArray[np.float64]
type BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class EnvelopeChunk:
    """One half-open native sample span with residual values and qualification."""

    start_sample: int
    stop_sample: int
    values: Float64Array
    valid: BoolArray
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class BandEnvelope:
    """Resolved band metadata and its fixed 64-bin envelope means."""

    resolved: ResolvedBand
    filter_order: int
    phase_means: PhaseMeans


@dataclass(frozen=True, slots=True)
class BandEnvelopes:
    """Bounded summaries with one-band-at-a-time residual replay."""

    bands: tuple[BandEnvelope, ...]
    sample_count: int
    sample_rate_hz: float
    _stream_factory: Callable[[int, Callable[[], None] | None], Iterator[EnvelopeChunk]] = field(
        repr=False, compare=False
    )

    def stream_residuals(
        self, band_index: int, checkpoint: Callable[[], None] | None = None
    ) -> Iterator[EnvelopeChunk]:
        """Replay one band's residual chunks on their native sample spans."""
        self._require_band_index(band_index)
        return self._stream_factory(band_index, checkpoint)

    def residual(
        self,
        band_index: int,
        start_sample: int,
        stop_sample: int,
        checkpoint: Callable[[], None] | None = None,
    ) -> EnvelopeChunk:
        """Return one requested native span without aligning other bands."""
        self._require_band_index(band_index)
        if start_sample < 0 or stop_sample < start_sample or stop_sample > self.sample_count:
            raise ValueError("envelope slice is outside the sample record")
        values = np.zeros(stop_sample - start_sample, dtype=np.float64)
        valid = np.zeros(stop_sample - start_sample, dtype=np.bool_)
        reasons: set[str] = set()
        for chunk in self._stream_factory(band_index, checkpoint):
            low = max(start_sample, chunk.start_sample)
            high = min(stop_sample, chunk.stop_sample)
            if low >= high:
                continue
            source = slice(low - chunk.start_sample, high - chunk.start_sample)
            target = slice(low - start_sample, high - start_sample)
            values[target] = chunk.values[source]
            valid[target] = chunk.valid[source]
            if chunk.reason_code is not None:
                reasons.add(chunk.reason_code)
            if high == stop_sample:
                break
        reason = next(iter(reasons)) if len(reasons) == 1 else None
        if len(reasons) > 1:
            reason = "mixed_unavailable_support"
        return EnvelopeChunk(start_sample, stop_sample, values, valid, reason)

    def _require_band_index(self, band_index: int) -> None:
        if not 0 <= band_index < len(self.bands):
            raise IndexError("band index is outside the resolved band tuple")
