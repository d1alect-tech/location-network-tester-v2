"""Измерение locked F12 support на реалистичной synthetic сетке."""

from __future__ import annotations

import numpy as np

from lnt.analysis_store.characterization_settings import ResourceLimits
from lnt.characterization.f12_candidates import observed_candidates
from lnt.characterization.f12_result import F12Declarations
from lnt.characterization.f12_scales import observe_scale
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status

_FS_HZ = 10_000.0
_SAMPLE_COUNT = 270_336


def _resources() -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=4096,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=268_435_456,
        max_artifact_bytes=67_108_864,
        max_stored_trajectories=4096,
        max_surrogates=199,
        deterministic_seed=6022,
    )


def _phase() -> PhaseCycles:
    edges = np.arange(0, _SAMPLE_COUNT + 1, _FS_HZ / 50.0, dtype=np.float64)
    if int(edges[-1]) != _SAMPLE_COUNT:
        edges = np.append(edges, _SAMPLE_COUNT)
    return PhaseCycles(
        sample_rate_hz=_FS_HZ,
        sample_count=_SAMPLE_COUNT,
        cycle_start_samples=edges[:-1],
        cycle_end_samples=edges[1:],
        cycle_valid=np.ones(edges.size - 1, dtype=np.bool_),
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


def test_realistic_fixture_reaches_all_locked_scales_and_records_band_grid() -> None:
    """10 kHz / 5.63 s fixture: 32 large frames, 3264 positive-power candidates.

    SPEC-GAP F12-12: the fixed 199-surrogate add-one p floor was measured against
    this family-wide grid; locked q=0.05 was not retuned when the measured
    realization produced no significant bin.
    """
    indices = np.arange(_SAMPLE_COUNT, dtype=np.int64)
    time_s = indices.astype(np.float64) / _FS_HZ
    samples = ((indices % 4096) < 128).astype(np.float64) * np.sin(2.0 * np.pi * 3500.0 * time_s)
    declarations = F12Declarations.locked()
    scales = tuple(
        observe_scale(
            samples,
            _phase(),
            _means(),
            segment_samples=segment,
            declarations=declarations,
            resources=_resources(),
        )
        for segment in declarations.segment_samples
    )
    candidates = observed_candidates(scales)

    assert [scale.frame_count for scale in scales] == [2111, 527, 131, 32]
    assert [scale.frequencies_hz.size for scale in scales] == [39, 153, 615, 2457]
    assert candidates.spectral_kurtosis.size == 3264
    assert np.all(np.isfinite(candidates.spectral_kurtosis))
    assert float(np.max(candidates.spectral_kurtosis)) > 0.0
