"""Ограниченный по памяти односторонний Welch PSD.

Частотная сетка получена только через ``np.fft.rfftfreq``. Численное
соответствие SciPy 1.14+ проверяется с ``rtol=2e-6, atol=1e-15``.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from lnt.psd.errors import PsdCancelledError, PsdDataError
from lnt.psd.models import BandRms, PsdResult, PsdSettings
from lnt.psd.windows import canonical_window_name, enbw_hz, get_window

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]
InputArray = Float32Array | Float64Array


class CancellationToken(Protocol):
    """Минимальный контракт проверяемой отмены."""

    @property
    def cancelled(self) -> bool:
        """Истина после запроса отмены."""
        ...


def _validate_input(samples: InputArray, settings: PsdSettings) -> int:
    sample_count = int(samples.size)
    if sample_count == 0:
        raise PsdDataError("PSD: входной массив пуст")
    if samples.ndim != 1:
        raise PsdDataError("PSD: ожидается одномерный входной массив")
    if sample_count < settings.nperseg:
        raise PsdDataError(
            f"PSD: запись слишком короткая: {sample_count}, нужно >= {settings.nperseg}"
        )
    return sample_count


def compute_welch(
    samples: InputArray,
    *,
    settings: PsdSettings,
    cancellation: CancellationToken | None = None,
) -> PsdResult:
    """Считает Welch порциями, не материализуя всю запись как float64."""
    sample_count = _validate_input(samples, settings)
    step = max(1, settings.nperseg - settings.noverlap)
    segment_count = 1 + (sample_count - settings.nperseg) // step
    segments_per_chunk = max(1, (settings.max_chunk_samples - settings.nperseg) // step + 1)
    window_name = canonical_window_name(settings.window)
    window = get_window(window_name, settings.nperseg)
    scale = 1.0 / (settings.sample_rate_hz * float(np.sum(window * window)))
    accumulated = np.zeros(settings.nperseg // 2 + 1, dtype=np.float64)

    for first_segment in range(0, segment_count, segments_per_chunk):
        if cancellation is not None and cancellation.cancelled:
            raise PsdCancelledError("расчёт PSD отменён")
        chunk_segments = min(segments_per_chunk, segment_count - first_segment)
        first_sample = first_segment * step
        last_sample = first_sample + (chunk_segments - 1) * step + settings.nperseg
        chunk = np.asarray(samples[first_sample:last_sample], dtype=np.float64)
        if not np.all(np.isfinite(chunk)):
            raise PsdDataError("PSD: данные содержат NaN или бесконечность")
        if float(np.max(np.abs(chunk))) > np.sqrt(np.finfo(np.float64).max):
            raise PsdDataError("PSD: численное переполнение входных данных")
        for offset in range(0, chunk_segments * step, step):
            segment = chunk[offset : offset + settings.nperseg]
            segment = (segment - float(np.mean(segment))) * window
            transformed = np.fft.rfft(segment)
            periodogram = np.asarray(transformed.real**2 + transformed.imag**2) * scale
            if settings.nperseg % 2 == 0:
                periodogram[1:-1] *= 2.0
            else:
                periodogram[1:] *= 2.0
            accumulated += periodogram

    psd = accumulated / segment_count
    if not np.all(np.isfinite(psd)):
        raise PsdDataError("PSD: численное переполнение при накоплении")
    frequency = np.fft.rfftfreq(settings.nperseg, d=1.0 / settings.sample_rate_hz)
    asd = np.sqrt(psd)
    with np.errstate(divide="ignore"):
        level_db = 10.0 * np.log10(psd / 1.0)
    band_rms = tuple(
        BandRms(
            band=band,
            rms_v=float(
                np.sqrt(
                    np.sum(psd[(frequency >= band.low_hz) & (frequency <= band.high_hz)])
                    * settings.resolution_hz
                )
            ),
        )
        for band in settings.bands
    )
    return PsdResult(
        frequency_hz=frequency,
        psd_v2_per_hz=psd,
        asd_v_per_sqrt_hz=asd,
        level_db_v2_per_hz=level_db,
        band_rms=band_rms,
        segment_count=segment_count,
        window=window_name,
        enbw_hz=enbw_hz(window_name, settings.nperseg, settings.sample_rate_hz),
    )
