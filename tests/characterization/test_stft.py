from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest
from scipy import signal

from lnt.analysis_store.characterization_settings import (
    PhaseSettings,
    ResourceLimits,
    StftSettings,
)
from lnt.characterization.phase import (
    PhaseCycles,
    PhaseMeans,
    compute_phase_cycles,
    compute_phase_means,
    phase_residual,
)
from lnt.characterization.stft import ResidualStftChunk, stream_phase_residual_stft
from lnt.errors import InputError

if TYPE_CHECKING:
    from numpy.typing import NDArray


_RATE_HZ = 6400.0


def _phase_settings() -> PhaseSettings:
    return PhaseSettings(
        reference_channel="ch2",
        reference_event="rising_zero_crossing",
        grid_frequency_low_hz=47.5,
        grid_frequency_high_hz=52.5,
        phase_bins=64,
        minimum_support_per_bin=10,
    )


def _stft_settings() -> StftSettings:
    return StftSettings(
        window="hann_periodic",
        segment_samples=256,
        overlap_fraction=0.75,
        detrend="constant",
        analysis_low_hz=3000.0,
        analysis_high_hz=3100.0,
        nyquist_fraction_max=0.49,
    )


def _resources(*, chunk: int = 4096, work_bytes: int = 32_000_000) -> ResourceLimits:
    return ResourceLimits(
        chunk_samples=chunk,
        hard_max_chunk_samples=1_048_576,
        max_work_bytes=work_bytes,
        max_artifact_bytes=1_000_000,
        max_stored_trajectories=4096,
        max_surrogates=19,
        deterministic_seed=6022,
    )


def _signals(duration_s: float = 4.0) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    time_s = np.arange(round(_RATE_HZ * duration_s), dtype=np.float64) / _RATE_HZ
    ch2 = np.sin(2.0 * np.pi * 50.0 * time_s)
    ch1 = 2.0 * ch2 + 1.5 * np.cos(2.0 * np.pi * 3025.0 * time_s + 0.3)
    return ch1, ch2


def _phase_and_means(
    samples: NDArray[np.float64], ch2: NDArray[np.float64]
) -> tuple[PhaseCycles, PhaseMeans]:
    resources = _resources()
    phase = compute_phase_cycles(
        ch2,
        sample_rate_hz=_RATE_HZ,
        settings=_phase_settings(),
        resources=resources,
    )
    means = compute_phase_means(
        samples,
        phase,
        settings=_phase_settings(),
        resources=resources,
    )
    assert np.any(means.valid_bins)
    return phase, means


def _collect(chunks: list[ResidualStftChunk]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.concatenate([chunk.frame_indices for chunk in chunks]),
        np.concatenate([chunk.time_s for chunk in chunks]),
        np.concatenate([chunk.coefficients for chunk in chunks], axis=1),
    )


def _qualified_frames(valid: NDArray[np.bool_], length: int, hop: int) -> NDArray[np.int64]:
    count = 0 if valid.size < length else 1 + (valid.size - length) // hop
    return np.array(
        [index for index in range(count) if np.all(valid[index * hop : index * hop + length])],
        dtype=np.int64,
    )


def test_residual_stft_removes_phase_mean_and_keeps_carrier_amplitude() -> None:
    samples, ch2 = _signals()
    original = samples.copy()
    phase, means = _phase_and_means(samples, ch2)

    chunks = list(
        stream_phase_residual_stft(
            samples,
            phase,
            means,
            sample_rate_hz=_RATE_HZ,
            settings=_stft_settings(),
            resources=_resources(),
        )
    )
    frame_indices, time_s, coefficients = _collect(chunks)

    assert all(chunk.valid_frames.all() for chunk in chunks)
    assert all(chunk.coefficients.dtype == np.complex128 for chunk in chunks)
    assert all(chunk.coefficients.shape[1] <= 256 for chunk in chunks)
    np.testing.assert_array_equal(samples, original)
    np.testing.assert_array_equal(time_s, (frame_indices * 64 + 128) / _RATE_HZ)
    frequency_index = int(np.flatnonzero(chunks[0].frequencies_hz == 3025.0)[0])
    np.testing.assert_allclose(np.abs(coefficients[frequency_index]), 0.75, atol=2e-3)


def test_complete_qualified_grid_matches_scipy_without_doubling() -> None:
    samples, ch2 = _signals()
    phase, means = _phase_and_means(samples, ch2)
    settings = _stft_settings()
    residual, valid = phase_residual(samples, phase, means, 0, samples.size)
    expected_frames = _qualified_frames(valid, settings.segment_samples, 64)
    scipy_stft = vars(signal)["stft"]
    scipy_frequencies, _, scipy_coefficients = scipy_stft(
        residual,
        fs=_RATE_HZ,
        window="hann",
        nperseg=settings.segment_samples,
        noverlap=settings.segment_samples - 64,
        detrend="constant",
        boundary=None,
        padded=False,
        return_onesided=True,
        scaling="spectrum",
    )
    frequency_mask = (
        (scipy_frequencies >= settings.analysis_low_hz)
        & (scipy_frequencies <= settings.analysis_high_hz)
        & (scipy_frequencies > 0.0)
    )

    chunks = list(
        stream_phase_residual_stft(
            samples,
            phase,
            means,
            sample_rate_hz=_RATE_HZ,
            settings=settings,
            resources=_resources(),
        )
    )
    frame_indices, _, coefficients = _collect(chunks)

    np.testing.assert_array_equal(frame_indices, expected_frames)
    np.testing.assert_array_equal(chunks[0].frequencies_hz, scipy_frequencies[frequency_mask])
    np.testing.assert_allclose(
        coefficients,
        scipy_coefficients[frequency_mask][:, expected_frames],
        rtol=2e-14,
        atol=2e-14,
    )


