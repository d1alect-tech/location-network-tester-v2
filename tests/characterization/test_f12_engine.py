"""Публичные status/QC/determinism tests движка F12."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.clipping import ClippingBounds
from lnt.characterization.f12_contract import (
    CLIPPED,
    INSUFFICIENT_FRAMES,
    NO_SIGNIFICANT_BIN,
    PHASE_REFERENCE_UNAVAILABLE,
    SCALE_UNSUPPORTED,
    ZERO_POWER,
)
from lnt.characterization.f12_engine import compute_f12_spectral_kurtosis
from lnt.characterization.f12_result import F12Declarations
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status

_FS_HZ = 10_000.0


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=4096,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=64_000_000,
        max_artifact_bytes=1_000_000,
        max_stored_trajectories=4096,
        max_surrogates=199,
        deterministic_seed=6022,
    )


def _phase(sample_count: int, sample_rate_hz: float = _FS_HZ) -> PhaseCycles:
    edges = np.arange(0, sample_count + 1, sample_rate_hz / 50.0, dtype=np.float64)
    if int(edges[-1]) != sample_count:
        edges = np.append(edges, sample_count)
    return PhaseCycles(
        sample_rate_hz=sample_rate_hz,
        sample_count=sample_count,
        cycle_start_samples=edges[:-1],
        cycle_end_samples=edges[1:],
        cycle_valid=np.ones(edges.size - 1, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _means() -> PhaseMeans:
    return PhaseMeans(
        means_v=np.zeros(64, dtype=np.float64),
        counts=np.full(64, 100, dtype=np.int64),
        valid_bins=np.ones(64, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )


def _unclipped() -> ClippingBounds:
    return ClippingBounds(
        low_v=-10.0,
        high_v=10.0,
        reason_code=None,
        telemetry_rail_count=0,
    )


def test_unavailable_phase_normalizes_and_keeps_empty_domains() -> None:
    """Upstream phase refusal возвращает F12 status, а не zero или raw code."""
    sample_count = 10_000
    phase = replace(
        _phase(sample_count), status=Status.UNAVAILABLE, reason_code="no_sync_reference"
    )

    result = compute_f12_spectral_kurtosis(
        np.ones(sample_count, dtype=np.float64),
        phase,
        _means(),
        _unclipped(),
        F12Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (PHASE_REFERENCE_UNAVAILABLE,)
    assert result.segment_samples.size == 0
    assert result.frequencies_hz.size == 0
    assert result.spectral_kurtosis.size == 0
    assert result.adjusted_p_value.size == 0
    assert result.qualified_sample_count == 0
    assert result.surrogate_count == 0


def test_clipped_and_unknown_clipping_reject_before_measurement() -> None:
    """Hardware hit и unlocalized clipping оба refuse, не создавая SK axes."""
    sample_count = 10_000
    time_s = np.arange(sample_count, dtype=np.float64) / _FS_HZ
    samples = np.sin(2.0 * np.pi * 1000.0 * time_s)
    clipped = ClippingBounds(
        low_v=0.5,
        high_v=2.0,
        reason_code=None,
        telemetry_rail_count=1,
    )
    unknown = ClippingBounds(
        low_v=None,
        high_v=None,
        reason_code="clipping_localization_unavailable",
        telemetry_rail_count=None,
    )

    for bounds in (clipped, unknown):
        result = compute_f12_spectral_kurtosis(
            samples,
            _phase(sample_count),
            _means(),
            bounds,
            F12Declarations.locked(),
            _resources(),
        )
        assert result.status is Status.UNAVAILABLE
        assert result.reason_codes == (CLIPPED,)
        assert result.spectral_kurtosis.size == 0
        assert result.qualified_sample_count == 0


def test_zero_phase_residual_second_moment_is_unavailable() -> None:
    """Нулевой residual power не превращается в zero SK или p-value."""
    sample_count = 10_000

    result = compute_f12_spectral_kurtosis(
        np.ones(sample_count, dtype=np.float64),
        _phase(sample_count),
        replace(_means(), means_v=np.ones(64, dtype=np.float64)),
        _unclipped(),
        F12Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (ZERO_POWER,)
    assert result.spectral_kurtosis.size == 0
    assert result.qualified_sample_count == 0


def test_partial_scale_support_is_partial_without_claiming_missing_scales() -> None:
    """L=256 измеряется, L=1024 имеет 31 frames, старшие scales unavailable."""
    sample_count = 10_000
    indices = np.arange(sample_count, dtype=np.int64)
    time_s = indices.astype(np.float64) / _FS_HZ
    samples = ((indices % 512) < 32).astype(np.float64) * np.sin(2.0 * np.pi * 3500.0 * time_s)

    result = compute_f12_spectral_kurtosis(
        samples,
        _phase(sample_count),
        _means(),
        _unclipped(),
        F12Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.PARTIAL
    assert INSUFFICIENT_FRAMES in result.reason_codes
    assert SCALE_UNSUPPORTED in result.reason_codes
    # N=10000 gives 77 complete L=256 frames, 18 L=1024, 3 L=4096, and no L=16384 frame.
    assert result.frame_count.tolist() == [77, 18, 3, 0]
    assert result.scale_available.tolist() == [True, False, False, False]
    assert result.analyzed_scale_count == 1
    assert result.surrogate_count == 199


def test_short_record_reports_declared_scale_support_codes() -> None:
    """31-or-fewer frames не подменяются: каждый scale получает свой declared code."""
    sample_count = 1000
    time_s = np.arange(sample_count, dtype=np.float64) / _FS_HZ

    result = compute_f12_spectral_kurtosis(
        np.sin(2.0 * np.pi * 3500.0 * time_s),
        _phase(sample_count),
        _means(),
        _unclipped(),
        F12Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.UNAVAILABLE
    assert result.reason_codes == (INSUFFICIENT_FRAMES, SCALE_UNSUPPORTED)
    assert result.segment_samples.size == 0
    assert result.frame_count.size == 0
    assert result.candidate_count == 0


def test_periodic_band_limited_impulses_recover_significant_scale_band_and_are_deterministic() -> (
    None
):
    """270336 samples gives exactly 32 frames at L=16384; repeated F12 runs are bit-identical."""
    sample_count = 270_336
    indices = np.arange(sample_count, dtype=np.int64)
    sample_rate_hz = 6680.0
    time_s = indices.astype(np.float64) / sample_rate_hz
    samples = ((indices % 4096) < 128).astype(np.float64) * np.sin(
        2.0 * np.pi * 3000.78125 * time_s
    )
    phase = _phase(sample_count, sample_rate_hz)
    means = _means()
    clipping = _unclipped()
    declarations = F12Declarations.locked()
    resources = _resources()

    first = compute_f12_spectral_kurtosis(samples, phase, means, clipping, declarations, resources)
    second = compute_f12_spectral_kurtosis(samples, phase, means, clipping, declarations, resources)

    assert first.status in {Status.AVAILABLE, Status.PARTIAL}
    assert NO_SIGNIFICANT_BIN not in first.reason_codes
    # hop=128,512,2048,8192; 1+(N-L)//hop gives these exact complete-frame counts.
    assert first.frame_count.tolist() == [2111, 527, 131, 32]
    assert first.stored_significant_bin_count > 0
    assert first.selected_scale_index is not None
    assert first.selected_band_low_hz is not None
    assert first.selected_band_high_hz is not None
    assert first.selected_band_low_hz == pytest.approx(3000.78125)
    assert first.selected_band_high_hz == pytest.approx(3000.78125)
    assert first.maximum_spectral_kurtosis is not None
    assert first.maximum_spectral_kurtosis > 0.0
    np.testing.assert_array_equal(first.frequencies_hz, second.frequencies_hz)
    np.testing.assert_array_equal(first.spectral_kurtosis, second.spectral_kurtosis)
    np.testing.assert_array_equal(first.adjusted_p_value, second.adjusted_p_value)
    np.testing.assert_array_equal(first.frame_count, second.frame_count)
    np.testing.assert_array_equal(first.scale_available, second.scale_available)
    assert first.reason_codes == second.reason_codes
    assert first.maximum_spectral_kurtosis == second.maximum_spectral_kurtosis
    assert first.selected_scale_index == second.selected_scale_index
    assert first.selected_band_low_hz == second.selected_band_low_hz
    assert first.selected_band_high_hz == second.selected_band_high_hz
    assert first.candidate_count == second.candidate_count
    assert first.significant_bin_count == second.significant_bin_count
    assert first.stored_significant_bin_count == second.stored_significant_bin_count


def test_seeded_gaussian_realization_has_no_significant_bin() -> None:
    """Stationary Gaussian control при fixed seed не получает significant F12 bin."""
    sample_count = 270_336
    sample_rate_hz = 6680.0
    samples = np.random.default_rng(6022).normal(0.0, 1.0, sample_count)

    result = compute_f12_spectral_kurtosis(
        samples,
        _phase(sample_count, sample_rate_hz),
        _means(),
        _unclipped(),
        F12Declarations.locked(),
        _resources(),
    )

    assert result.status is Status.PARTIAL
    assert result.reason_codes == (NO_SIGNIFICANT_BIN,)
    assert result.candidate_count > 0
    assert result.significant_bin_count == 0
    assert result.spectral_kurtosis.size == 0


def test_checkpoint_cancellation_propagates_by_identity() -> None:
    """Cancellation между bounded passes не превращается в F12 reason code."""
    error = RuntimeError("cancel")
    calls = 0

    def checkpoint() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise error

    with pytest.raises(RuntimeError) as raised:
        compute_f12_spectral_kurtosis(
            np.sin(np.arange(10_000, dtype=np.float64) / 10_000.0),
            _phase(10_000),
            _means(),
            _unclipped(),
            F12Declarations.locked(),
            _resources(),
            checkpoint=checkpoint,
        )

    assert raised.value is error
