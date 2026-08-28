"""Bounded-memory contracts for band spectrum routing and artifact digests.

``compute_band_spectrum`` must route through ``lnt.psd.compute_welch`` while
keeping numerical agreement with a direct ``scipy.signal.welch`` reference at
``rtol=2e-6, atol=1e-15`` (the engine's validated SciPy-equivalence tolerance),
and the orchestrator must hash channel artifacts with a streaming digest whose
hex value equals ``hashlib.sha256(path.read_bytes()).hexdigest()``.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np
from scipy import signal

from lnt.analysis_store import AnalysisRecipe, ArtifactInputs, CodeIdentity, NamedDigest
from lnt.analysis_v2.orchestrator import (
    _artifact_inputs,  # pyright: ignore[reportPrivateUsage]
    _sha256_file,  # pyright: ignore[reportPrivateUsage]
)
from lnt.spectrum import compute_band_spectrum

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE_RATE_HZ = 48_000.0


def _recipe() -> AnalysisRecipe:
    return AnalysisRecipe.from_mapping(
        {
            "schema_version": 1,
            "mode": "standard",
            "channels": ["ch1", "ch2"],
            "band_grid": {"low_hz": 10.0, "high_hz": 400.0, "grid_hz": 1.0},
            "welch": {
                "window": "hann_periodic",
                "segment_samples": 64,
                "overlap_fraction": 0.5,
                "detrend": "constant",
                "scaling": "density",
                "average": "mean",
            },
            "spectrogram": {"enabled": True, "segment_samples": 64, "overlap_fraction": 0.5},
            "events": {"enabled": True, "threshold_sigma": 5.0},
            "bands": {"edges_hz": [10.0, 100.0, 400.0]},
            "correction": {"method": "none"},
            "uncertainty": {"enabled": False, "confidence_level": 0.95, "bootstrap_samples": 0},
        }
    )


def _reference_nperseg(sample_count: int, sample_rate_hz: float) -> int:
    """Replicates the documented 50 Hz-resolution power-of-two segment choice."""
    target = sample_rate_hz / 50.0
    power = int(np.floor(np.log2(max(target, 1_024))))
    nperseg = 2**power
    while nperseg > sample_count:
        nperseg //= 2
    return max(nperseg, 1_024)


def test_band_spectrum_matches_scipy_reference_within_tolerance() -> None:
    # Given: a multi-chunk medium record with a dominant tone plus noise
    rng = np.random.default_rng(20260826)
    sample_count = 1_200_000
    time_s = np.arange(sample_count, dtype=np.float64) / SAMPLE_RATE_HZ
    samples = (
        0.05 * rng.normal(0.0, 1.0, sample_count) + 0.3 * np.sin(2 * np.pi * 10_000.0 * time_s)
    ).astype(np.float32)

    # When: the band spectrum is computed against a direct scipy Welch reference
    spectrum = compute_band_spectrum(samples, sample_rate_hz=SAMPLE_RATE_HZ)
    nperseg = _reference_nperseg(samples.size, SAMPLE_RATE_HZ)
    expected_freqs, expected_psd = signal.welch(
        samples.astype(np.float64), fs=SAMPLE_RATE_HZ, nperseg=nperseg
    )
    effective_high = min(3_000_000.0, 0.45 * SAMPLE_RATE_HZ)
    mask = (expected_freqs >= 3_000.0) & (expected_freqs <= effective_high)

    # Then
    np.testing.assert_array_equal(spectrum.frequencies_hz, expected_freqs[mask])
    np.testing.assert_allclose(spectrum.psd_v2_per_hz, expected_psd[mask], rtol=2e-6, atol=1e-15)
    assert spectrum.resolution_hz == SAMPLE_RATE_HZ / nperseg
    assert spectrum.band_low_hz == 3_000.0
    assert spectrum.band_high_hz == effective_high


def test_band_spectrum_accepts_memmap_input(tmp_path: Path) -> None:
    # Given: the same record addressable as a read-only memmap and in memory
    rng = np.random.default_rng(77)
    sample_count = 16_384
    time_s = np.arange(sample_count, dtype=np.float64) / SAMPLE_RATE_HZ
    samples = (
        0.05 * rng.normal(0.0, 1.0, sample_count) + 0.3 * np.sin(2 * np.pi * 10_000.0 * time_s)
    ).astype(np.float32)
    path = tmp_path / "ch1.npy"
    np.save(path, samples)
    memmap_samples = np.load(path, mmap_mode="r")

    # When: the spectrum is computed from the memmap view
    from_memmap = compute_band_spectrum(memmap_samples, sample_rate_hz=SAMPLE_RATE_HZ)
    from_memory = compute_band_spectrum(np.asarray(memmap_samples), sample_rate_hz=SAMPLE_RATE_HZ)

    # Then
    np.testing.assert_array_equal(from_memmap.frequencies_hz, from_memory.frequencies_hz)
    np.testing.assert_allclose(
        from_memmap.psd_v2_per_hz, from_memory.psd_v2_per_hz, rtol=2e-6, atol=1e-15
    )
    assert len(from_memmap.peaks) == len(from_memory.peaks)


def test_artifact_digest_unchanged_vs_read_bytes(tmp_path: Path) -> None:
    # Given: a multi-megabyte artifact whose bytes span several 1 MiB chunks
    payload = np.random.default_rng(7).normal(0.0, 0.2, 900_000).astype(np.float32)
    path = tmp_path / "ch1.npy"
    np.save(path, payload)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    # When
    digest = _sha256_file(path)

    # Then
    assert digest == expected


def test_orchestrator_inputs_use_streaming_digest(tmp_path: Path) -> None:
    # Given: a small two-channel session and directly computed expected inputs
    session = tmp_path / "measurement"
    session.mkdir()
    np.save(session / "ch1.npy", np.linspace(-1, 1, 4096, dtype=np.float32))
    np.save(session / "ch2.npy", np.linspace(1, -1, 4096, dtype=np.float32))
    recipe = _recipe()
    paths = (session / "ch1.npy", session / "ch2.npy")
    identity = CodeIdentity(lnt="test", numpy=np.__version__, scipy="test")
    expected = ArtifactInputs(
        recipe_sha256=recipe.recipe_sha256,
        raw_inputs=tuple(
            NamedDigest(name=path.name, digest=hashlib.sha256(path.read_bytes()).hexdigest())
            for path in paths
        ),
        context_dependencies=(),
        profile_dependencies=(),
        calibration_dependencies=(),
        code_identity=identity,
    )

    # When
    actual = _artifact_inputs(recipe, paths, identity)

    # Then
    assert actual == expected
    assert actual.artifact_key == expected.artifact_key
