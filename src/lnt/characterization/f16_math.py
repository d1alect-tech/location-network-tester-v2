"""F16: unbiased FFT ACF, MAD recurrence и exact count-window moments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f13_math import envelope_mad
from lnt.characterization.sync_grid import nominal_window_samples

if TYPE_CHECKING:
    from collections.abc import Sequence

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]
type Span = tuple[int, int]


class F16ScaleZeroError(ValueError):
    """Локальный MAD или lag-zero covariance не имеет положительной шкалы."""


def declared_lag_samples(lags_s: Sequence[float], sample_rate_hz: float) -> Int64Array:
    """Перевести declared seconds в nearest-integer sample offsets."""
    return np.rint(np.asarray(lags_s, dtype=np.float64) * sample_rate_hz).astype(np.int64)


@dataclass(slots=True)
class F16MemoryAccumulator:
    """Pair-weighted ACF и recurrence support по анализируемым сегментам."""

    lag_samples: Int64Array
    recurrence_radius_mad: Float64Array
    covariance_sum: Float64Array
    recurrence_hit: Float64Array
    pair_count: Int64Array
    lag_zero_sum: float = 0.0
    sample_count: int = 0
    segment_count: int = 0

    @classmethod
    def empty(
        cls, lag_samples: Int64Array, recurrence_radius_mad: Float64Array
    ) -> F16MemoryAccumulator:
        """Создать exact fixed axes без измерений."""
        lags = np.asarray(lag_samples, dtype=np.int64)
        radii = np.asarray(recurrence_radius_mad, dtype=np.float64)
        return cls(
            lag_samples=lags,
            recurrence_radius_mad=radii,
            covariance_sum=np.zeros(lags.size, dtype=np.float64),
            recurrence_hit=np.zeros((lags.size, radii.size), dtype=np.float64),
            pair_count=np.zeros(lags.size, dtype=np.int64),
        )

    def add(self, residual: Float64Array) -> None:
        """Добавить один непрерывный сегмент длиной не больше locked FFT cap."""
        values = np.asarray(residual, dtype=np.float64)
        if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
            raise ValueError("F16 segment must be one finite nonempty vector")
        scale = envelope_mad(values)
        if not np.isfinite(scale) or scale <= 0.0:
            raise F16ScaleZeroError
        products = _linear_products(values, self.lag_samples)
        size = int(values.size)
        for index, lag in enumerate(self.lag_samples.tolist()):
            if lag >= size:
                continue
            offset = int(lag)
            self.covariance_sum[index] += products[offset]
            self.pair_count[index] += size - offset
            difference = (
                np.zeros(size, dtype=np.float64)
                if offset == 0
                else np.abs(values[offset:] - values[:-offset])
            )
            for radius_index, radius in enumerate(self.recurrence_radius_mad.tolist()):
                self.recurrence_hit[index, radius_index] += np.count_nonzero(
                    difference <= float(radius) * scale
                )
        self.lag_zero_sum += float(products[0])
        self.sample_count += size
        self.segment_count += 1

    def autocorrelation(self) -> Float64Array:
        """Нормировать pair-weighted covariance на глобальную lag-zero covariance."""
        if self.sample_count == 0 or self.lag_zero_sum <= 0.0:
            raise F16ScaleZeroError
        result = np.full(self.lag_samples.size, np.nan, dtype=np.float64)
        supported = self.pair_count > 0
        result[supported] = (self.covariance_sum[supported] / self.pair_count[supported]) / (
            self.lag_zero_sum / self.sample_count
        )
        return result

    def recurrence_rate(self) -> Float64Array:
        """Разделить exact recurrence hits на total within-segment pairs."""
        result = np.full(self.recurrence_hit.shape, np.nan, dtype=np.float64)
        supported = self.pair_count > 0
        result[supported] = self.recurrence_hit[supported] / self.pair_count[supported, None]
        return result


def _linear_products(values: Float64Array, lags: Int64Array) -> Float64Array:
    """Получить linear products zero-padding до FFT length >= 2N-1.

    Паддинг длиннее полного linear product spectrum исключает circular wrap: ASK
    для lag k видит только пары внутри исходного N, а не хвост с начала сегмента.
    """
    size = int(values.size)
    required = 2 * size - 1
    fft_length = 1 << (required - 1).bit_length()
    spectrum = np.fft.rfft(values, n=fft_length)
    products = np.fft.irfft(spectrum * np.conjugate(spectrum), n=fft_length)
    if bool(np.any(lags < 0)):
        raise ValueError("F16 lag offsets must be nonnegative")
    return products


@dataclass(frozen=True, slots=True, kw_only=True)
class F16CountSummary:
    """Count moments с явными availability masks."""

    mean: Float64Array
    variance: Float64Array
    fano_factor: Float64Array
    available: BoolArray
    fano_available: BoolArray


@dataclass(slots=True)
class F16CountAccumulator:
    """Global sample-zero nonoverlap counts, не пересекающие qualified gaps."""

    window_samples: Int64Array
    count_window: Int64Array
    span_starts: Int64Array
    span_stops: Int64Array
    event_window_count: dict[int, dict[int, int]] = field(default_factory=dict)
    event_count: int = 0

    @classmethod
    def empty(
        cls, windows_s: Sequence[float], sample_rate_hz: float, spans: Sequence[Span]
    ) -> F16CountAccumulator:
        """Посчитать только полные global-aligned окна внутри qualified spans."""
        sizes = np.asarray(
            [nominal_window_samples(value, sample_rate_hz) for value in windows_s],
            dtype=np.int64,
        )
        normalized = _normalized_spans(spans)
        counts = np.asarray(
            [sum(_complete_window_count(span, int(size)) for span in normalized) for size in sizes],
            dtype=np.int64,
        )
        return cls(
            window_samples=sizes,
            count_window=counts,
            span_starts=np.asarray([start for start, _ in normalized], dtype=np.int64),
            span_stops=np.asarray([stop for _, stop in normalized], dtype=np.int64),
        )

    def add_peak(self, peak_sample: int) -> None:
        """Отнести event peak к одному global window, только если окно полно."""
        self.event_count += 1
        for index, size in enumerate(self.window_samples.tolist()):
            if size <= 0:
                continue
            start = (int(peak_sample) // int(size)) * int(size)
            span_index = int(np.searchsorted(self.span_starts, start, side="right")) - 1
            if span_index < 0:
                continue
            span_start = int(self.span_starts[span_index])
            span_stop = int(self.span_stops[span_index])
            if span_start <= start and start + int(size) <= span_stop:
                occupied = self.event_window_count.setdefault(index, {})
                window_index = start // int(size)
                occupied[window_index] = occupied.get(window_index, 0) + 1

    def summary(self, minimum_windows: int) -> F16CountSummary:
        """Вычислить sample variance ddof=1 и Fano только на locked support."""
        available = self.count_window >= int(minimum_windows)
        mean = np.full(self.window_samples.size, np.nan, dtype=np.float64)
        variance = np.full(self.window_samples.size, np.nan, dtype=np.float64)
        fano = np.full(self.window_samples.size, np.nan, dtype=np.float64)
        for index in np.flatnonzero(available).tolist():
            count = float(self.count_window[index])
            observed = self.event_window_count.get(int(index), {})
            sum_count = float(sum(observed.values()))
            sum_square = float(sum(value * value for value in observed.values()))
            means = sum_count / count
            mean[index] = means
            variance[index] = (sum_square - count * means**2) / (count - 1.0)
        fano_available = available & (mean > 0.0)
        fano[fano_available] = variance[fano_available] / mean[fano_available]
        return F16CountSummary(
            mean=mean,
            variance=variance,
            fano_factor=fano,
            available=available,
            fano_available=fano_available,
        )


def _normalized_spans(spans: Sequence[Span]) -> tuple[Span, ...]:
    return tuple((int(start), int(stop)) for start, stop in spans if int(stop) > int(start))


def _complete_window_count(span: Span, size: int) -> int:
    if size <= 0:
        return 0
    start, stop = span
    first = (start + size - 1) // size
    after_last = stop // size
    return max(0, after_last - first)
