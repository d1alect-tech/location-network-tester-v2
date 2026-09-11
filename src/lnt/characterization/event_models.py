"""Bounded public records for the characterization root-event inventory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from lnt.events.metrics import EventRun, dominant_band
from lnt.events.models import Polarity
from lnt.events.settings import FrequencyBand

_MINIMUM_FFT_SAMPLES = 4

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.clipping import ClippingBounds, FloatArray
    from lnt.characterization.records import Status
    from lnt.events.models import UnqualifiedGap
    from lnt.events.settings import DetectionSettings


@dataclass(frozen=True, slots=True, kw_only=True)
class RootEventSettings:
    """Complete effective settings and provenance for one root computation."""

    recipe_sha256: str
    detector: str
    noise_window_samples: int
    noise_step_samples: int
    minimum_noise_samples: int
    threshold_sigma: float
    max_gap_samples: int
    minimum_event_samples: int
    minimum_snr_db: float
    minimum_snr_ratio: float
    dead_time_s: float
    dead_time_samples: int
    chunk_samples: int
    fft_max_samples: int
    clipping_low_v: float | None
    clipping_high_v: float | None
    clipping_reason_code: str | None
    dead_time_handling: str
    gap_handling: str

    def to_dict(self) -> dict[str, str | int | float | None]:
        """Return JSON-safe effective settings."""
        return {
            "recipe_sha256": self.recipe_sha256,
            "detector": self.detector,
            "noise_window_samples": self.noise_window_samples,
            "noise_step_samples": self.noise_step_samples,
            "minimum_noise_samples": self.minimum_noise_samples,
            "threshold_sigma": self.threshold_sigma,
            "max_gap_samples": self.max_gap_samples,
            "minimum_event_samples": self.minimum_event_samples,
            "minimum_snr_db": self.minimum_snr_db,
            "minimum_snr_ratio": self.minimum_snr_ratio,
            "dead_time_s": self.dead_time_s,
            "dead_time_samples": self.dead_time_samples,
            "chunk_samples": self.chunk_samples,
            "fft_max_samples": self.fft_max_samples,
            "clipping_low_v": self.clipping_low_v,
            "clipping_high_v": self.clipping_high_v,
            "clipping_reason_code": self.clipping_reason_code,
            "dead_time_handling": self.dead_time_handling,
            "gap_handling": self.gap_handling,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RootEvent:
    """One qualified, non-causal event candidate in saved volts."""

    ordinal: int
    timeline_segment: int
    start_sample: int
    end_sample: int
    peak_sample: int
    start_time_s: float
    end_time_s: float
    peak_time_s: float
    peak_value_v: float
    polarity: Polarity
    snr_ratio: float
    excess_v2_s: float
    v2_s: float
    clipped: bool | None
    dominant_band: str | None
    dominant_band_reason_code: str | None
    boundary: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class DeadTimeExclusion:
    """Qualified candidate rejected inside an accepted event's dead interval."""

    candidate: RootEvent
    blocked_by_event_ordinal: int
    start_sample: int
    end_sample: int


@dataclass(frozen=True, slots=True)
class TaggedEvent:
    """Accepted event tagged for timeline replay."""

    kind: Literal["event"]
    event: RootEvent


@dataclass(frozen=True, slots=True)
class TaggedGap:
    """Unqualified gap tagged for timeline replay."""

    kind: Literal["gap"]
    gap: UnqualifiedGap


@dataclass(frozen=True, slots=True)
class TaggedExclusion:
    """Dead-time exclusion tagged for timeline replay."""

    kind: Literal["exclusion"]
    exclusion: DeadTimeExclusion


type RootTimelineItem = TaggedEvent | TaggedGap | TaggedExclusion
type ReplayFactory = Callable[[Callable[[], None] | None], Iterator[RootTimelineItem]]


