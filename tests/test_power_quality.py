"""Golden tests for the per-half-cycle RMS power-quality detector (A1)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.power_quality import (
    HalfCycleRmsSeries,
    PowerQualityInventory,
    detect_half_cycle_rms,
    detect_power_quality,
    power_quality_preset,
)

if TYPE_CHECKING:
    from collections.abc import Callable

SAMPLE_RATE_HZ = 100_000.0
LINE_HZ = 50.0


def _signal(duration_s: float, profile: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """Синтетика: несущая 50 Гц с кусочно-постоянной амплитудой (float32)."""
    time_s = np.arange(round(SAMPLE_RATE_HZ * duration_s), dtype=np.float64) / SAMPLE_RATE_HZ
    amplitude = profile(time_s)
    return (amplitude * np.sin(2.0 * np.pi * LINE_HZ * time_s)).astype(np.float32)


def _flat(factor: float = 1.0) -> Callable[[np.ndarray], np.ndarray]:
    return lambda time_s: np.full(time_s.size, factor)


def _stepped(start_s: float, end_s: float, factor: float) -> Callable[[np.ndarray], np.ndarray]:
    def profile(time_s: np.ndarray) -> np.ndarray:
        amplitude = np.ones(time_s.size)
        amplitude[(time_s >= start_s) & (time_s < end_s)] = factor
        return amplitude

    return profile


def _series(samples: np.ndarray, *, chunk_samples: int = 1_048_576) -> HalfCycleRmsSeries:
    return detect_half_cycle_rms(samples, line_frequency_hz=LINE_HZ, chunk_samples=chunk_samples)


def _inventory(samples: np.ndarray, *, chunk_samples: int = 1_048_576) -> PowerQualityInventory:
    settings = power_quality_preset("itic_default")
    return detect_power_quality(_series(samples, chunk_samples=chunk_samples), settings=settings)


def test_nominal_signal_zero_events() -> None:
    # Given: flat-amplitude 50 Hz carrier, half a second.
    samples = _signal(0.5, _flat())

    # When: the power-quality detector scans the half-cycle RMS series.
    inventory = _inventory(samples)

    # Then: a healthy mains record raises neither voltage events nor RVC steps.
    assert inventory.events == ()
    assert inventory.rvc_events == ()
    assert inventory.half_cycle_rms_summary["count"] == 50
    assert inventory.half_cycle_rms_summary["nominal_rms_v"] == pytest.approx(
        np.sqrt(0.5), rel=1e-3
    )


def test_sag_detected_with_depth_and_duration() -> None:
    # Given: amplitude dropped to 60% of nominal for exactly 200 ms.
    samples = _signal(0.5, _stepped(0.05, 0.25, 0.6))

    # When: detection runs on the self-referenced half-cycle RMS series.
    inventory = _inventory(samples)

    # Then: one sag event with 40% depth and 200 ms duration; 60% < 70%-floor
    # of ITIC for 200 ms, so the honest verdict is out_of_tolerance.
    assert len(inventory.events) == 1
    event = inventory.events[0]
    assert event.kind.value == "sag"
    assert event.depth_pct == pytest.approx(40.0, rel=1e-2)
    assert event.duration_s == pytest.approx(0.2, rel=1e-2)
    assert event.verdict.value == "out_of_tolerance"
    assert event.itic_region.value == "sag"


def test_dropout_short_event_classified() -> None:
    # Given: near-zero amplitude for 15 ms starting exactly on a cycle boundary.
    samples = _signal(0.4, _stepped(0.10, 0.115, 0.001))

    # When: detection runs.
    inventory = _inventory(samples)

    # Then: the dip is a dropout, sub-half-cycle edges give 15 ms, ITIC tolerates it.
    assert len(inventory.events) == 1
    event = inventory.events[0]
    assert event.kind.value == "dropout"
    assert event.duration_s == pytest.approx(0.015, rel=1e-2)
    assert event.depth_pct == pytest.approx(99.9, rel=1e-2)
    assert event.verdict.value == "in_tolerance"
    assert event.itic_region.value == "dropout"


@pytest.mark.parametrize(
    ("factor", "duration_s", "expected_verdict"),
    [
        (1.30, 0.10, "out_of_tolerance"),  # >120% уже внутри 0.5 с недопустим
        (1.15, 0.40, "in_tolerance"),  # <=120% в пределах 0.5 с — допускается
        (1.15, 0.60, "out_of_tolerance"),  # за пределом 0.5 с допуск ужесточается до 110%
    ],
)
def test_swell_detected_and_itic_verdict(
    factor: float, duration_s: float, expected_verdict: str
) -> None:
    # Given: a swell plateau whose nominal surroundings stay the strict majority
    # (self-referenced median must sit on the undisturbed level).
    tail_s = max(0.3, duration_s)
    samples = _signal(0.1 + duration_s + tail_s, _stepped(0.1, 0.1 + duration_s, factor))

    # When: detection runs.
    inventory = _inventory(samples)

    # Then: exactly one swell whose verdict follows the encoded ITIC boundary logic.
    assert len(inventory.events) == 1
    event = inventory.events[0]
    assert event.kind.value == "swell"
    assert event.depth_pct == pytest.approx((factor - 1.0) * 100.0, rel=1e-2)
    assert event.verdict.value == expected_verdict
    assert event.itic_region.value == "swell"


def test_rvc_step_detected() -> None:
    # Given: amplitude steps +25% and stays there; pre-step level keeps majority.
    samples = _signal(0.42, _stepped(0.26, 0.42, 1.25))

    # When: detection runs.
    inventory = _inventory(samples)

    # Then: one rapid-voltage-change step, upward, at the switching instant.
    assert len(inventory.rvc_events) == 1
    step = inventory.rvc_events[0]
    assert step.delta_pct == pytest.approx(25.0, rel=1e-2)
    assert step.direction.value == "up"
    assert step.step_time_s == pytest.approx(0.26, rel=1e-2)
    assert step.sustained_cycles >= 1


def test_bounded_chunks_equal_whole_array() -> None:
    # Given: one sagging record analysed twice with different chunk geometries.
    samples = _signal(0.3, _stepped(0.05, 0.15, 0.6))
    settings = power_quality_preset("itic_default")

    # When: bounded 128k-sample chunks versus one giant chunk.
    bounded = detect_power_quality(_series(samples, chunk_samples=131_072), settings=settings)
    whole = detect_power_quality(_series(samples), settings=settings)

    # Then: RMS series and inventory are bit-identical (determinism across chunks).
    bounded_series = _series(samples, chunk_samples=131_072)
    whole_series = _series(samples)
    assert np.array_equal(bounded_series.times_s, whole_series.times_s)
    assert np.array_equal(bounded_series.rms_v, whole_series.rms_v)
    assert bounded.events == whole.events
    assert bounded.rvc_events == whole.rvc_events
    assert bounded.settings_hash == whole.settings_hash


def test_inventory_serialization_round_trip() -> None:
    # Given: an inventory from a record containing a sag.
    samples = _signal(0.3, _stepped(0.05, 0.15, 0.6))

    # When: the inventory is serialised and restored through JSON.
    payload = _inventory(samples).to_dict()
    restored = json.loads(json.dumps(payload, ensure_ascii=False))

    # Then: the payload is JSON-safe and carries schema version plus settings hash.
    assert restored == payload
    assert restored["schema_version"] == 1
    assert isinstance(restored["settings_hash"], str)
    assert len(restored["settings_hash"]) == 64
    assert restored["half_cycle_rms_summary"]["count"] == 30
    assert restored["events"][0]["kind"] == "sag"
