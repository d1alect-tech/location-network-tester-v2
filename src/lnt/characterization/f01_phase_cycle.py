"""F01 synchronous relative harmonic DFT over every complete qualified window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.records import Status
from lnt.harmonics.constants import (
    EPS_LEVEL,
    GRID_SEARCH_HIGH_HZ,
    GRID_SEARCH_LOW_HZ,
    NOMINAL_GRID_HZ,
)

METHOD: Final = "synchronous_relative_harmonic_dft"
WINDOW_S: Final = 0.2
MIN_WINDOW_COUNT: Final = 12
CYCLES_PER_WINDOW: Final = 10
MAXIMUM_HARMONIC_ORDER: Final = 40
PHASE_RESULTANT_MIN: Final = 0.8
H1_CONCENTRATION_RATIO_MIN: Final = 0.95
GRID_BAND_LOW_HZ: Final = 47.5
GRID_BAND_HIGH_HZ: Final = 52.5

_BIN_WIDTH_HZ: Final = 5.0
_MIN_PEAK_SEARCH_BINS: Final = 3
_CONCENTRATION_NEIGHBOR_BINS: Final = 3
_FUNDAMENTAL_ABSENT_BIN_LEVEL: Final = 1e-3
_TEMPLATE_SAMPLES: Final = 1000

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type ComplexArray = NDArray[np.complex128]

__all__ = [
    "CYCLES_PER_WINDOW",
    "GRID_BAND_HIGH_HZ",
    "GRID_BAND_LOW_HZ",
    "H1_CONCENTRATION_RATIO_MIN",
    "MAXIMUM_HARMONIC_ORDER",
    "METHOD",
    "MIN_WINDOW_COUNT",
    "PHASE_RESULTANT_MIN",
    "WINDOW_S",
    "F01Result",
    "compute_f01_phase_cycle",
    "estimate_grid_frequency_quinn_fernandes",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class F01Result:
    """Bounded F01 outcome over every complete qualified window."""

    status: Status
    reason_codes: tuple[str, ...]
    f1_hz: float | None
    c_k_v: ComplexArray | None
    phi_rel_k_rad: Float64Array | None
    phase_resultant_k: Float64Array | None
    x_template_v: Float64Array | None
    window_count: int
    evaluated_window_count: int


def estimate_grid_frequency_quinn_fernandes(
    window: FloatInput,
    *,
    sample_rate_hz: float,
    detrend: bool = True,
) -> float:
    """Estimate grid frequency with one Quinn-Fernandes refinement step."""
    signal = np.asarray(window, dtype=np.float64)
    n = int(signal.size)
    signal = signal - float(np.mean(signal)) if detrend else signal
    freqs = np.fft.rfftfreq(n, d=1.0 / float(sample_rate_hz))
    # Quinn-Fernandes on the complex rectangular spectrum [QUINN91, Fredenhagen
    # form]: Hann peak selects the bin, complex ratios give the fraction.
    rect = np.fft.rfft(signal)
    freqs_rect = freqs
    hann = np.abs(np.fft.rfft(signal * np.hanning(n)))
    idx_h = np.nonzero((freqs >= GRID_SEARCH_LOW_HZ) & (freqs <= GRID_SEARCH_HIGH_HZ))[0]
    if idx_h.size < _MIN_PEAK_SEARCH_BINS:
        return float(NOMINAL_GRID_HZ)
    kh = int(idx_h[int(np.argmax(hann[idx_h]))])
    k = int(np.argmin(np.abs(freqs_rect - freqs[kh])))
    if k <= 0 or k >= rect.size - 1:
        return float(freqs_rect[k])
    center = rect[k]
    if abs(center) < EPS_LEVEL:
        return float(freqs_rect[k])
    ratio_next = rect[k + 1] / center
    ratio_prev = rect[k - 1] / center
    denom = 2.0 - ratio_next - ratio_prev
    if abs(denom) < EPS_LEVEL:
        return float(freqs_rect[k])
    delta = (ratio_prev - ratio_next) / denom
    return float(freqs_rect[k] + float(delta.real) * (freqs_rect[1] - freqs_rect[0]))


def _resampled_window(
    signal: Float64Array,
    fs: float,
    f1: float,
    start_sample: int,
    n_nominal: int,
) -> Float64Array:
    """Resample exactly 10 cycles from ``start_sample`` by linear interpolation."""
    span = CYCLES_PER_WINDOW / f1 * fs
    source = np.linspace(
        float(start_sample),
        float(start_sample) + span,
        n_nominal,
        endpoint=False,
    )
    clipped = np.clip(source, 0.0, float(signal.size - 1) - 1e-9)
    indices = np.arange(signal.size, dtype=np.float64)
    return np.interp(clipped, indices, signal).astype(np.float64)


def _assess_window(
    win: Float64Array,
    fs: float,
) -> tuple[float | None, bool, bool]:
    """Return measured f1 plus grid-unstable and fundamental-absent flags."""
    centered = win - float(np.mean(win))
    raw_spec = np.fft.rfft(centered)
    freqs = np.fft.rfftfreq(win.size, d=1.0 / fs)
    search = (freqs >= GRID_SEARCH_LOW_HZ) & (freqs <= GRID_SEARCH_HIGH_HZ)
    idx = np.nonzero(search)[0]
    peak_level = float(np.max(np.abs(raw_spec[idx]))) if idx.size else 0.0
    if peak_level < _FUNDAMENTAL_ABSENT_BIN_LEVEL:
        return None, False, True
    f1 = estimate_grid_frequency_quinn_fernandes(win, sample_rate_hz=fs)
    if not GRID_BAND_LOW_HZ <= f1 <= GRID_BAND_HIGH_HZ:
        return f1, True, False
    hb = int(np.argmin(np.abs(freqs - f1)))
    if hb < 1 or hb >= raw_spec.size - 1:
        return f1, True, False
    lo = max(0, hb - _CONCENTRATION_NEIGHBOR_BINS)
    hi = min(int(raw_spec.size) - 1, hb + _CONCENTRATION_NEIGHBOR_BINS)
    total_energy = float(np.sum(np.abs(raw_spec[lo : hi + 1]) ** 2))
    center_energy = float(np.abs(raw_spec[hb]) ** 2)
    unstable = (
        total_energy > EPS_LEVEL and center_energy / total_energy < H1_CONCENTRATION_RATIO_MIN
    )
    return f1, unstable, False


def _average_windows(
    signal: Float64Array,
    fs: float,
    n_nominal: int,
    window_f1: list[float | None],
    f1_global: float,
) -> tuple[ComplexArray, Float64Array]:
    """Vector-average c_k and exp(j phi_rel) over windows with a fundamental."""
    orders = np.arange(1, MAXIMUM_HARMONIC_ORDER + 1)
    sum_c = np.zeros(MAXIMUM_HARMONIC_ORDER, dtype=np.complex128)
    sum_phase = np.zeros(MAXIMUM_HARMONIC_ORDER, dtype=np.complex128)
    for i, f1_i in enumerate(window_f1):
        if f1_i is None:
            continue
        start = i * n_nominal
        resampled = _resampled_window(signal, fs, f1_global, start, n_nominal)
        spec = np.fft.rfft(resampled)
        c_k = (2.0 / n_nominal) * spec[10 * orders]
        phi_rel = np.angle(spec[10 * orders]) - orders * np.angle(spec[10])
        phi_rel = phi_rel - (orders - 1) * (np.pi / 2.0)
        phi_rel = np.mod(phi_rel + np.pi, 2.0 * np.pi) - np.pi
        sum_c += c_k
        sum_phase += np.exp(1j * phi_rel)
    evaluated = sum(1 for value in window_f1 if value is not None)
    return sum_c / float(evaluated), np.abs(sum_phase) / float(evaluated)


def _relative_phase(avg_c: ComplexArray) -> Float64Array:
    """Return harmonic phases relative to the fundamental (sine basis)."""
    orders = np.arange(1, MAXIMUM_HARMONIC_ORDER + 1)
    phi_rel = np.angle(avg_c) - orders * np.angle(avg_c[0])
    phi_rel = phi_rel - (orders - 1) * (np.pi / 2.0)
    return np.mod(phi_rel + np.pi, 2.0 * np.pi) - np.pi


def _build_template(avg_c: ComplexArray) -> Float64Array:
    """Synthesize one aligned cycle from the vector-averaged coefficients."""
    theta = np.linspace(0.0, 2.0 * np.pi, _TEMPLATE_SAMPLES, endpoint=False)
    template = np.zeros(_TEMPLATE_SAMPLES, dtype=np.float64)
    for index in range(MAXIMUM_HARMONIC_ORDER):
        template += 2.0 * abs(avg_c[index]) * np.cos((index + 1) * theta + np.angle(avg_c[index]))
    return template


def _unavailable(codes: tuple[str, ...], total: int, evaluated: int) -> F01Result:
    """Return an unavailable F01 result with no fabricated values."""
    return F01Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        f1_hz=None,
        c_k_v=None,
        phi_rel_k_rad=None,
        phase_resultant_k=None,
        x_template_v=None,
        window_count=total,
        evaluated_window_count=evaluated,
    )


def compute_f01_phase_cycle(
    samples: FloatInput,
    *,
    sample_rate_hz: float,
    sync_reference: FloatInput | None,
) -> F01Result:
    """Evaluate every complete 0.2 s window of the qualified record."""
    if sync_reference is None:
        return _unavailable(("no_sync_reference",), 0, 0)
    signal = np.asarray(samples, dtype=np.float64)
    fs = float(sample_rate_hz)
    n_nominal = round(WINDOW_S * fs)
    total = int(np.floor(float(signal.size) / float(n_nominal)))
    if total < MIN_WINDOW_COUNT:
        return _unavailable(("window_too_short",), total, 0)

    window_f1: list[float | None] = []
    grid_unstable = 0
    fundamental_absent = 0
    for i in range(total):
        start = i * n_nominal
        f1, unstable, absent = _assess_window(signal[start : start + n_nominal], fs)
        if absent or f1 is None:
            fundamental_absent += 1
            window_f1.append(None)
            continue
        if unstable:
            grid_unstable += 1
        window_f1.append(f1)

    codes: list[str] = []
    if fundamental_absent:
        codes.append("fundamental_absent")
    if grid_unstable:
        codes.append("grid_unstable")
    f1_values = [float(value) for value in window_f1 if value is not None]
    if not f1_values:
        return _unavailable(tuple(codes), total, 0)
    f1_global = float(np.median(f1_values))

    avg_c, resultant = _average_windows(signal, fs, n_nominal, window_f1, f1_global)
    if float(np.min(resultant)) < PHASE_RESULTANT_MIN:
        codes.append("phase_unstable")
    status = Status.AVAILABLE if not codes else Status.PARTIAL
    evaluated = sum(1 for value in window_f1 if value is not None)
    return F01Result(
        status=status,
        reason_codes=tuple(codes),
        f1_hz=f1_global,
        c_k_v=avg_c,
        phi_rel_k_rad=_relative_phase(avg_c),
        phase_resultant_k=resultant,
        x_template_v=_build_template(avg_c),
        window_count=total,
        evaluated_window_count=evaluated,
    )
