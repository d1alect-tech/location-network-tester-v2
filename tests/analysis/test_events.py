"""Golden tests for deterministic candidate-event inventory."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from lnt.events import (
    BaselineFloor,
    DetectionSettings,
    FrequencyBand,
    detect_events,
    event_preset,
)

SAMPLE_RATE_HZ = 100_000.0
TIMING_TOLERANCE_SAMPLES = 8


def _settings() -> DetectionSettings:
    return DetectionSettings(
        event_detection_version=1,
        preset_name="golden_test",
        noise_window_samples=501,
        noise_step_samples=64,
        minimum_noise_samples=250,
        threshold_sigma=6.0,
        max_gap_samples=8,
        minimum_event_samples=1,
        minimum_snr=6.0,
        chunk_samples=2_048,
        rail_low_v=-1.0,
        rail_high_v=1.0,
        rail_tolerance_v=1e-6,
        bands=(
            FrequencyBand(name="low", low_hz=0.0, high_hz=2_000.0),
            FrequencyBand(name="ring", low_hz=2_000.0, high_hz=8_000.0),
            FrequencyBand(name="high", low_hz=8_000.0, high_hz=30_000.0),
        ),
    )


def _noise(sample_count: int) -> np.ndarray:
    return np.random.default_rng(20260811).normal(0.0, 0.01, sample_count).astype(np.float64)


def _matched(event_samples: list[int], truth_samples: list[int]) -> tuple[float, float]:
    matches = sum(
        any(abs(event_sample - truth) <= TIMING_TOLERANCE_SAMPLES for event_sample in event_samples)
        for truth in truth_samples
    )
    precision = matches / len(event_samples)
    recall = matches / len(truth_samples)
    return precision, recall


def test_detects_injected_impulses_with_exact_precision_and_recall() -> None:
    # Given: three clearly separated, clearly above-threshold impulses in realistic white noise.
    samples = _noise(20_000)
    truth = [3_000, 9_000, 15_000]
    samples[truth] += np.array([0.35, -0.40, 0.45])

    # When: deterministic local median/MAD detection scans bounded chunks.
    inventory = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=_settings())

    # Then: timing is judged at the peak within ±8 samples (80 µs), with no extras or misses.
    precision, recall = _matched([event.peak_sample for event in inventory.events], truth)
    assert (precision, recall) == (1.0, 1.0)
    assert [event.polarity.value for event in inventory.events] == [
        "positive",
        "negative",
        "positive",
    ]


def test_detects_burst_and_identifies_dominant_band() -> None:
    # Given: a 5 kHz burst spanning enough samples for deterministic short-FFT classification.
    samples = _noise(12_000)
    start = 5_000
    length = 200
    phase = np.arange(length, dtype=np.float64) / SAMPLE_RATE_HZ
    samples[start : start + length] += 0.20 * np.sin(2.0 * np.pi * 5_000.0 * phase)

    # When: adjacent threshold crossings are merged only through qualified short gaps.
    inventory = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=_settings())

    # Then: the burst is one bipolar candidate in the configured ring band.
    assert len(inventory.events) == 1
    event = inventory.events[0]
    assert event.polarity.value == "bipolar"
    assert event.dominant_band == "ring"
    assert event.start_sample <= start + TIMING_TOLERANCE_SAMPLES
    assert event.end_sample >= start + length - TIMING_TOLERANCE_SAMPLES


def test_noise_only_false_positive_budget_is_zero_at_six_sigma() -> None:
    # Given: fixed realistic white noise without injected transients.
    samples = _noise(20_000)

    # When: the documented six-sigma preset threshold is used.
    inventory = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=_settings())

    # Then: the fixed golden fixture's false-positive budget is exactly zero.
    assert inventory.events == ()


def test_clipped_candidate_is_retained_and_flagged() -> None:
    # Given: an impulse touching the configured positive acquisition rail.
    samples = _noise(8_000)
    samples[4_000] = 1.0

    # When: candidate events are inventoried.
    inventory = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=_settings())

    # Then: clipping is metadata, never a reason to discard the candidate.
    assert len(inventory.events) == 1
    assert inventory.events[0].clipped is True


def test_record_edge_candidate_has_boundary_flag() -> None:
    # Given: a clearly above-threshold impulse at the first sample.
    samples = _noise(8_000)
    samples[0] = 0.5

    # When: the record is scanned.
    inventory = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=_settings())

    # Then: it remains a candidate and records contact with the record boundary.
    assert len(inventory.events) == 1
    assert inventory.events[0].boundary is True


def test_unqualified_baseline_gap_is_reported_and_never_bridged() -> None:
    # Given: threshold crossings on both sides of an explicitly unqualified baseline interval.
    samples = _noise(8_000)
    samples[3_998] = 0.35
    samples[4_002] = 0.40
    qualified = np.ones(samples.size, dtype=np.bool_)
    qualified[4_000:4_002] = False
    baseline = BaselineFloor(
        noise_sigma_v=np.full(samples.size, 0.01),
        qualified=qualified,
        qualification_rule_id="compatible_baseline_v1",
    )
    settings = replace(_settings(), max_gap_samples=16)

    # When: a gap shorter than max_gap is nevertheless unqualified.
    inventory = detect_events(
        samples,
        sample_rate_hz=SAMPLE_RATE_HZ,
        settings=settings,
        baseline=baseline,
    )

    # Then: qualification wins over merge distance and the gap remains explicit.
    assert len(inventory.events) == 2
    assert [(gap.start_sample, gap.end_sample) for gap in inventory.unqualified_gaps] == [
        (4_000, 4_001)
    ]


def test_inventory_serialization_is_deterministic_and_persists_thresholds() -> None:
    # Given: an impulse and a named production preset.
    samples = _noise(8_000)
    samples[4_000] = 0.5
    settings = event_preset("impulses_default")

    # When: identical input is processed twice.
    first = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=settings).to_dict()
    second = detect_events(samples, sample_rate_hz=SAMPLE_RATE_HZ, settings=settings).to_dict()

    # Then: JSON-safe payloads are identical and preserve every effective threshold plus its hash.
    assert first == second
    assert json.loads(json.dumps(first, ensure_ascii=False)) == first
    assert first["language"] == "кандидаты событий"
    assert first["settings"]["event_detection_version"] == 1
    assert first["settings"]["threshold_sigma"] == pytest.approx(6.0)
    assert len(first["settings_hash"]) == 64


def test_presets_are_complete_and_distinct() -> None:
    # Given/When: both public presets are resolved to full effective settings.
    impulses = event_preset("impulses_default")
    bursts = event_preset("bursts_default")

    # Then: both are versioned and differ in explicit merge/event thresholds.
    assert impulses.event_detection_version == bursts.event_detection_version == 1
    assert impulses.max_gap_samples < bursts.max_gap_samples
    assert impulses.minimum_event_samples < bursts.minimum_event_samples