def test_gap_omits_every_overlapping_frame_without_shifting_later_indices() -> None:
    samples, ch2 = _signals()
    phase, means = _phase_and_means(samples, ch2)
    samples[12_000:12_100] = np.nan
    _, valid = phase_residual(samples, phase, means, 0, samples.size)
    expected = _qualified_frames(valid, 256, 64)

    chunks = list(
        stream_phase_residual_stft(
            samples,
            phase,
            means,
            sample_rate_hz=_RATE_HZ,
            settings=_stft_settings(),
            resources=_resources(chunk=1024),
        )
    )
    frame_indices, _, coefficients = _collect(chunks)

    np.testing.assert_array_equal(frame_indices, expected)
    assert not np.any((frame_indices * 64 < 12_100) & (frame_indices * 64 + 256 > 12_000))
    assert np.all(np.isfinite(coefficients))
    assert np.any(frame_indices * 64 >= 12_100)


def test_processing_bounds_do_not_change_global_residual_frames() -> None:
    samples, ch2 = _signals()
    phase, means = _phase_and_means(samples, ch2)

    outputs = []
    for chunk_samples in (256, 777, 8192):
        chunks = list(
            stream_phase_residual_stft(
                samples,
                phase,
                means,
                sample_rate_hz=_RATE_HZ,
                settings=_stft_settings(),
                resources=_resources(chunk=chunk_samples),
            )
        )
        outputs.append(_collect(chunks))

    for actual, expected in zip(outputs[1:], outputs[:-1], strict=True):
        for actual_array, expected_array in zip(actual, expected, strict=True):
            np.testing.assert_allclose(actual_array, expected_array, rtol=0.0, atol=1e-14)
    repeated = _collect(
        list(
            stream_phase_residual_stft(
                samples,
                phase,
                means,
                sample_rate_hz=_RATE_HZ,
                settings=_stft_settings(),
                resources=_resources(chunk=777),
            )
        )
    )
    for actual_array, expected_array in zip(repeated, outputs[1], strict=True):
        np.testing.assert_array_equal(actual_array, expected_array)


def test_segment_override_recomputes_hop_frequency_grid_and_centres() -> None:
    samples, ch2 = _signals()
    phase, means = _phase_and_means(samples, ch2)

    chunks = list(
        stream_phase_residual_stft(
            samples,
            phase,
            means,
            sample_rate_hz=_RATE_HZ,
            settings=_stft_settings(),
            resources=_resources(),
            segment_samples=128,
        )
    )
    frame_indices, time_s, _ = _collect(chunks)

    np.testing.assert_array_equal(time_s, (frame_indices * 32 + 64) / _RATE_HZ)
    np.testing.assert_array_equal(chunks[0].frequencies_hz, np.array([3000.0, 3050.0, 3100.0]))


def test_unsupported_phase_short_record_and_empty_band_emit_no_spectra() -> None:
    samples, ch2 = _signals(0.01)
    phase = compute_phase_cycles(
        ch2,
        sample_rate_hz=_RATE_HZ,
        settings=_phase_settings(),
        resources=_resources(),
    )
    means = compute_phase_means(
        samples,
        phase,
        settings=_phase_settings(),
        resources=_resources(),
    )
    assert phase.reason_code is not None
    assert not list(
        stream_phase_residual_stft(
            samples,
            phase,
            means,
            sample_rate_hz=_RATE_HZ,
            settings=_stft_settings(),
            resources=_resources(),
        )
    )

    full_samples, full_ch2 = _signals()
    full_phase, full_means = _phase_and_means(full_samples, full_ch2)
    empty_band = replace(_stft_settings(), analysis_low_hz=4000.0, analysis_high_hz=5000.0)
    assert not list(
        stream_phase_residual_stft(
            full_samples,
            full_phase,
            full_means,
            sample_rate_hz=_RATE_HZ,
            settings=empty_band,
            resources=_resources(),
        )
    )


def test_work_limits_and_checkpoint_fail_before_transform() -> None:
    samples, ch2 = _signals()
    phase, means = _phase_and_means(samples, ch2)
    with pytest.raises(InputError, match="work"):
        list(
            stream_phase_residual_stft(
                samples,
                phase,
                means,
                sample_rate_hz=_RATE_HZ,
                settings=_stft_settings(),
                resources=_resources(work_bytes=64),
            )
        )
    with pytest.raises(InputError, match="segment_samples"):
        list(
            stream_phase_residual_stft(
                samples,
                phase,
                means,
                sample_rate_hz=_RATE_HZ,
                settings=_stft_settings(),
                resources=replace(_resources(), hard_max_chunk_samples=128, chunk_samples=128),
            )
        )

    error = RuntimeError("cancel")

    def checkpoint() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        list(
            stream_phase_residual_stft(
                samples,
                phase,
                means,
                sample_rate_hz=_RATE_HZ,
                settings=_stft_settings(),
                resources=_resources(),
                checkpoint=checkpoint,
            )
        )
    assert caught.value is error

    cancel_enabled = False

    def cancel_after_first_chunk() -> None:
        if cancel_enabled:
            raise error

    chunks = stream_phase_residual_stft(
        samples,
        phase,
        means,
        sample_rate_hz=_RATE_HZ,
        settings=_stft_settings(),
        resources=_resources(chunk=4096),
        checkpoint=cancel_after_first_chunk,
    )
    assert next(chunks).frame_indices.size > 0
    cancel_enabled = True
    with pytest.raises(RuntimeError) as caught_after_chunk:
        next(chunks)
    assert caught_after_chunk.value is error
