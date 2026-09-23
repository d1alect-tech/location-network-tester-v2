"""F07 two_window_real_cepstrum_and_sideband_symmetry поверх одиночного кадра."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray
from scipy.signal import get_window

from lnt.characterization.f07_result import (
    BELOW_RESOLUTION,
    HARMONIC_COMB_ONLY,
    LOG_FLOOR_UNSTABLE,
    METHOD,
    NO_DOMINANT_QUEFRENCY,
    WINDOW_DEPENDENT,
    F07Result,
    _unavailable,
)
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f01_phase_cycle import F01Result

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]

_PROMINENCE_RATIO_MIN: Final = 10.0
_RESOLUTION_BINS: Final = 2.0
_SECOND_FLOOR_DELTA_DB: Final = 20.0
_INVARIANCE_WINDOW_COUNT: Final = 2
_AUTOCORR_HALF_MAX: Final = 0.5
_MIN_AUTOCORR_LAGS: Final = 3

__all__ = ["METHOD", "F07Result", "compute_f07_comb_cepstrum"]


def compute_f07_comb_cepstrum(  # noqa: C901, PLR0911, PLR0912, PLR0913 - гейты рецепта
    samples: FloatInput,
    *,
    sample_rate_hz: float,
    f01_result: F01Result | None,
    fft_samples: int,
    windows: Sequence[str],
    log_floor_db_below_maximum: float,
    minimum_quefrency_samples: int,
    offset_bins: Sequence[int],
    spacing_crosscheck: str,
    window_peak_tolerance_bins: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F07Result:
    """Шаг несущей, симметрия боковых и вещественный кепстр одного кадра.

    Вещественный кепстр ``c[q] = Re(IFFT(log|X| - mean))`` с полом ``floor``
    как объявленной долей ``max|X|`` (спека:344-351). Пик ``q*`` в зоне
    ``[q_lo, N//2]`` даёт шаг ``df = fs / q*`` (спека:352-354). Двухоконный
    протокол бракует пик, сдвинувшийся между Hann и Blackman
    (``window_dependent``), гребёнку сети — по ``f1`` из F01
    (``harmonic_comb_only``), шаг на границе разрешения бана (``below_resolution``),
    слабый или двинувшийся под полом пик (``no_dominant_quefrency`` /
    ``log_floor_unstable``).
    """
    if checkpoint is not None:
        checkpoint()
    rate = float(sample_rate_hz)
    if not math.isfinite(rate) or rate <= 0.0:
        raise ValueError("sample rate must be positive and finite")
    nfft = int(fft_samples)
    if nfft <= 0:
        raise ValueError("fft_samples must be positive")
    # Объявленный бюджет не расходуется: работа O(N log N) (спека:375), нечего лимитировать.
    _ = resources
    # Кроссчек залочен magnitude_spectrum_autocorrelation (contract.py); иной путь
    # не реализуется, параметр вычитывается, но всегда идёт один и тот же АКФ-кроссчек.
    _ = spacing_crosscheck
    f1 = f01_result.f1_hz if f01_result is not None else None
    if f1 is None or not math.isfinite(float(f1)) or float(f1) <= 0.0:
        return _unavailable((HARMONIC_COMB_ONLY,))
    frame = _frame(np.asarray(samples, dtype=np.float64), nfft)
    window_names = tuple(windows)
    if not window_names:
        return _unavailable((NO_DOMINANT_QUEFRENCY,))
    floor_db = float(log_floor_db_below_maximum)
    min_q = int(minimum_quefrency_samples)
    tol = int(window_peak_tolerance_bins)
    offsets = tuple(int(j) for j in offset_bins)

    primary = _analyze(frame, window_names[0], nfft, floor_db, min_q)
    if primary.dominant is None:
        return _unavailable((NO_DOMINANT_QUEFRENCY,))
    q_primary = primary.dominant[0]
    ratio_primary = primary.dominant[1]
    amplitude_primary = primary.dominant[2]

    if len(window_names) >= _INVARIANCE_WINDOW_COUNT:
        second = _analyze(frame, window_names[1], nfft, floor_db, min_q)
        q_second = second.dominant[0] if second.dominant is not None else None
        if q_second is None or abs(q_second - q_primary) > tol:
            return _unavailable((WINDOW_DEPENDENT,))

    q_f1 = round(rate / float(f1))
    if abs(q_primary - q_f1) <= tol:
        return _unavailable((HARMONIC_COMB_ONLY,))

    raised = _analyze(frame, window_names[0], nfft, floor_db + _SECOND_FLOOR_DELTA_DB, min_q)
    q_raised = raised.dominant[0] if raised.dominant is not None else None
    if q_raised is not None and abs(q_raised - q_primary) > tol:
        return _unavailable((LOG_FLOOR_UNSTABLE,))

    if ratio_primary < _PROMINENCE_RATIO_MIN:
        return _unavailable((NO_DOMINANT_QUEFRENCY,))

    df_hz = rate / float(q_primary)
    bin_resolution = rate / float(nfft)
    if df_hz <= _RESOLUTION_BINS * bin_resolution:
        return _unavailable((BELOW_RESOLUTION,))

    crosscheck_lag = _spectrum_autocorrelation_lag(primary.spectrum)
    expected_lag = float(nfft) / float(q_primary)
    if crosscheck_lag is None or abs(float(crosscheck_lag) - expected_lag) > float(tol):
        return _unavailable((NO_DOMINANT_QUEFRENCY,))

    carrier_bin = int(np.argmax(primary.spectrum[1:]) + 1)
    sym_db = _sideband_symmetry_db(primary.spectrum, carrier_bin, offsets)
    return F07Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        df_hz=df_hz,
        sym_db=sym_db,
        q_s=float(q_primary) / rate,
        quefrency_amplitude=amplitude_primary,
        carrier_bin=carrier_bin,
        sample_count=1,
        observation_count=1,
        missing_count=0,
        stored_count=1,
    )


class _WindowAnalysis:
    """Промежуточный результат анализа одного окна: кепстр, спектр, доминанта."""

    __slots__: Final = ("dominant", "spectrum")

    spectrum: Float64Array
    dominant: tuple[int, float, float] | None

    def __init__(self, spectrum: Float64Array, dominant: tuple[int, float, float] | None) -> None:
        self.spectrum = spectrum
        self.dominant = dominant


def _frame(raw: Float64Array, nfft: int) -> Float64Array:
    """Ведущий сегмент записи, дополненный нулями до ``nfft``."""
    frame = np.zeros(nfft, dtype=np.float64)
    taken = min(int(raw.size), nfft)
    frame[:taken] = raw[:taken]
    return frame


def _analyze(
    frame: Float64Array,
    name: str,
    nfft: int,
    floor_db: float,
    minimum_quefrency: int,
) -> _WindowAnalysis:
    """Оконный анализ: спектр ``|X|``, вещественный кепстр и доминантный пик."""
    window = np.asarray(get_window(name, nfft, fftbins=True), dtype=np.float64)
    framed = frame * window
    spectrum = np.abs(np.fft.rfft(framed))
    width = _autocorrelation_half_width(framed)
    q_lo = max(int(minimum_quefrency), width)
    q_hi = nfft // 2
    maximum = float(np.max(spectrum))
    if q_lo >= q_hi or maximum <= 0.0 or not math.isfinite(maximum):
        return _WindowAnalysis(spectrum, None)
    floor = maximum * float(10.0 ** (-floor_db / 20.0))
    level = np.log(spectrum + floor)
    level -= float(np.mean(level))
    cepstrum = np.fft.irfft(level, n=nfft)
    band = np.abs(cepstrum[q_lo : q_hi + 1])
    if band.size == 0 or not bool(np.any(band > 0.0)):
        return _WindowAnalysis(spectrum, None)
    q_star = int(np.argmax(band)) + q_lo
    ordered = np.sort(band)
    index = min(int(ordered.size * 0.99), ordered.size - 1)
    reference = float(ordered[index])
    ratio = float(ordered[-1]) / reference if reference > 0.0 else 0.0
    peak = float(cepstrum[q_star])
    return _WindowAnalysis(spectrum, (q_star, ratio, peak))


def _autocorrelation_half_width(framed: Float64Array) -> int:
    """Ширина главного лепестка АКФ: первый лаг падения нормированной АКФ ниже 0.5."""
    n = int(framed.size)
    autocorr = np.correlate(framed, framed, "full")[n - 1 :]
    autocorr = autocorr / autocorr[0]
    below = np.where(autocorr[1:] <= _AUTOCORR_HALF_MAX)[0]
    return int(below[0]) + 1 if below.size else n


def _spectrum_autocorrelation_lag(spectrum: Float64Array) -> int | None:
    """Лаг первого доминирующего пика автокорреляции модуля спектра."""
    centered = spectrum - float(np.mean(spectrum))
    autocorr = np.correlate(centered, centered, "full")[spectrum.size - 1 :]
    if autocorr.size < _MIN_AUTOCORR_LAGS or autocorr[0] <= 0.0:
        return None
    autocorr = autocorr / autocorr[0]
    return int(np.argmax(autocorr[1:]) + 1)


def _sideband_symmetry_db(
    spectrum: Float64Array, carrier_bin: int, offset_bins: Sequence[int]
) -> float | None:
    """Среднее по объявленным смещениям ``10 log10(P[k0+j] / P[k0-j])``."""
    power = spectrum**2
    usable = [j for j in offset_bins if carrier_bin - j >= 0 and carrier_bin + j < spectrum.size]
    if not usable:
        return None
    ratios: list[float] = []
    for j in usable:
        ratio = float(power[carrier_bin + j] / power[carrier_bin - j])
        ratios.append(10.0 * math.log10(ratio) if ratio > 0.0 else math.nan)
    if not ratios or not all(math.isfinite(value) for value in ratios):
        return None
    return float(np.mean(ratios))
