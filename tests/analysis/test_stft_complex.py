from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pytest
from scipy import signal

from lnt.errors import InputError
from lnt.spectrogram.errors import SpectrogramCancelledError
from lnt.spectrogram.models import StftSettings
from lnt.spectrogram.stft import stream_complex, stream_power

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray


def _settings(
    *, segment_samples: int = 150, hop_samples: int = 47, scaling: str = "spectrum"
) -> StftSettings:
    return StftSettings.parse(
        version=1,
        window="hann",
        segment_samples=segment_samples,
        hop_samples=hop_samples,
        detrend="constant",
        scaling=scaling,
    )


def _direct(
    samples: NDArray[np.float32] | NDArray[np.float64],
    sample_rate_hz: float,
    settings: StftSettings,
) -> tuple[NDArray[np.float64], NDArray[np.complex64] | NDArray[np.complex128]]:
    _, time_s, coefficients = vars(signal)["stft"](
        samples,
        fs=sample_rate_hz,
        window=settings.window,
        nperseg=settings.segment_samples,
        noverlap=settings.segment_samples - settings.hop_samples,
        detrend=settings.detrend,
        boundary=None,
        padded=False,
        return_onesided=True,
        scaling=settings.scaling,
    )
    return time_s, coefficients


@dataclass
class SequenceCancellation:
    states: list[bool]

    def cancelled(self) -> bool:
        return self.states.pop(0)


def test_exact_bin_cosine_has_analytic_spectrum_amplitude_and_phase() -> None:
    sample_rate_hz = 2048.0
    segment_samples = 128
    frequency_bin = 11
    amplitude = 3.25
    phase = 0.37
    sample_index = np.arange(segment_samples, dtype=np.float64)
    samples = amplitude * np.cos(
        2.0 * np.pi * frequency_bin * sample_index / segment_samples + phase
    )
    settings = StftSettings(
        version=1,
        window="hann",
        segment_samples=segment_samples,
        hop_samples=37,
        detrend="constant",
        scaling="spectrum",
    )

    chunks = list(stream_complex(samples, sample_rate_hz, settings))

    assert len(chunks) == 1
    assert chunks[0].first_frame == 0
    assert chunks[0].coefficients.dtype == np.complex128
    coefficient = chunks[0].coefficients[frequency_bin, 0]
    np.testing.assert_allclose(np.abs(coefficient), amplitude / 2.0, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(np.angle(coefficient), phase, rtol=0.0, atol=1e-13)


def test_complex_chunks_match_direct_scipy_with_global_frame_centres() -> None:
    sample_rate_hz = 12_345.0
    settings = _settings()
    frame_total = 530
    sample_count = settings.segment_samples + (frame_total - 1) * settings.hop_samples + 19
    samples = np.random.default_rng(6022).normal(size=sample_count)

    chunks = list(stream_complex(samples, sample_rate_hz, settings))
    direct_time_s, direct_coefficients = _direct(samples, sample_rate_hz, settings)
    coefficients = np.concatenate([chunk.coefficients for chunk in chunks], axis=1)
    frame_indices = np.concatenate(
        [chunk.first_frame + np.arange(chunk.coefficients.shape[1]) for chunk in chunks]
    )
    expected_time_s = (
        frame_indices * settings.hop_samples + settings.segment_samples / 2
    ) / sample_rate_hz

    assert [chunk.first_frame for chunk in chunks] == [0, 256, 512]
    assert [chunk.coefficients.shape[1] for chunk in chunks] == [256, 256, 18]
    np.testing.assert_allclose(coefficients, direct_coefficients, rtol=1e-14, atol=1e-14)
    np.testing.assert_array_equal(direct_time_s, expected_time_s)


def test_float32_complex_dtype_and_power_are_bitwise_legacy_compatible() -> None:
    settings = _settings(scaling="psd")
    samples = np.random.default_rng(41).normal(size=30_000).astype(np.float32)

    complex_chunks = list(stream_complex(samples, 8000.0, settings))
    power_chunks = list(stream_power(samples, 8000.0, settings))

    assert all(chunk.coefficients.dtype == np.complex64 for chunk in complex_chunks)
    assert [chunk.first_frame for chunk in complex_chunks] == [0, 256, 512]
    for complex_chunk, power_chunk in zip(complex_chunks, power_chunks, strict=True):
        assert complex_chunk.first_frame == power_chunk.first_frame
        start = power_chunk.first_frame * settings.hop_samples
        stop = (
            start
            + settings.segment_samples
            + (power_chunk.power.shape[1] - 1) * settings.hop_samples
        )
        _, direct_coefficients = _direct(samples[start:stop], 8000.0, settings)
        expected = np.asarray(np.abs(direct_coefficients) ** 2, dtype=np.float64)
        np.testing.assert_array_equal(power_chunk.power, expected)


def test_max_chunk_samples_bounds_each_input_and_preserves_global_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    samples = np.random.default_rng(9).normal(size=2000)
    max_chunk_samples = settings.segment_samples + 2 * settings.hop_samples + 20
    observed_sizes: list[int] = []
    scipy_stft: Callable[..., tuple[NDArray[np.float64], NDArray[np.float64], np.ndarray]] = vars(
        signal
    )["stft"]

    def recording_stft(
        values: NDArray[np.float32] | NDArray[np.float64], **kwargs: object
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], np.ndarray]:
        observed_sizes.append(int(values.size))
        return scipy_stft(values, **kwargs)

    monkeypatch.setitem(vars(signal), "stft", recording_stft)
    chunks = list(
        stream_complex(
            samples,
            4000.0,
            settings,
            max_chunk_samples=max_chunk_samples,
        )
    )

    assert max(observed_sizes) <= max_chunk_samples
    assert all(chunk.coefficients.shape[1] <= 3 for chunk in chunks)
    assert [chunk.first_frame for chunk in chunks] == list(range(0, 40, 3))


