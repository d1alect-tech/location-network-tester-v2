"""Измерение F16 locked support на реалистичной детерминированной записи."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.event_models import (
    RootEvent,
    RootEvents,
    RootEventSettings,
    RootTimelineItem,
    TaggedEvent,
)
from lnt.characterization.f16_engine import compute_f16_multiscale_memory
from lnt.characterization.f16_result import F16Declarations
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status
from lnt.events.models import Polarity

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_FS_HZ = 48_000.0
_SAMPLE_COUNT = 576_000


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=8_192,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4_096,
        max_surrogates=19,
        deterministic_seed=6_022,
    )


def _phase() -> PhaseCycles:
    starts = np.arange(0, _SAMPLE_COUNT + 1, _FS_HZ / 50.0, dtype=np.float64)
    return PhaseCycles(
        sample_rate_hz=_FS_HZ,
        sample_count=_SAMPLE_COUNT,
        cycle_start_samples=starts[:-1],
        cycle_end_samples=starts[1:],
        cycle_valid=np.ones(starts.size - 1, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _means() -> PhaseMeans:
    return PhaseMeans(
        means_v=np.zeros(64, dtype=np.float64),
        counts=np.full(64, 9_000, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _event(peak: int, ordinal: int) -> RootEvent:
    return RootEvent(
        ordinal=ordinal,
        timeline_segment=0,
        start_sample=peak - 2,
        end_sample=peak + 2,
        peak_sample=peak,
        start_time_s=(peak - 2) / _FS_HZ,
        end_time_s=(peak + 2) / _FS_HZ,
        peak_time_s=peak / _FS_HZ,
        peak_value_v=1.0,
        polarity=Polarity.POSITIVE,
        snr_ratio=12.0,
        excess_v2_s=0.002,
        v2_s=0.003,
        clipped=False,
        dominant_band="band_0002",
        dominant_band_reason_code=None,
        boundary=False,
    )


def _inventory(events: tuple[RootEvent, ...]) -> RootEvents:
    def replay(_: Callable[[], None] | None) -> Iterator[RootTimelineItem]:
        for event in events:
            yield TaggedEvent("event", event)

    settings = RootEventSettings(
        recipe_sha256="f16-probe",
        detector="existing_event_inventory",
        noise_window_samples=2_048,
        noise_step_samples=1_024,
        minimum_noise_samples=1_024,
        threshold_sigma=5.0,
        max_gap_samples=4,
        minimum_event_samples=1,
        minimum_snr_db=10.0,
        minimum_snr_ratio=3.9810717055349722,
        dead_time_s=0.001,
        dead_time_samples=48,
        chunk_samples=8_192,
        fft_max_samples=1_048_576,
        clipping_low_v=None,
        clipping_high_v=None,
        clipping_reason_code="not_applicable",
        dead_time_handling="exclude_intervals",
        gap_handling="exclude_crossing_intervals",
    )
    return RootEvents(
        sample_rate_hz=_FS_HZ,
        sample_count=_SAMPLE_COUNT,
        events=events,
        gaps=(),
        exclusions=(),
        candidate_count=len(events),
        snr_rejected_count=0,
        accepted_count=len(events),
        omitted_count=0,
        dead_time_rejected_count=0,
        gap_count=0,
        omitted_gap_count=0,
        omitted_exclusion_count=0,
        selection_rule="first_by_peak_sample",
        retained_candidates_complete=True,
        settings=settings,
        status=Status.AVAILABLE,
        reason_codes=(),
        _replay_factory=replay,
    )


def _samples() -> np.ndarray:
    indices = np.arange(_SAMPLE_COUNT, dtype=np.float64)
    times = indices / _FS_HZ
    bursts = ((indices.astype(np.int64) % 18_500) < 2_000).astype(np.float64)
    return (
        0.55 * np.sin(2.0 * np.pi * 1_730.0 * times)
        + 0.20 * np.sin(2.0 * np.pi * 11_000.0 * times + 0.3)
        + 0.05 * np.cos(2.0 * np.pi * 37_000.0 * times)
        + 0.90 * bursts
    )


def test_locked_thresholds_are_reached_on_realistic_twelve_second_fixture() -> None:
    """12 s / 48 kHz fixture достигает всех pair/window gates и различает radius."""
    peaks = tuple(
        round(second * _FS_HZ) for second in (9.10, 9.20, 9.90, 10.10, 10.20, 10.90, 11.10, 11.90)
    )
    events = tuple(_event(peak, index + 1) for index, peak in enumerate(peaks))

    result = compute_f16_multiscale_memory(
        _samples(),
        _phase(),
        _means(),
        _inventory(events),
        F16Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.AVAILABLE
    assert result.reason_codes == ()
    assert result.pair_count.tolist() == [
        575_995,
        575_952,
        575_520,
        575_040,
        571_200,
        552_000,
    ]
    assert int(np.min(result.pair_count)) >= 100
    assert result.count_window_count.tolist() == [600, 120, 24, 12]
    assert int(np.min(result.count_window_count)) >= 10
    assert np.all(np.isfinite(result.recurrence_rate))
    assert np.all(np.diff(result.recurrence_rate, axis=1) >= 0.0)
    assert float(np.max(np.ptp(result.recurrence_rate, axis=1))) > 0.05
    assert np.all(result.fano_available)
    assert float(np.max(result.fano_factor)) > 1.0
