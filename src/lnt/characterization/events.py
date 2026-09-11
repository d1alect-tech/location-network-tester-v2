"""Bounded root-event computation over the existing streaming detector."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from lnt.characterization.bands import ResolvedBand, resolve_characterization_bands
from lnt.characterization.event_models import (
    DeadTimeExclusion,
    MaterializationContext,
    RootEvent,
    RootEvents,
    RootEventSettings,
    RootTimelineItem,
    TaggedEvent,
    TaggedExclusion,
    TaggedGap,
    materialize_root_event,
)
from lnt.characterization.records import Status
from lnt.events.models import UnqualifiedGap
from lnt.events.settings import event_preset
from lnt.events.stream import stream_event_runs

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.recipe_v2 import CharacterizationRecipe
    from lnt.characterization.clipping import ClippingBounds, FloatArray
    from lnt.events.settings import DetectionSettings

_DETECTOR_WORK_BYTES, _RETAINED_ITEM_BYTES, _NOISE_WINDOW_SAMPLES = 128_032, 1024, 4001


def compute_root_events(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    recipe: CharacterizationRecipe,
    clipping: ClippingBounds,
    checkpoint: Callable[[], None] | None = None,
) -> RootEvents:
    """Compute bounded retained candidates while counting the complete record."""
    _checkpoint(checkpoint)
    settings, detector_settings, bands = _settings(recipe, sample_rate_hz, clipping)
    if not _resources_supported(recipe):
        return _empty_root(samples, sample_rate_hz, settings)

    context = MaterializationContext(
        samples=samples,
        sample_rate_hz=sample_rate_hz,
        detector=detector_settings,
        settings=settings,
        clipping=clipping,
        bands=bands,
        checkpoint=checkpoint,
    )
    events: list[RootEvent] = []
    gaps: list[UnqualifiedGap] = []
    exclusions: list[DeadTimeExclusion] = []
    candidate_count = snr_rejected_count = accepted_count = dead_rejected_count = gap_count = 0
    last_accepted_peak: int | None = None
    last_accepted_ordinal: int | None = None
    for item in stream_event_runs(
        samples,
        sample_rate_hz=sample_rate_hz,
        settings=detector_settings,
        checkpoint=checkpoint,
    ):
        if isinstance(item, UnqualifiedGap):
            gap_count += 1
            if len(gaps) < recipe.resource_limits.max_stored_trajectories:
                gaps.append(item)
            continue
        candidate_count += 1
        if item.peak_deviation / item.peak_sigma < settings.minimum_snr_ratio:
            snr_rejected_count += 1
            continue
        qualified_ordinal = accepted_count + dead_rejected_count + 1
        if (
            last_accepted_peak is not None
            and item.peak - last_accepted_peak < settings.dead_time_samples
        ):
            dead_rejected_count += 1
            if len(exclusions) < recipe.resource_limits.max_stored_trajectories:
                exclusions.append(
                    DeadTimeExclusion(
                        candidate=materialize_root_event(
                            item, qualified_ordinal, gap_count, context
                        ),
                        blocked_by_event_ordinal=_required_ordinal(last_accepted_ordinal),
                        start_sample=last_accepted_peak,
                        end_sample=min(
                            int(samples.size) - 1,
                            last_accepted_peak + settings.dead_time_samples - 1,
                        ),
                    )
                )
            continue
        accepted_count += 1
        last_accepted_peak = item.peak
        last_accepted_ordinal = qualified_ordinal
        if len(events) < recipe.events.maximum_events:
            events.append(materialize_root_event(item, qualified_ordinal, gap_count, context))

    omitted_count = accepted_count - len(events)
    reasons = tuple(
        reason
        for condition, reason in (
            (omitted_count > 0, "event_retention_limit"),
            (gap_count > len(gaps), "gap_retention_limit"),
            (dead_rejected_count > len(exclusions), "exclusion_retention_limit"),
        )
        if condition
    )

    def replay_factory(replay_checkpoint: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        return _replay(replace(context, checkpoint=replay_checkpoint), replay_checkpoint)

    return RootEvents(
        sample_rate_hz=sample_rate_hz,
        sample_count=int(samples.size),
        events=tuple(events),
        gaps=tuple(gaps),
        exclusions=tuple(exclusions),
        candidate_count=candidate_count,
        snr_rejected_count=snr_rejected_count,
        accepted_count=accepted_count,
        omitted_count=omitted_count,
        dead_time_rejected_count=dead_rejected_count,
        gap_count=gap_count,
        omitted_gap_count=gap_count - len(gaps),
        omitted_exclusion_count=dead_rejected_count - len(exclusions),
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=omitted_count == 0,
        settings=settings,
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=reasons,
        _replay_factory=replay_factory,
    )


def _settings(
    recipe: CharacterizationRecipe, sample_rate_hz: float, clipping: ClippingBounds
) -> tuple[RootEventSettings, DetectionSettings, tuple[ResolvedBand, ...]]:
    minimum_snr_ratio = 10.0 ** (recipe.events.minimum_snr_db / 20.0)
    dead_time_samples = math.ceil(recipe.events.dead_time_s * sample_rate_hz)
    base = event_preset("impulses_default")
    detector = replace(
        base,
        threshold_sigma=recipe.events.threshold_sigma,
        minimum_snr=minimum_snr_ratio,
        chunk_samples=recipe.resource_limits.chunk_samples,
    )
    return (
        RootEventSettings(
            recipe_sha256=recipe.recipe_sha256,
            detector=recipe.events.detector,
            noise_window_samples=_NOISE_WINDOW_SAMPLES,
            noise_step_samples=base.noise_step_samples,
            minimum_noise_samples=base.minimum_noise_samples,
            threshold_sigma=recipe.events.threshold_sigma,
            max_gap_samples=base.max_gap_samples,
            minimum_event_samples=base.minimum_event_samples,
            minimum_snr_db=recipe.events.minimum_snr_db,
            minimum_snr_ratio=minimum_snr_ratio,
            dead_time_s=recipe.events.dead_time_s,
            dead_time_samples=dead_time_samples,
            chunk_samples=recipe.resource_limits.chunk_samples,
            fft_max_samples=min(
                base.fft_max_samples,
                recipe.resource_limits.hard_max_chunk_samples,
                recipe.resource_limits.max_work_bytes // 40,
            ),
            clipping_low_v=clipping.low_v,
            clipping_high_v=clipping.high_v,
            clipping_reason_code=clipping.reason_code,
            dead_time_handling=recipe.events.dead_time_handling,
            gap_handling=recipe.events.gap_handling,
        ),
        detector,
        resolve_characterization_bands(recipe, sample_rate_hz),
    )


def _resources_supported(recipe: CharacterizationRecipe) -> bool:
    limits = recipe.resource_limits
    retained_bytes = 3 * limits.max_stored_trajectories * _RETAINED_ITEM_BYTES
    return (
        limits.hard_max_chunk_samples >= _NOISE_WINDOW_SAMPLES
        and limits.max_work_bytes >= _DETECTOR_WORK_BYTES + retained_bytes
    )


def _empty_root(
    samples: FloatArray, sample_rate_hz: float, settings: RootEventSettings
) -> RootEvents:
    def empty(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        _checkpoint(_)
        return iter(())

    return RootEvents(
        sample_rate_hz=sample_rate_hz,
        sample_count=int(samples.size),
        events=(),
        gaps=(),
        exclusions=(),
        candidate_count=0,
        snr_rejected_count=0,
        accepted_count=0,
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=0,
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.UNAVAILABLE,
        reason_codes=("event_detector_work_budget_too_small",),
        _replay_factory=empty,
    )


def _required_ordinal(value: int | None) -> int:
    if value is None:
        raise RuntimeError("accepted event ordinal is missing")
    return value


def _checkpoint(checkpoint: Callable[[], None] | None) -> None:
    if checkpoint is not None:
        checkpoint()


def _replay(
    context: MaterializationContext,
    checkpoint: Callable[[], None] | None,
) -> Iterator[RootTimelineItem]:
    accepted_peak: int | None = None
    accepted_ordinal: int | None = None
    qualified_ordinal = timeline_segment = 0
    for item in stream_event_runs(
        context.samples,
        sample_rate_hz=context.sample_rate_hz,
        settings=context.detector,
        checkpoint=checkpoint,
    ):
        if isinstance(item, UnqualifiedGap):
            yield TaggedGap("gap", item)
            timeline_segment += 1
            continue
        if item.peak_deviation / item.peak_sigma < context.settings.minimum_snr_ratio:
            continue
        qualified_ordinal += 1
        event = materialize_root_event(item, qualified_ordinal, timeline_segment, context)
        if (
            accepted_peak is not None
            and item.peak - accepted_peak < context.settings.dead_time_samples
        ):
            exclusion = DeadTimeExclusion(
                candidate=event,
                blocked_by_event_ordinal=_required_ordinal(accepted_ordinal),
                start_sample=accepted_peak,
                end_sample=min(
                    int(context.samples.size) - 1,
                    accepted_peak + context.settings.dead_time_samples - 1,
                ),
            )
            yield TaggedExclusion("exclusion", exclusion)
            continue
        accepted_peak, accepted_ordinal = item.peak, qualified_ordinal
        yield TaggedEvent("event", event)
