from __future__ import annotations

import numpy as np
import pytest

from lnt.events import (
    BaselineFloor,
    DetectionSettings,
    FrequencyBand,
    UnqualifiedGap,
    detect_events,
)
from lnt.events.detector import stream_event_runs
from lnt.events.metrics import EventRun, MetricContext, materialize_event

SAMPLE_RATE_HZ = 10_000.0


def _settings(*, max_gap_samples: int = 2) -> DetectionSettings:
    return DetectionSettings(
        event_detection_version=1,
        preset_name="stream_test",
        noise_window_samples=101,
        noise_step_samples=32,
        minimum_noise_samples=50,
        threshold_sigma=6.0,
        max_gap_samples=max_gap_samples,
        minimum_event_samples=1,
        minimum_snr=6.0,
        chunk_samples=64,
        rail_low_v=-1.0,
        rail_high_v=1.0,
        rail_tolerance_v=1e-6,
        bands=(FrequencyBand(name="all", low_hz=0.0, high_hz=5_000.0),),
    )


def _signal(sample_count: int, dtype: np.dtype[np.floating]) -> np.ndarray:
    samples = np.resize(np.array([-0.01, 0.0, 0.01], dtype=dtype), sample_count)
    return samples.astype(dtype, copy=False)


@pytest.mark.parametrize("dtype", [np.dtype(np.float32), np.dtype(np.float64)])
def test_stream_runs_materialize_to_the_legacy_analytic_inventory(
    dtype: np.dtype[np.floating],
) -> None:
    samples = _signal(512, dtype)
    samples[[80, 240, 400]] = np.array([0.4, -0.5, 0.6], dtype=dtype)
    settings = _settings()

    streamed = tuple(
        item
        for item in stream_event_runs(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=settings)
        if isinstance(item, EventRun)
    )
    materialized = tuple(
        materialize_event(
            run,
            MetricContext(samples=samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=settings),
        )
        for run in streamed
    )

    assert [(run.start, run.end, run.peak) for run in streamed] == [
        (80, 80, 80),
        (240, 240, 240),
        (400, 400, 400),
    ]
    assert (
        materialized
        == detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=settings).events
    )


def test_equal_peak_tie_and_long_run_merge_across_chunks() -> None:
    samples = _signal(256, np.dtype(np.float64))
    crossings = np.arange(55, 77, 3)
    samples[crossings] = 0.5

    items = tuple(
        stream_event_runs(
            samples,
            sample_rate_hz=SAMPLE_RATE_HZ,
            settings=_settings(max_gap_samples=2),
        )
    )

    assert len(items) == 1
    run = items[0]
    assert isinstance(run, EventRun)
    assert (run.start, run.end, run.peak) == (55, 76, 55)


def test_unqualified_gap_flushes_before_later_event_and_blocks_merge() -> None:
    samples = _signal(256, np.dtype(np.float64))
    samples[[78, 82, 170]] = 0.5
    qualified = np.ones(samples.size, dtype=np.bool_)
    qualified[80:82] = False
    baseline = BaselineFloor(
        noise_sigma_v=np.full(samples.size, 0.01),
        qualified=qualified,
        qualification_rule_id="stream_test",
    )

    items = tuple(
        stream_event_runs(
            samples,
            sample_rate_hz=SAMPLE_RATE_HZ,
            settings=_settings(max_gap_samples=8),
            baseline=baseline,
        )
    )

    assert [type(item) for item in items] == [EventRun, UnqualifiedGap, EventRun, EventRun]
    assert [(item.start, item.end) for item in items if isinstance(item, EventRun)] == [
        (78, 78),
        (82, 82),
        (170, 170),
    ]
    assert [
        (item.start_sample, item.end_sample) for item in items if isinstance(item, UnqualifiedGap)
    ] == [(80, 81)]


def test_empty_event_record_coalesces_to_one_full_unqualified_gap() -> None:
    samples = np.zeros(257, dtype=np.float32)

    items = tuple(stream_event_runs(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=_settings()))

    assert items == (
        UnqualifiedGap(
            start_sample=0,
            end_sample=256,
            start_time_s=0.0,
            end_time_s=256 / SAMPLE_RATE_HZ,
        ),
    )


def test_qualified_record_without_events_yields_nothing() -> None:
    assert (
        tuple(
            stream_event_runs(
                _signal(257, np.dtype(np.float64)),
                sample_rate_hz=SAMPLE_RATE_HZ,
                settings=_settings(),
            )
        )
        == ()
    )


def test_many_separated_impulses_yield_before_eof_is_scanned() -> None:
    samples = _signal(3_200, np.dtype(np.float64))
    samples[np.arange(16, samples.size, 64)] = 0.5
    checkpoint_calls = 0

    def checkpoint() -> None:
        nonlocal checkpoint_calls
        checkpoint_calls += 1

    stream = stream_event_runs(
        samples,
        sample_rate_hz=SAMPLE_RATE_HZ,
        settings=_settings(max_gap_samples=2),
        checkpoint=checkpoint,
    )

    first = next(stream)

    assert isinstance(first, EventRun)
    assert first.peak == 16
    assert checkpoint_calls < samples.size // 32


def test_checkpoint_exception_propagates_before_work() -> None:
    error = RuntimeError("cancel before scan")

    def checkpoint() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        next(
            stream_event_runs(
                _signal(128, np.dtype(np.float64)),
                sample_rate_hz=SAMPLE_RATE_HZ,
                settings=_settings(),
                checkpoint=checkpoint,
            )
        )

    assert caught.value is error


def test_checkpoint_exception_propagates_midstream() -> None:
    samples = _signal(1_024, np.dtype(np.float64))
    samples[np.arange(16, samples.size, 64)] = 0.5
    error = RuntimeError("cancel during scan")
    checkpoint_calls = 0

    def checkpoint() -> None:
        nonlocal checkpoint_calls
        checkpoint_calls += 1
        if checkpoint_calls == 8:
            raise error

    with pytest.raises(RuntimeError) as caught:
        tuple(
            stream_event_runs(
                samples,
                sample_rate_hz=SAMPLE_RATE_HZ,
                settings=_settings(),
                checkpoint=checkpoint,
            )
        )

    assert caught.value is error
