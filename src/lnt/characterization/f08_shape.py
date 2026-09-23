"""Объявленные гейты F08 и первичные морфологические меры по спану события."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.characterization.f08_result import InitialSeed

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]

LOCKED_BASELINE: Final = "linear_detrend"

_MODE_RELATIVE_LEVEL_DB: Final = 15.0
_MODE_PEAK_DISTANCE_BINS: Final = 2
_ENVELOPE_PERIOD_FRACTION: Final = 0.75
_RISE_LOW: Final = 0.1
_RISE_HIGH: Final = 0.9
_MINIMUM_SPAN_SAMPLES: Final = 2
_MINIMUM_ENVELOPE_PEAKS: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class Gates:
    """Объявленные гейты рецепта, собранные в одно значение."""

    rate_hz: float
    ringing_low_hz: float
    ringing_high_hz: float
    tau_min_samples: int
    tau_max_s: float
    amplitude_multiple: float
    phase_low_rad: float
    phase_high_rad: float
    maximum_evaluations: int
    minimum_snr_db: float
    residual_fraction_max: float
    minimum_zero_crossings: int
    maximum_events: int

    @property
    def nyquist_hz(self) -> float:
        """Верхняя граница звонка, зажатая пределом Найквиста."""
        return min(self.ringing_high_hz, self.rate_hz / 2.0)

    @property
    def tau_floor_s(self) -> float:
        """Нижняя граница постоянной затухания в объявленных отсчётах."""
        return self.tau_min_samples / self.rate_hz


def gate_band(gates: Gates) -> tuple[float, float]:
    """Объявленная полоса звонка: конечная, неотрицательная, ниже Найквиста."""
    low = gates.ringing_low_hz
    high = gates.nyquist_hz
    if not (math.isfinite(low) and math.isfinite(high) and low >= 0.0):
        raise ValueError("ringing band must be finite and nonnegative")
    return low, high


def validate_gates(gates: Gates) -> None:  # noqa: C901 - один предикат на каждое объявление
    """Невалидные объявления — ValueError; внесловарные состояния не бросают исключений."""
    if not math.isfinite(gates.rate_hz) or gates.rate_hz <= 0.0:
        raise ValueError("sample rate must be positive and finite")
    band = gate_band(gates)
    if not band[0] < band[1]:
        raise ValueError("ringing band must be ordered and below nyquist")
    if gates.tau_min_samples <= 0:
        raise ValueError("decay_time_minimum_samples must be positive")
    if not math.isfinite(gates.tau_max_s) or gates.tau_max_s <= gates.tau_floor_s:
        raise ValueError("decay_time_max_s must exceed the sample-grid floor")
    if not math.isfinite(gates.amplitude_multiple) or gates.amplitude_multiple <= 0.0:
        raise ValueError("amplitude maximum multiple must be positive and finite")
    if not (
        math.isfinite(gates.phase_low_rad)
        and math.isfinite(gates.phase_high_rad)
        and gates.phase_low_rad < gates.phase_high_rad
    ):
        raise ValueError("phase bounds must be finite and ordered")
    if gates.maximum_evaluations <= 0:
        raise ValueError("maximum_function_evaluations must be positive")
    if gates.maximum_events <= 0:
        raise ValueError("maximum_events must be positive")
    if not math.isfinite(gates.minimum_snr_db):
        raise ValueError("minimum_snr_db must be finite")
    if not math.isfinite(gates.residual_fraction_max) or gates.residual_fraction_max < 0.0:
        raise ValueError("residual_fraction_max must be finite and nonnegative")
    if gates.minimum_zero_crossings < 0:
        raise ValueError("minimum_zero_crossings must be nonnegative")


def guard_span_bounds(start_sample: int, end_sample: int, sample_count: int) -> tuple[int, int]:
    """Границы окна детренда: спан плюс одна его длительность с каждой стороны.

    Спека:396-397 требует guard в одну длительность события с каждой стороны;
    на границе записи guard клиппится, потому что за конец записи отсчётов нет.
    """
    length = end_sample - start_sample + 1
    return max(0, start_sample - length), min(sample_count, end_sample + 1 + length)


def zero_crossings(values: Float64Array) -> int:
    """Число смен знака: границы колебаний, из которых берётся f_d."""
    signs = np.signbit(values)
    return int(np.count_nonzero(signs[1:] != signs[:-1]))


def rise_time(values: Float64Array, rate_hz: float, v_peak: float) -> float | None:
    """Время от первого пересечения 0.1 пика до первого пересечения 0.9 пика."""
    level = np.abs(values) / v_peak
    low = np.flatnonzero(level >= _RISE_LOW)
    high = np.flatnonzero(level >= _RISE_HIGH)
    if low.size == 0 or high.size == 0:
        return None
    return float(int(high[0]) - int(low[0])) / rate_hz


def snr_db(snr_ratio: float) -> float:
    """SNR события в децибелах; неположительное отношение не несёт сигнала вовсе."""
    ratio = float(snr_ratio)
    return 20.0 * math.log10(ratio) if ratio > 0.0 else -math.inf


def decay_seed(
    values: Float64Array, rate_hz: float, f_d_hz: float
) -> tuple[float | None, float | None]:
    """Средний логарифмический декремент и постоянная tau из пиков огибающей."""
    distance = max(1, round(_ENVELOPE_PERIOD_FRACTION * rate_hz / f_d_hz))
    envelope = np.abs(values)
    peaks, _ = signal.find_peaks(envelope, distance=distance)
    peaks = peaks[peaks < values.size - 1]
    magnitudes = envelope[peaks]
    magnitudes = magnitudes[magnitudes > 0.0]
    if peaks.size < _MINIMUM_ENVELOPE_PEAKS or magnitudes.size < _MINIMUM_ENVELOPE_PEAKS:
        return None, None
    delta = float(np.mean(-np.diff(np.log(magnitudes))))
    if not math.isfinite(delta) or delta <= 0.0:
        return None, None
    return delta, (1.0 / f_d_hz) / delta


def initial_damped_sinusoid_seed(  # noqa: PLR0913 - объявленные границы рецепта явны
    span: FloatInput,
    *,
    sample_rate_hz: float,
    ringing_frequency_low_hz: float,
    ringing_frequency_high_hz: float,
    decay_time_minimum_samples: int,
    decay_time_max_s: float,
) -> InitialSeed:
    """Шаг 2 спеки:399-400 — частота по пересечениям нуля, tau по декременту.

    ``f_d`` берётся из числа пересечений нуля ``n_zc`` как ``fs n_zc / (2 L)``,
    ``tau_d`` — из среднего логарифмического декремента
    ``delta = ln(a_n / a_{n+1})`` последовательных пиков огибающей. Когда декремент
    не измеряется (меньше двух пиков, неположительный или неконечный ``delta``) или
    выходит за объявленные границы ``tau_d``, инициализации нет: это отказ, а не
    значение.
    """
    values = np.asarray(span, dtype=np.float64)
    rate = float(sample_rate_hz)
    if not math.isfinite(rate) or rate <= 0.0:
        raise ValueError("sample rate must be positive and finite")
    count = zero_crossings(values)
    if values.size < _MINIMUM_SPAN_SAMPLES:
        return InitialSeed(n_zc=count, f_d_hz=None, log_decrement=None, tau_d_s=None)
    high_hz = min(float(ringing_frequency_high_hz), rate / 2.0)
    f_seed = min(max(rate * count / (2.0 * values.size), float(ringing_frequency_low_hz)), high_hz)
    delta, tau_d = decay_seed(values, rate, f_seed)
    floor_s = int(decay_time_minimum_samples) / rate
    if tau_d is None or not floor_s <= tau_d <= float(decay_time_max_s):
        return InitialSeed(n_zc=count, f_d_hz=f_seed, log_decrement=delta, tau_d_s=None)
    return InitialSeed(n_zc=count, f_d_hz=f_seed, log_decrement=delta, tau_d_s=tau_d)


def mode_count(span: Float64Array, rate_hz: float, low_hz: float, high_hz: float) -> int:
    """Число разрешённых мод: сильные пики спектра спана в объявленной полосе.

    Спека:404-405 требует ``multimode`` при более чем одной разрешённой моде, но
    правила разрешения не даёт; правило и его границы зафиксированы решением
    F08-12 (относительный уровень 15 дБ, расстояние 2 бина).
    """
    size = int(span.size)
    window = np.asarray(signal.get_window("hann", size, fftbins=True), dtype=np.float64)
    magnitude = np.abs(np.fft.rfft(span * window))
    grid = np.fft.rfftfreq(size, d=1.0 / rate_hz)
    band = np.where((grid >= low_hz) & (grid <= high_hz), magnitude, 0.0)
    peaks, _ = signal.find_peaks(band, distance=_MODE_PEAK_DISTANCE_BINS)
    if peaks.size < _MINIMUM_ENVELOPE_PEAKS:
        return int(peaks.size)
    ceiling = float(band[peaks].max())
    floor = ceiling * 10.0 ** (-_MODE_RELATIVE_LEVEL_DB / 20.0)
    return int(np.count_nonzero(band[peaks] >= floor))
