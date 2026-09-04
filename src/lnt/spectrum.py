"""Band-спектр Уэлча (3 кГц–3 МГц) с поиском пиков и оценкой Q.

Q оценивается по полуширине пика на уровне половинной мощности (-3 дБ):
Q = f0 / FWHM; f0 уточняется параболической интерполяцией по трём бинам.

PSD считается через ограниченный по памяти ``lnt.psd.compute_welch``
(посегментное накопление, запись не материализуется как float64 целиком,
memmap-входы читаются порциями). Численное соответствие прямому
``scipy.signal.welch`` (hann, detrend=constant, density, mean) —
``rtol=2e-6, atol=1e-15``. Отличие от прежней scipy-реализации:
нечисловые входы (NaN/Inf, переполнение) отклоняются ``PsdDataError``
вместо тихого NaN/Inf-результата.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.errors import InputError
from lnt.psd import FrequencyBand, PsdSettings, compute_welch
from lnt.psd.errors import PsdSettingsError
from lnt.psd.models import DEFAULT_MAX_CHUNK_SAMPLES
from lnt.psd.windows import (
    DEFAULT_RBW_HZ,
    DEFAULT_WINDOW,
    canonical_window_name,
    enbw_hz,
    validate_rbw_hz,
)

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

DEFAULT_BAND_LOW_HZ = 3_000.0
DEFAULT_BAND_HIGH_HZ = 3_000_000.0
TARGET_RESOLUTION_HZ = DEFAULT_RBW_HZ
MIN_NPERSEG = 1_024
MIN_BAND_BINS = 8
MIN_PROMINENCE_DB = 6.0
PSD_FLOOR = 1e-30
NYQUIST_FRACTION = 0.45
DEFAULT_MAX_PEAKS = 8
MIN_PEAK_REGION_BINS = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectrumPeak:
    """Обнаруженный спектральный пик."""

    frequency_hz: float
    level_db: float
    prominence_db: float
    q_factor: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class BandSpectrum:
    """PSD в рабочей полосе с найденными пиками (сортировка по prominence)."""

    frequencies_hz: Float64Array
    psd_v2_per_hz: Float64Array
    resolution_hz: float
    band_low_hz: float
    band_high_hz: float
    peaks: tuple[SpectrumPeak, ...]
    window: str = DEFAULT_WINDOW
    enbw_hz: float = 0.0


def compute_band_spectrum(  # noqa: PLR0913 - RBW/окно это отдельные контракты селектора
    samples: Float32Array,
    *,
    sample_rate_hz: float,
    band_low_hz: float = DEFAULT_BAND_LOW_HZ,
    band_high_hz: float = DEFAULT_BAND_HIGH_HZ,
    max_peaks: int = DEFAULT_MAX_PEAKS,
    rbw_hz: float = DEFAULT_RBW_HZ,
    window: str = DEFAULT_WINDOW,
) -> BandSpectrum:
    """Считает Welch-PSD в полосе и находит пики; вход в вольтах."""
    if samples.size < MIN_NPERSEG:
        raise InputError(
            f"слишком мало отсчётов для спектра: {samples.size}, нужно >= {MIN_NPERSEG}",
        )
    try:
        resolved_rbw_hz = validate_rbw_hz(rbw_hz)
        window_name = canonical_window_name(window)
    except PsdSettingsError as error:
        raise InputError(str(error)) from error
    effective_high = min(band_high_hz, NYQUIST_FRACTION * sample_rate_hz)
    if band_low_hz >= effective_high:
        raise InputError(
            f"пустая полоса анализа: {band_low_hz:.0f}..{effective_high:.0f} Гц",
        )
    nperseg = _choose_nperseg(samples.size, sample_rate_hz, resolved_rbw_hz)
    result = compute_welch(
        np.asarray(samples),
        settings=PsdSettings(
            sample_rate_hz=sample_rate_hz,
            nperseg=nperseg,
            max_chunk_samples=max(DEFAULT_MAX_CHUNK_SAMPLES, nperseg),
            bands=(FrequencyBand(name="full", low_hz=0.0, high_hz=sample_rate_hz / 2.0),),
            window=window_name,
            overlap_fraction=0.5,
        ),
    )
    freqs = result.frequency_hz
    psd = result.psd_v2_per_hz
    mask = (freqs >= band_low_hz) & (freqs <= effective_high)
    if int(mask.sum()) < MIN_BAND_BINS:
        raise InputError(
            f"полоса {band_low_hz:.0f}..{effective_high:.0f} Гц уже разрешения спектра",
        )
    band_freqs = freqs[mask].copy()
    band_psd = np.maximum(psd[mask], PSD_FLOOR).copy()
    resolution_hz = sample_rate_hz / nperseg
    peaks = _find_peaks(
        band_freqs,
        band_psd,
        max_peaks=max_peaks,
        min_prominence_db=MIN_PROMINENCE_DB,
    )
    return BandSpectrum(
        frequencies_hz=band_freqs,
        psd_v2_per_hz=band_psd,
        resolution_hz=resolution_hz,
        band_low_hz=band_low_hz,
        band_high_hz=effective_high,
        peaks=peaks,
        window=window_name,
        enbw_hz=enbw_hz(window_name, nperseg, sample_rate_hz),
    )


def level_at_db(spectrum: BandSpectrum, frequency_hz: float) -> float:
    """Уровень PSD (дБ отн. 1 В²/Гц) в ближайшем к частоте бине."""
    index = int(np.argmin(np.abs(spectrum.frequencies_hz - frequency_hz)))
    return float(10.0 * np.log10(spectrum.psd_v2_per_hz[index]))


def find_qualified_peaks(
    frequencies_hz: Float64Array,
    corrected_psd_v2_per_hz: Float64Array,
    qualified: BoolArray,
    *,
    max_peaks: int = DEFAULT_MAX_PEAKS,
    min_prominence_db: float = MIN_PROMINENCE_DB,
) -> tuple[SpectrumPeak, ...]:
    """Находит пики только в непрерывных qualified-регионах corrected excess PSD."""
    present = qualified & np.isfinite(corrected_psd_v2_per_hz)
    start_indices = np.flatnonzero(present & np.r_[True, ~present[:-1]])
    stop_indices = np.flatnonzero(present & np.r_[~present[1:], True]) + 1
    found: list[SpectrumPeak] = []
    for start, stop in zip(start_indices, stop_indices, strict=True):
        region_freqs = frequencies_hz[start:stop]
        region_psd = corrected_psd_v2_per_hz[start:stop]
        region_peaks = (
            _find_peaks(
                region_freqs,
                region_psd,
                max_peaks=max_peaks,
                min_prominence_db=min_prominence_db,
            )
            if stop - start >= MIN_PEAK_REGION_BINS
            else ()
        )
        found.extend(region_peaks)
    return tuple(sorted(found, key=lambda peak: peak.prominence_db, reverse=True)[:max_peaks])


def _choose_nperseg(
    sample_count: int, sample_rate_hz: float, rbw_hz: float = DEFAULT_RBW_HZ
) -> int:
    target = sample_rate_hz / rbw_hz
    power = int(np.floor(np.log2(max(target, MIN_NPERSEG))))
    nperseg = 2**power
    while nperseg > sample_count:
        nperseg //= 2
    return max(nperseg, MIN_NPERSEG)


def _find_peaks(
    freqs: Float64Array,
    psd: Float64Array,
    *,
    max_peaks: int,
    min_prominence_db: float,
) -> tuple[SpectrumPeak, ...]:
    psd_db = 10.0 * np.log10(psd)
    indices_raw, props = signal.find_peaks(psd_db, prominence=min_prominence_db)
    indices = np.asarray(indices_raw, dtype=np.intp)
    prominences = np.asarray(props["prominences"], dtype=np.float64)
    order = np.argsort(prominences)[::-1][:max_peaks]
    found: list[SpectrumPeak] = []
    for position in order:
        index = int(indices[position])
        half_power = float(psd[index]) / 2.0
        left = _half_power_crossing(freqs, psd, index, half_power, step=-1)
        right = _half_power_crossing(freqs, psd, index, half_power, step=1)
        found.append(
            SpectrumPeak(
                frequency_hz=_centroid_frequency(freqs, psd, index, left, right),
                level_db=float(psd_db[index]),
                prominence_db=float(prominences[position]),
                q_factor=_q_from_crossings(float(freqs[index]), left, right),
            ),
        )
    return tuple(found)


def _q_from_crossings(peak_freq: float, left: float | None, right: float | None) -> float | None:
    if left is None or right is None or right <= left:
        return None
    return peak_freq / (right - left)


def _centroid_frequency(
    freqs: Float64Array,
    psd: Float64Array,
    index: int,
    left: float | None,
    right: float | None,
) -> float:
    if left is None or right is None or right <= left:
        return float(freqs[index])
    mask = (freqs >= left) & (freqs <= right)
    weights = psd[mask] - float(psd[index]) / 2.0
    weights = np.maximum(weights, 0.0)
    total = float(weights.sum())
    if total <= 0.0:
        return float(freqs[index])
    return float(np.sum(freqs[mask] * weights) / total)


def _half_power_crossing(
    freqs: Float64Array,
    psd: Float64Array,
    index: int,
    half_power: float,
    *,
    step: int,
) -> float | None:
    position = index
    while 0 <= position + step < psd.size:
        neighbor = position + step
        if float(psd[neighbor]) <= half_power:
            inside_power = float(psd[position])
            outside_power = float(psd[neighbor])
            fraction = (inside_power - half_power) / (inside_power - outside_power)
            return float(freqs[position]) + fraction * (
                float(freqs[neighbor]) - float(freqs[position])
            )
        position = neighbor
    return None
