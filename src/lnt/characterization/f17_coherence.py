"""F17: declared cyclic cross-spectrum и magnitude-squared coherence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from lnt.characterization.f17_frequency import FrequencyGrid

type Complex128Array = NDArray[np.complex128]
type Int64Array = NDArray[np.int64]
type Float64Array = NDArray[np.float64]
type BoolArray = NDArray[np.bool_]
_SPECTRUM_NDIM = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class CoherenceEstimate:
    """Один STFT-pass с маской exact mapping и положительного denominator."""

    cyclic_spectrum: Complex128Array
    coherence: Float64Array
    segment_support: Int64Array
    available: BoolArray


def estimate_cyclic_coherence(
    first: Complex128Array,
    second: Complex128Array,
    spectrum_bins: Int64Array,
    grid: FrequencyGrid,
) -> CoherenceEstimate:
    """Вычислить S_alpha и gamma2 для точных симметричных FFT-пар."""
    upper_values = np.asarray(first, dtype=np.complex128)
    lower_values = np.asarray(second, dtype=np.complex128)
    bins = np.asarray(spectrum_bins, dtype=np.int64)
    if (
        upper_values.ndim != _SPECTRUM_NDIM
        or lower_values.shape != upper_values.shape
        or bins.ndim != 1
        or bins.size != upper_values.shape[0]
        or np.any(np.diff(bins) <= 0)
    ):
        raise ValueError("F17 spectra must be aligned two-dimensional arrays")
    shape = grid.available.shape
    cyclic = np.full(shape, np.nan + 1j * np.nan, dtype=np.complex128)
    coherence = np.full(shape, np.nan, dtype=np.float64)
    support = np.zeros(shape, dtype=np.int64)
    available = np.zeros(shape, dtype=np.bool_)
    alpha_indices, frequency_indices = np.nonzero(grid.available)
    if alpha_indices.size == 0 or bins.size == 0 or upper_values.shape[1] == 0:
        return CoherenceEstimate(
            cyclic_spectrum=cyclic,
            coherence=coherence,
            segment_support=support,
            available=available,
        )
    lower_bins = grid.lower_bins[alpha_indices, frequency_indices]
    upper_bins = grid.upper_bins[alpha_indices, frequency_indices]
    lower_rows = np.searchsorted(bins, lower_bins)
    upper_rows = np.searchsorted(bins, upper_bins)
    valid = (
        (lower_rows < bins.size)
        & (upper_rows < bins.size)
        & (bins[np.minimum(lower_rows, bins.size - 1)] == lower_bins)
        & (bins[np.minimum(upper_rows, bins.size - 1)] == upper_bins)
    )
    if not bool(np.all(valid)):
        alpha_indices = alpha_indices[valid]
        frequency_indices = frequency_indices[valid]
        lower_rows = lower_rows[valid]
        upper_rows = upper_rows[valid]
    if alpha_indices.size == 0:
        return CoherenceEstimate(
            cyclic_spectrum=cyclic,
            coherence=coherence,
            segment_support=support,
            available=available,
        )
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        cross = np.mean(upper_values[upper_rows] * np.conjugate(lower_values[lower_rows]), axis=1)
        upper_power = np.mean(np.abs(upper_values[upper_rows]) ** 2, axis=1)
        lower_power = np.mean(np.abs(lower_values[lower_rows]) ** 2, axis=1)
        denominator = upper_power * lower_power
        ratio = np.abs(cross) ** 2 / denominator
    positive = np.isfinite(ratio) & (denominator > 0.0)
    alpha_indices = alpha_indices[positive]
    frequency_indices = frequency_indices[positive]
    cyclic[alpha_indices, frequency_indices] = cross[positive]
    coherence[alpha_indices, frequency_indices] = np.minimum(ratio[positive], 1.0)
    support[alpha_indices, frequency_indices] = upper_values.shape[1]
    available[alpha_indices, frequency_indices] = True
    return CoherenceEstimate(
        cyclic_spectrum=cyclic,
        coherence=coherence,
        segment_support=support,
        available=available,
    )
