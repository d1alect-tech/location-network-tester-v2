"""Детектор гармоник IEC 61000-4-7: 12×200 мс, subgroups/IHG, THD, sync resample."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.harmonics.constants import (
    BIN_HZ,
    DFT_BINS_PER_HARMONIC,
    H_MAX,
    HARMONICS_VERSION,
    NOMINAL_GRID_HZ,
    RECORD_DURATION_S,
    WINDOW_COUNT,
    WINDOW_DURATION_S,
)
from lnt.harmonics.models import (
    HarmonicsInventory,
    HarmonicsSettings,
    HarmonicsWindow,
    harmonics_preset,
    harmonics_settings_hash,
)

FloatArray = NDArray[np.floating]


def _validate(samples: FloatArray, sample_rate_hz: float) -> int:
    view = np.asarray(samples)
    if view.ndim != 1 or view.size == 0:
        raise InputError("гармоники: требуется непустой одномерный ряд")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise InputError("гармоники: частота дискретизации некорректна")
    return int(view.size)


def _estimate_grid_frequency(signal: NDArray[np.float64], fs: float) -> float:
    """Пик в 45–55 Гц с Hann и параболической интерполяцией."""
    n = int(signal.size)
    if n < 1024:
        return float(NOMINAL_GRID_HZ)
    windowed = signal * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    mask = (freqs >= 40.0) & (freqs <= 60.0)
    idx = np.nonzero(mask)[0]
    if idx.size < 3:
        return float(NOMINAL_GRID_HZ)
    sub = spectrum[idx]
    peak = int(np.argmax(sub))
    # global bin with max
    k = int(idx[peak])
    if k <= 0 or k >= spectrum.size - 1:
        return float(freqs[k])
    # parabolic interpolation
    a, b, c = float(spectrum[k - 1]), float(spectrum[k]), float(spectrum[k + 1])
    denom = a - 2 * b + c
    delta = 0.0 if abs(denom) < 1e-12 else 0.5 * (a - c) / denom
    # delta in bins
    bin_hz = freqs[1] - freqs[0]
    return float(freqs[k] + delta * bin_hz)


def _resampled_window(
    signal: NDArray[np.float64], fs: float, f_est: float, index: int, n_nominal: int
) -> NDArray[np.float64]:
    """Resample 10 циклов с f_est к n_nominal точкам линейной интерполяцией."""
    dur_actual = 10.0 / float(f_est)
    start = index * dur_actual * fs
    end = (index + 1) * dur_actual * fs
    # linspace source positions (fractional)
    src_pos = np.linspace(start, end, n_nominal, endpoint=False)
    # interpolate; src indices
    integers = np.arange(signal.size, dtype=np.float64)
    # clip to bounds
    clipped = np.clip(src_pos, 0, signal.size - 1 - 1e-9)
    # linear interpolation via np.interp on each point uses piecewise linear
    # use np.interp with integers as x
    return np.interp(clipped, integers, signal).astype(np.float64)


def _window_metrics(
    window: NDArray[np.float64], *_: object
) -> tuple[float, float, tuple[float, ...], tuple[float, ...]]:
    """Считает subgroups, IHG, THD для одного окна (rectangular sync)."""
    n = int(window.size)
    spectrum = np.fft.rfft(window)
    # RMS per bin: |X|*sqrt2/N for k>0
    mag = np.abs(spectrum).astype(np.float64)
    rms = mag * math.sqrt(2.0) / float(n)
    rms[0] /= math.sqrt(2.0)  # DC
    if rms.size > 1:
        rms[-1] /= 1.0 if n % 2 == 0 else 1.0  # Nyquist already correct for sqrt2? keep
        # For even N Nyquist is real-only, our sqrt2 overestimates by sqrt2, correct:
        if n % 2 == 0:
            rms[-1] /= math.sqrt(2.0)
    # number of bins
    # subgroups H1..40
    h_sub: list[float] = []
    for h in range(1, H_MAX + 1):
        center = h * DFT_BINS_PER_HARMONIC
        if center >= rms.size:
            h_sub.append(0.0)
            continue
        lo = max(0, center - 1)
        hi = min(rms.size - 1, center + 1)
        energy = float(np.sum(rms[lo : hi + 1] ** 2))
        h_sub.append(math.sqrt(energy))
    # IHG 39 groups between H
    ihg: list[float] = []
    for h in range(1, H_MAX):
        c1 = h * DFT_BINS_PER_HARMONIC
        c2 = (h + 1) * DFT_BINS_PER_HARMONIC
        lo = c1 + 2
        hi = c2 - 2
        if lo >= rms.size or hi < lo:
            ihg.append(0.0)
            continue
        lo = max(0, lo)
        hi = min(rms.size - 1, hi)
        energy = float(np.sum(rms[lo : hi + 1] ** 2))
        ihg.append(math.sqrt(energy))
    # THD: sqrt(sum h=2..40)/h1
    h1 = float(h_sub[0]) if h_sub else 0.0
    if h1 < 1e-12:
        thd = 0.0
        fund = h1
    else:
        sum_sq = float(np.sum(np.asarray(h_sub[1:]) ** 2))
        thd = math.sqrt(sum_sq) / h1
        fund = h1
    return fund, thd, tuple(h_sub), tuple(ihg)


def compute_harmonics(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    settings: HarmonicsSettings | None = None,
) -> HarmonicsInventory:
    """Инвентаризирует гармоники 12×200 мс с sync-resample, subgroups суммой ±1 bin."""
    n = _validate(samples, sample_rate_hz)
    if settings is None:
        settings = harmonics_preset()
    fs = float(sample_rate_hz)
    n_nominal = int(round(WINDOW_DURATION_S * fs))
    needed = int(round(RECORD_DURATION_S * fs))
    if n < needed:
        raise InputError("гармоники: запись короче 2.4 с")
    # truncate to first 2.4s nominal for bounded work
    signal = np.asarray(samples[:needed], dtype=np.float64)
    # estimate grid
    f_est = _estimate_grid_frequency(signal, fs)
    # clamp to plausible
    if not math.isfinite(f_est) or not 40.0 < f_est < 70.0:
        f_est = float(NOMINAL_GRID_HZ)
    # build windows
    windows: list[HarmonicsWindow] = []
    for idx in range(WINDOW_COUNT):
        resampled = _resampled_window(signal, fs, f_est, idx, n_nominal)
        fund, thd, h_sub, ihg = _window_metrics(resampled)
        windows.append(
            HarmonicsWindow(
                index=idx,
                start_time_s=idx * WINDOW_DURATION_S,
                fundamental_rms=float(fund),
                thd=float(thd),
                h_subgroups=tuple(float(v) for v in h_sub),
                ihg=tuple(float(v) for v in ihg),
            )
        )
        # bounded check
        _ = BIN_HZ
    return HarmonicsInventory(
        schema_version=HARMONICS_VERSION,
        settings_hash=harmonics_settings_hash(settings),
        settings=settings,
        sample_rate_hz=fs,
        estimated_grid_frequency_hz=float(f_est),
        record_duration_s=float(RECORD_DURATION_S),
        window_count=int(WINDOW_COUNT),
        windows=tuple(windows),
    )
