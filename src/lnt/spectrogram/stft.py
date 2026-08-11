"""Порционный STFT над mmap без материализации полного куба."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from scipy import signal

from lnt.errors import InputError
from lnt.spectrogram.errors import SpectrogramCancelledError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from numpy.typing import NDArray

    from lnt.spectrogram.models import CancellationToken, StftSettings

FRAME_CHUNK: Final = 256


@dataclass(frozen=True, slots=True, kw_only=True)
class StftChunk:
    """Линейная мощность соседних STFT-кадров."""

    first_frame: int
    power: NDArray[np.float64]


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
    count = frame_count(int(samples.size), settings)
    for first in range(0, count, FRAME_CHUNK):
        _check_cancelled(cancellation)
        chunk_frames = min(FRAME_CHUNK, count - first)
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
            scaling=settings.scaling,
        )
        yield StftChunk(
            first_frame=first,
            power=np.asarray(np.abs(transformed) ** 2, dtype=np.float64),
        )
    _check_cancelled(cancellation)


def _check_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation is not None and cancellation.cancelled():
        raise SpectrogramCancelledError
