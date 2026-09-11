"""Порционный STFT над mmap без материализации полного куба."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from scipy import signal

from lnt.errors import InputError
from lnt.spectrogram.errors import SpectrogramCancelledError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from numpy.typing import NDArray

    from lnt.spectrogram.models import CancellationToken, StftSettings

FRAME_CHUNK: Final = 256


@dataclass(frozen=True, slots=True, kw_only=True)
class StftChunk:
    """Линейная мощность соседних STFT-кадров."""

    first_frame: int
    power: NDArray[np.float64]


@dataclass(frozen=True, slots=True, kw_only=True)
class ComplexStftChunk:
    """Комплексные коэффициенты соседних STFT-кадров."""

    first_frame: int
    coefficients: NDArray[np.complex64] | NDArray[np.complex128]


def open_samples(path: Path) -> NDArray[np.float32]:
    """Открывает одномерный float32 NPY как mmap."""
    try:
        samples = np.load(path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError) as error:
        raise InputError(f"спектрограмма: не удалось открыть NPY: {path}") from error
    if samples.ndim != 1 or samples.dtype != np.float32:
        raise InputError("спектрограмма: требуется одномерный NPY float32")
    return samples


def frequencies(sample_rate_hz: float, settings: StftSettings) -> NDArray[np.float64]:
    """Возвращает одностороннюю частотную ось STFT."""
    return np.asarray(
        np.fft.rfftfreq(settings.segment_samples, d=1.0 / sample_rate_hz),
        dtype=np.float64,
    )


def frame_count(sample_count: int, settings: StftSettings) -> int:
    """Считает только полностью доступные кадры, без zero padding."""
    if sample_count < settings.segment_samples:
        return 0
    return 1 + (sample_count - settings.segment_samples) // settings.hop_samples


def stream_power(
    samples: NDArray[np.float32],
    sample_rate_hz: float,
    settings: StftSettings,
    cancellation: CancellationToken | None = None,
) -> Iterator[StftChunk]:
    """Вычисляет до FRAME_CHUNK кадров за раз и проверяет отмену между порциями."""
    for chunk in stream_complex(samples, sample_rate_hz, settings, cancellation):
        yield StftChunk(
            first_frame=chunk.first_frame,
            power=np.asarray(np.abs(chunk.coefficients) ** 2, dtype=np.float64),
        )


def stream_complex(  # noqa: PLR0913 - public seam keeps limits and hooks explicit
    samples: NDArray[np.float32] | NDArray[np.float64],
    sample_rate_hz: float,
    settings: StftSettings,
    cancellation: CancellationToken | None = None,
    *,
    max_chunk_samples: int | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> Iterator[ComplexStftChunk]:
    """Вычисляет комплексный STFT ограниченными, глобально нумерованными порциями."""
    if max_chunk_samples is not None and max_chunk_samples < settings.segment_samples:
        raise InputError("спектрограмма: max_chunk_samples меньше длины окна")
    count = frame_count(int(samples.size), settings)
    chunk_limit = FRAME_CHUNK
    if max_chunk_samples is not None:
        chunk_limit = min(
            FRAME_CHUNK,
            1 + (max_chunk_samples - settings.segment_samples) // settings.hop_samples,
        )
    for first in range(0, count, chunk_limit):
        if checkpoint is not None:
            checkpoint()
        _check_cancelled(cancellation)
        chunk_frames = min(chunk_limit, count - first)
        start = first * settings.hop_samples
        stop = start + settings.segment_samples + (chunk_frames - 1) * settings.hop_samples
        stft = vars(signal)["stft"]
        _, _, transformed = stft(
            samples[start:stop],
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
        yield ComplexStftChunk(
            first_frame=first,
            coefficients=transformed,
        )
    if checkpoint is not None:
        checkpoint()
    _check_cancelled(cancellation)


def _check_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation is not None and cancellation.cancelled():
        raise SpectrogramCancelledError
