"""F15 проверка F13-полос и потоковый RMS аналитического сигнала."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.envelopes import stream_band_analytic
from lnt.characterization.f15_result import FEATURE_UNAVAILABLE

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.bands import ResolvedBand

EXPECTED_BANDS: Final = (
    (3_000.0, 10_000.0),
    (10_000.0, 50_000.0),
    (50_000.0, 200_000.0),
)


def checked_f15_bands(bands: tuple[ResolvedBand, ...], filter_order: int) -> str | None:
    """Проверить порядок F13-полос; недоступная полоса даёт F15 reason code."""
    if len(bands) != len(EXPECTED_BANDS) or filter_order <= 0:
        raise ValueError("F15 requires three resolved F13 bands and a positive filter order")
    unavailable = False
    for band, expected in zip(bands, EXPECTED_BANDS, strict=True):
        requested = band.requested
        if (float(requested.low), float(requested.high)) != expected:
            raise ValueError("F15 band order does not match the locked feature names")
        unavailable |= band.effective is None
    return FEATURE_UNAVAILABLE if unavailable else None


def band_window_rms_v(  # noqa: PLR0913 - потоковый источник и геометрия окон
    samples: np.ndarray,
    band: ResolvedBand,
    window_indices: np.ndarray,
    n_nominal: int,
    *,
    sample_rate_hz: float,
    filter_order: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> np.ndarray:
    """RMS модуля аналитического сигнала полосы в каждом выбранном окне."""
    indices = np.asarray(window_indices, dtype=np.int64)
    starts = indices * n_nominal
    stops = starts + n_nominal
    sums = np.zeros(indices.size, dtype=np.float64)
    counts = np.zeros(indices.size, dtype=np.int64)
    for chunk in stream_band_analytic(
        samples,
        band,
        sample_rate_hz=sample_rate_hz,
        filter_order=filter_order,
        resources=resources,
        checkpoint=checkpoint,
    ):
        if chunk.values is None:
            continue
        first = int(np.searchsorted(stops, chunk.start_sample, side="right"))
        last = int(np.searchsorted(starts, chunk.stop_sample, side="left"))
        power = np.abs(chunk.values) ** 2
        for row in range(first, last):
            low = max(int(starts[row]), chunk.start_sample) - chunk.start_sample
            high = min(int(stops[row]), chunk.stop_sample) - chunk.start_sample
            sums[row] += float(np.sum(power[low:high]))
            counts[row] += high - low
    result = np.full(indices.size, np.nan, dtype=np.float64)
    supported = counts == n_nominal
    result[supported] = np.sqrt(sums[supported] / n_nominal)
    return result