def test_too_small_chunk_cap_is_rejected_before_checkpoint() -> None:
    settings = _settings()
    checkpoint_calls = 0

    def checkpoint() -> None:
        nonlocal checkpoint_calls
        checkpoint_calls += 1

    with pytest.raises(InputError, match="max_chunk_samples"):
        list(
            stream_complex(
                np.empty(0, dtype=np.float32),
                1000.0,
                settings,
                max_chunk_samples=settings.segment_samples - 1,
                checkpoint=checkpoint,
            )
        )
    assert checkpoint_calls == 0


def test_checkpoint_runs_before_every_chunk_and_at_termination() -> None:
    settings = _settings()
    calls: list[int] = []
    samples = np.zeros(settings.segment_samples + 4 * settings.hop_samples)

    chunks = list(
        stream_complex(
            samples,
            1000.0,
            settings,
            max_chunk_samples=settings.segment_samples + settings.hop_samples,
            checkpoint=lambda: calls.append(len(calls)),
        )
    )

    assert len(chunks) == 3
    assert calls == [0, 1, 2, 3]


def test_checkpoint_exception_propagates_unchanged() -> None:
    failure = RuntimeError("stop here")

    def checkpoint() -> None:
        raise failure

    with pytest.raises(RuntimeError) as caught:
        list(stream_complex(np.zeros(150), 1000.0, _settings(), checkpoint=checkpoint))
    assert caught.value is failure


@pytest.mark.parametrize("sample_count", [0, 149])
def test_cancellation_is_checked_for_empty_short_series(sample_count: int) -> None:
    token = SequenceCancellation([True])

    with pytest.raises(SpectrogramCancelledError):
        list(stream_complex(np.zeros(sample_count), 1000.0, _settings(), token))


def test_cancellation_is_checked_before_and_between_bounded_chunks() -> None:
    settings = _settings()
    samples = np.zeros(settings.segment_samples + settings.hop_samples)

    with pytest.raises(SpectrogramCancelledError):
        next(stream_complex(samples, 1000.0, settings, SequenceCancellation([True])))

    chunks = stream_complex(
        samples,
        1000.0,
        settings,
        SequenceCancellation([False, True]),
        max_chunk_samples=settings.segment_samples,
    )
    assert next(chunks).first_frame == 0
    with pytest.raises(SpectrogramCancelledError):
        next(chunks)