@dataclass(frozen=True, slots=True, kw_only=True)
class RootEvents:
    """Bounded retained prefixes plus exact full-record accounting and replay."""

    sample_rate_hz: float
    sample_count: int
    events: tuple[RootEvent, ...]
    gaps: tuple[UnqualifiedGap, ...]
    exclusions: tuple[DeadTimeExclusion, ...]
    candidate_count: int
    snr_rejected_count: int
    accepted_count: int
    omitted_count: int
    dead_time_rejected_count: int
    gap_count: int
    omitted_gap_count: int
    omitted_exclusion_count: int
    selection_rule: str
    retained_candidates_complete: bool
    settings: RootEventSettings
    status: Status
    reason_codes: tuple[str, ...]
    _replay_factory: ReplayFactory = field(repr=False, compare=False)

    def replay(self, checkpoint: Callable[[], None] | None = None) -> Iterator[RootTimelineItem]:
        """Stream every qualified event, gap, and exclusion again in timeline order."""
        return self._replay_factory(checkpoint)


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializationContext:
    """Bounded source and settings needed to materialize one event run."""

    samples: FloatArray
    sample_rate_hz: float
    detector: DetectionSettings
    settings: RootEventSettings
    clipping: ClippingBounds
    bands: tuple[ResolvedBand, ...]
    checkpoint: Callable[[], None] | None


def materialize_root_event(
    run: EventRun, ordinal: int, timeline_segment: int, context: MaterializationContext
) -> RootEvent:
    """Materialize one run without reading more than the declared bounded span."""
    _checkpoint(context.checkpoint)
    polarity = (
        Polarity.BIPOLAR
        if run.positive and run.negative
        else Polarity.POSITIVE
        if run.positive
        else Polarity.NEGATIVE
    )
    dominant, dominant_reason = _dominant(run, context)
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=timeline_segment,
        start_sample=run.start,
        end_sample=run.end,
        peak_sample=run.peak,
        start_time_s=run.start / context.sample_rate_hz,
        end_time_s=run.end / context.sample_rate_hz,
        peak_time_s=run.peak / context.sample_rate_hz,
        peak_value_v=run.peak_value,
        polarity=polarity,
        snr_ratio=run.peak_deviation / run.peak_sigma,
        excess_v2_s=run.excess_energy_sum / context.sample_rate_hz,
        v2_s=_v2_s(run, context),
        clipped=_classify_clipping(run, context),
        dominant_band=dominant,
        dominant_band_reason_code=dominant_reason,
        boundary=run.start == 0 or run.end == int(context.samples.size) - 1,
    )


def _dominant(run: EventRun, context: MaterializationContext) -> tuple[str | None, str | None]:
    length = run.end - run.start + 1
    if length > context.settings.fft_max_samples:
        return None, "event_exceeds_fft_max_samples"
    effective = tuple(item for item in context.bands if item.effective is not None)
    if length < _MINIMUM_FFT_SAMPLES or not effective:
        return None, "dominant_band_insufficient_support"
    span = np.asarray(context.samples[run.start : run.end + 1], dtype=np.float64)
    name = dominant_band(
        span,
        sample_rate_hz=context.sample_rate_hz,
        bands=tuple(
            FrequencyBand(
                name=item.requested.name,
                low_hz=item.effective.low_hz,
                high_hz=item.effective.high_hz,
            )
            for item in effective
            if item.effective is not None
        ),
        fft_max_samples=context.settings.fft_max_samples,
        interval_rule="half_open_last_closed",
    )
    if name is None:
        return None, "dominant_band_no_in_band_signal"
    return name, None


def _v2_s(run: EventRun, context: MaterializationContext) -> float:
    total = 0.0
    for low in range(run.start, run.end + 1, context.settings.chunk_samples):
        _checkpoint(context.checkpoint)
        values = np.asarray(
            context.samples[low : min(run.end + 1, low + context.settings.chunk_samples)],
            dtype=np.float64,
        )
        total += float(np.dot(values, values))
    return total / context.sample_rate_hz


def _classify_clipping(run: EventRun, context: MaterializationContext) -> bool | None:
    result: bool | None = False
    for low in range(run.start, run.end + 1, context.settings.chunk_samples):
        _checkpoint(context.checkpoint)
        classified = context.clipping.classify(
            context.samples[low : min(run.end + 1, low + context.settings.chunk_samples)]
        )
        if classified is True:
            return True
        if classified is None:
            result = None
    return result


def _checkpoint(checkpoint: Callable[[], None] | None) -> None:
    if checkpoint is not None:
        checkpoint()
