from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import PhaseSettings, ResourceLimits
from lnt.characterization.phase import (
    PhaseCycles,
    compute_phase_cycles,
    compute_phase_means,
    phase_bins,
    phase_residual,
)
from lnt.characterization.records import Status


def _settings(*, bins: int = 64, support: int = 2) -> PhaseSettings:
    return PhaseSettings(
        reference_channel="ch2",
        reference_event="rising_zero_crossing",
        grid_frequency_low_hz=47.5,
        grid_frequency_high_hz=52.5,
        phase_bins=bins,
        minimum_support_per_bin=support,
    )


def _resources(*, chunk: int = 2048, work_bytes: int = 8_000_000) -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=chunk,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=work_bytes,
        max_artifact_bytes=1_000_000,
        max_stored_trajectories=4096,
        max_surrogates=19,
        deterministic_seed=6022,
    )


def _sine(
    rate: float,
    duration_s: float,
    frequency_hz: float = 50.0,
    shift_samples: float = 0.0,
) -> np.ndarray:
    time_s = np.arange(round(rate * duration_s), dtype=np.float64) / rate
    return np.sin(2.0 * np.pi * frequency_hz * (time_s - shift_samples / rate)).astype(np.float32)


def _cycles(
    starts: list[float], ends: list[float], valid: list[bool], sample_count: int
) -> PhaseCycles:
    return PhaseCycles(
        sample_rate_hz=3200.0,
        sample_count=sample_count,
        cycle_start_samples=np.array(starts, dtype=np.float64),
        cycle_end_samples=np.array(ends, dtype=np.float64),
        cycle_valid=np.array(valid, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def test_full_record_phase_keeps_fractional_interior_cycles_beyond_capture_minimum() -> None:
    rate = 3200.0
    samples = _sine(rate, 6.0, shift_samples=0.25)
    original = samples.copy()

    phase = compute_phase_cycles(
        samples, sample_rate_hz=rate, settings=_settings(), resources=_resources()
    )

    assert phase.status is Status.AVAILABLE
    assert phase.reason_code is None
    assert np.count_nonzero(phase.cycle_valid) >= 200
    assert phase.cycle_end_samples[phase.cycle_valid][-1] > 4.0 * rate
    assert np.allclose(np.diff(phase.cycle_start_samples[phase.cycle_valid]), 64.0, atol=1e-3)
    assert phase.cycle_start_samples[phase.cycle_valid][0] % 64.0 == pytest.approx(0.25, abs=1e-3)
    assert np.array_equal(samples, original)
    repeated = compute_phase_cycles(
        samples, sample_rate_hz=rate, settings=_settings(), resources=_resources()
    )
    assert np.array_equal(phase.cycle_start_samples, repeated.cycle_start_samples)
    assert np.array_equal(phase.cycle_valid, repeated.cycle_valid)


def test_fractional_cycle_bins_are_left_closed_and_consistent_at_16_and_64() -> None:
    phase = _cycles([0.25], [20.25], [True], 22)

    bins64, valid64 = phase_bins(phase, 0, 22, 64)
    bins16, valid16 = phase_bins(phase, 0, 22, 16)

    expected_valid = np.arange(22) >= 1
    expected_valid[-1] = False
    assert np.array_equal(valid64, expected_valid)
    assert np.array_equal(valid16, expected_valid)
    positions = np.arange(1, 21, dtype=np.float64)
    assert np.array_equal(bins64[1:21], np.floor((positions - 0.25) / 20.0 * 64).astype(np.int64))
    assert np.array_equal(bins16[valid16], bins64[valid64] // 4)
    assert np.all(bins64[~valid64] == 0)


def test_phase_means_and_residual_use_native_piecewise_voltage() -> None:
    phase = _cycles([0.0, 64.0], [64.0, 128.0], [True, True], 128)
    truth_v = np.arange(64, dtype=np.float64) / 8.0 - 4.0
    samples = np.tile(truth_v, 2).astype(np.float32)

    means = compute_phase_means(
        samples, phase, settings=_settings(support=2), resources=_resources()
    )
    residual_v, valid = phase_residual(samples, phase, means, 0, 128)

    assert means.status is Status.AVAILABLE
    assert means.reason_code is None
    assert np.array_equal(means.counts, np.full(64, 2, dtype=np.int64))
    assert np.all(means.valid_bins)
    assert np.allclose(means.means_v, truth_v)
    assert np.all(valid)
    assert np.array_equal(residual_v, np.zeros(128, dtype=np.float64))


def test_missing_reference_and_out_of_band_cycles_are_explicitly_unavailable() -> None:
    missing = compute_phase_cycles(
        None, sample_rate_hz=3200.0, settings=_settings(), resources=_resources()
    )
    assert missing.status is Status.UNAVAILABLE
    assert missing.reason_code == "no_sync_reference"
    assert missing.cycle_start_samples.size == 0

    for frequency_hz in (45.0, 60.0):
        phase = compute_phase_cycles(
            _sine(3200.0, 1.0, frequency_hz),
            sample_rate_hz=3200.0,
            settings=_settings(),
            resources=_resources(),
        )
        assert phase.status is Status.UNAVAILABLE
        assert phase.reason_code == "grid_unstable"
        assert phase.cycle_valid.size > 0
        assert not np.any(phase.cycle_valid)


def test_means_report_insufficient_phase_support_with_finite_masked_values() -> None:
    phase = _cycles([0.0], [64.0], [True], 64)
    means = compute_phase_means(
        np.ones(64, dtype=np.float64),
        phase,
        settings=_settings(support=2),
        resources=_resources(),
    )

    assert means.status is Status.UNAVAILABLE
    assert means.reason_code == "insuff_phase_support"
    assert np.array_equal(means.counts, np.ones(64, dtype=np.int64))
    assert not np.any(means.valid_bins)
    assert np.array_equal(means.means_v, np.zeros(64, dtype=np.float64))


def test_nonfinite_gap_separates_supported_cycles() -> None:
    rate = 3200.0
    samples = _sine(rate, 2.0).astype(np.float64)
    gap_start, gap_stop = 2400, 4000
    samples[gap_start:gap_stop] = np.nan

    phase = compute_phase_cycles(
        samples, sample_rate_hz=rate, settings=_settings(), resources=_resources(chunk=512)
    )

    assert phase.status is Status.PARTIAL
    assert phase.reason_code == "insufficient_phase_support"
    assert np.any(phase.cycle_valid)
    assert not np.any(
        (phase.cycle_start_samples < gap_start) & (phase.cycle_end_samples > gap_stop)
    )
    _, gap_valid = phase_bins(phase, gap_start, gap_stop, 64)
    assert not np.any(gap_valid)


def test_callbacks_propagate_and_high_rate_or_tiny_budget_fail_closed() -> None:
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        compute_phase_cycles(
            _sine(3200.0, 1.0),
            sample_rate_hz=3200.0,
            settings=_settings(),
            resources=_resources(),
            checkpoint=cancel,
        )
    assert caught.value is error

    phase = _cycles([0.0], [64.0], [True], 64)
    with pytest.raises(RuntimeError) as means_caught:
        compute_phase_means(
            np.ones(64, dtype=np.float32),
            phase,
            settings=_settings(),
            resources=_resources(),
            checkpoint=cancel,
        )
    assert means_caught.value is error

    refused = compute_phase_cycles(
        np.zeros(100, dtype=np.float32),
        sample_rate_hz=1e12,
        settings=_settings(),
        resources=_resources(),
    )
    assert refused.status is Status.UNAVAILABLE
    assert refused.reason_code == "phase_reference_unavailable"

    tiny = compute_phase_cycles(
        _sine(3200.0, 1.0),
        sample_rate_hz=3200.0,
        settings=_settings(),
        resources=replace(_resources(), max_work_bytes=8),
    )
    assert tiny.status is Status.UNAVAILABLE
    assert "work_budget" in str(tiny.reason_code)
