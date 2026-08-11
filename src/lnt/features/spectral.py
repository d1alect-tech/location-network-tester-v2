"""Линейные полосовые оценки PSD и спектрограммы."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from lnt.features.models import (
    BandFeature,
    NoiseFloor,
    PeakFeature,
    SpectralFeatures,
    SpectrogramWindowFeatures,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.features.bands import BandDefinition, BandSet
    from lnt.psd.models import PsdResult
    from lnt.spectrogram.models import SpectrogramOverview


def compute_psd_features(result: PsdResult, bands: BandSet) -> SpectralFeatures:
    """Считает оценки только из линейной PSD; dB используется лишь как отношение."""
    frequencies = np.asarray(result.frequency_hz, dtype=np.float64)
    power = np.asarray(result.psd_v2_per_hz, dtype=np.float64)
    resolution_hz = _resolution(frequencies)
    return SpectralFeatures(
        bands=tuple(_band_feature(frequencies, power, band, resolution_hz) for band in bands.bands)
    )


def compute_spectrogram_features(
    overview: SpectrogramOverview, bands: BandSet
) -> tuple[SpectrogramWindowFeatures, ...]:
    """Считает те же оценки для каждого временного окна overview."""
    frequencies = np.asarray(overview.frequency_hz, dtype=np.float64)
    widths = np.diff(np.asarray(overview.frequency_edges_hz, dtype=np.float64))
    windows: list[SpectrogramWindowFeatures] = []
    for index, time_s in enumerate(overview.time_s):
        power = np.asarray(overview.linear_power[:, index], dtype=np.float64)
        qualified = np.asarray(overview.coverage[:, index] > 0, dtype=np.bool_)
        power = np.where(qualified, power, np.nan)
        windows.append(
            SpectrogramWindowFeatures(
                window_id=f"window-{index:06d}",
                time_s=float(time_s),
                bands=tuple(
                    _band_feature(frequencies, power, band, widths) for band in bands.bands
                ),
            )
        )
    return tuple(windows)


def _band_feature(
    frequencies: NDArray[np.float64],
    power: NDArray[np.float64],
    band: BandDefinition,
    bin_width_hz: float | NDArray[np.float64],
) -> BandFeature:
    selected = (frequencies >= band.low_hz) & (frequencies <= band.high_hz)
    values = power[selected]
    qualified = np.isfinite(values) & (values >= 0.0)
    finite = values[qualified]
    total = int(values.size)
    count = int(finite.size)
    floor = NoiseFloor(
        median_v2_per_hz=float(np.median(finite)) if count else None,
        p05_v2_per_hz=float(np.percentile(finite, 5)) if count else None,
        p95_v2_per_hz=float(np.percentile(finite, 95)) if count else None,
        qualified_bin_count=count,
        total_bin_count=total,
        qualified=count == total and total > 0,
        reason_code=None if count == total and total > 0 else "unqualified_bins",
    )
    if count == 0:
        return BandFeature(
            band=band, integrated_power_v2=None, rms_v=None, noise_floor=floor, peak=None
        )
    widths = np.broadcast_to(np.asarray(bin_width_hz, dtype=np.float64), frequencies.shape)[
        selected
    ]
    integrated = float(np.sum(values * widths)) if count == total else None
    peak = _peak_feature(frequencies[selected], values, qualified, floor)
    return BandFeature(
        band=band,
        integrated_power_v2=integrated,
        rms_v=math.sqrt(integrated) if integrated is not None else None,
        noise_floor=floor,
        peak=peak,
    )


def _peak_feature(
    frequencies: NDArray[np.float64],
    power: NDArray[np.float64],
    qualified: NDArray[np.bool_],
    floor: NoiseFloor,
) -> PeakFeature | None:
    if not np.any(qualified) or floor.median_v2_per_hz is None:
        return None
    index = int(np.nanargmax(np.where(qualified, power, np.nan)))
    peak_power = float(power[index])
    baseline = floor.median_v2_per_hz
    prominence = 10.0 * math.log10(peak_power / baseline) if baseline > 0.0 else math.inf
    left = _half_power_crossing(frequencies, power, qualified, index, -1)
    right = _half_power_crossing(frequencies, power, qualified, index, 1)
    gap = left is None or right is None
    q_factor = None if left is None or right is None else float(frequencies[index]) / (right - left)
    return PeakFeature(
        frequency_hz=float(frequencies[index]),
        power_v2_per_hz=peak_power,
        prominence_db=prominence,
        q_factor=q_factor,
        q_reason_code="unqualified_gap"
        if gap and not np.all(qualified)
        else ("half_power_unbounded" if gap else None),
        qualified=not gap,
    )


def _half_power_crossing(
    frequencies: NDArray[np.float64],
    power: NDArray[np.float64],
    qualified: NDArray[np.bool_],
    peak_index: int,
    step: int,
) -> float | None:
    half_power = float(power[peak_index]) / 2.0
    position = peak_index
    while 0 <= position + step < power.size:
        neighbor = position + step
        if not qualified[neighbor]:
            return None
        if float(power[neighbor]) <= half_power:
            inside = float(power[position])
            outside = float(power[neighbor])
            fraction = (inside - half_power) / (inside - outside)
            return float(frequencies[position]) + fraction * (
                float(frequencies[neighbor]) - float(frequencies[position])
            )
        position = neighbor
    return None


def _resolution(frequencies: NDArray[np.float64]) -> float:
    return float(np.median(np.diff(frequencies))) if frequencies.size > 1 else 0.0
