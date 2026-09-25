"""Тесты shared-STFT scale pass F12."""

from __future__ import annotations

import numpy as np

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.f12_contract import INSUFFICIENT_FRAMES, SCALE_UNSUPPORTED
from lnt.characterization.f12_result import F12Declarations
from lnt.characterization.f12_scales import observe_scale
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status

_FS_HZ = 10_000.0


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=4096,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=32_000_000,
        max_artifact_bytes=1_000_000,
        max_stored_trajectories=4096,
        max_surrogates=199,
        deterministic_seed=6022,
    )


def _phase(sample_count: int) -> PhaseCycles:
    edges = np.arange(0, sample_count + 1, 200, dtype=np.float64)
    if int(edges[-1]) != sample_count:
        edges = np.append(edges, sample_count)
    return PhaseCycles(
        sample_rate_hz=_FS_HZ,
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


def _samples(sample_count: int) -> np.ndarray:
    time_s = np.arange(sample_count, dtype=np.float64) / _FS_HZ
    return np.sin(2.0 * np.pi * 3125.0 * time_s) + 0.4 * np.sin(2.0 * np.pi * 4375.0 * time_s + 0.2)


def test_exact_frame_boundary_uses_locked_minimum() -> None:
    """При L=256 и hop=128 ровно 32 frames доступны, 31 дают insuffiency."""
    declarations = F12Declarations.locked()
    supported = observe_scale(
        _samples(4224),
        _phase(4224),
        _means(),
        segment_samples=256,
        declarations=declarations,
        resources=_resources(),
    )
    sparse = observe_scale(
        _samples(4223),
        _phase(4223),
        _means(),
        segment_samples=256,
        declarations=declarations,
        resources=_resources(),
    )

    assert supported.frame_count == 32
    assert supported.reason_code is None
    # 10 kHz / 256 = 39.0625 Hz; effective high=min(200 kHz, 0.45*10 kHz)=4.5 kHz.
    # Полоса содержит bins 77..115 включительно, точно 39 положительных grid points.
    assert supported.frequencies_hz.size == 39
    assert supported.frequencies_hz[[0, -1]].tolist() == [3007.8125, 4492.1875]
    assert np.all(np.isfinite(supported.spectral_kurtosis))
    assert sparse.frame_count == 31
    assert sparse.reason_code == INSUFFICIENT_FRAMES
    assert sparse.spectral_kurtosis.size == 0


def test_segment_longer_than_record_is_scale_unsupported() -> None:
    """Segment longer than available support is unsupported, not a zero-frame measurement."""
    declarations = F12Declarations.locked()
    result = observe_scale(
        _samples(255),
        _phase(255),
        _means(),
        segment_samples=256,
        declarations=declarations,
        resources=_resources(),
    )

    assert result.frame_count == 0
    assert result.reason_code == SCALE_UNSUPPORTED
