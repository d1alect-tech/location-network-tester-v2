"""Качество сети 50 Гц по трансформаторному входу CH1: THD, гармоники, RMS.

Сигнал — вторичка трансформатора 230:6 (реальные вольты, пробник уже учтён
при масштабировании). Тракт: децимация до ~40 кГц -> Hann + rfft ->
фундаментал в полосе сети (параболическая интерполяция) -> гармоники H2..H40.
RMS и crest-factor считаются по сырым отсчётам (выбросы не теряются),
огибающая — по перициклным вершинам НЧ-фильтрованного сигнала (без выбросов).
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.errors import AnalysisError

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]

TARGET_DECIMATED_RATE_HZ = 40_000.0
MAX_HARMONIC_ORDER = 40
FUNDAMENTAL_SEARCH_HALF_WIDTH_HZ = 10.0
HARMONIC_SEARCH_HALF_WIDTH_HZ = 3.0
MIN_FUNDAMENTAL_RMS_V = 0.05
MIN_LINE_HZ = 40.0
MAX_LINE_HZ = 70.0
MIN_CYCLES = 20
ENVELOPE_LOWPASS_HZ = 100.0
ENVELOPE_FILTER_ORDER = 4
EPS = 1e-30


@dataclass(frozen=True, slots=True, kw_only=True)
class LineHarmonic:
    """Одна гармоника сети: порядок, частота, амплитуда и доля от фундаментала."""

    order: int
    frequency_hz: float
    amplitude_v: float
    ratio: float


@dataclass(frozen=True, slots=True, kw_only=True)
class LineQualityMetrics:
    """Метрики качества синусоиды сети одной line-quality сессии."""

    fundamental_hz: float
    fundamental_rms_v: float
    total_rms_v: float
    thd_ratio: float
    crest_factor: float
    envelope_cv: float
    cycles_analyzed: int
    harmonics: tuple[LineHarmonic, ...]


def compute_line_quality(
    ch1: Float32Array,
    *,
    sample_rate_hz: float,
    nominal_line_hz: float = 50.0,
) -> LineQualityMetrics:
    """Считает частоту, RMS, THD, гармоники, crest-factor и огибающую сети."""
    raw = ch1.astype(np.float64)
    if raw.size == 0:
        raise AnalysisError("line-quality: пустая запись CH1")
    total_rms = float(np.sqrt(np.mean(raw**2)))

    decimated, decimated_rate = _decimate(raw, sample_rate_hz)
    # Crest — по полосоограниченному (≤децимированному) сигналу: одиночные
    # сэмплы-выбросы (мусор старта захвата, импульсные помехи) не должны
    # выдаваться за форму синусоиды.
    peak = float(np.max(np.abs(decimated)))
    frequencies, amplitudes = _amplitude_spectrum(decimated, decimated_rate)

    fundamental_hz, fundamental_amplitude = _find_fundamental(
        frequencies,
        amplitudes,
        nominal_line_hz=nominal_line_hz,
    )
    fundamental_rms = fundamental_amplitude / np.sqrt(2.0)
    if fundamental_rms < MIN_FUNDAMENTAL_RMS_V:
        raise AnalysisError(
            f"сигнал сети слишком слаб: RMS {fundamental_rms:.4f} В < {MIN_FUNDAMENTAL_RMS_V} В",
        )

    harmonics = _collect_harmonics(
        frequencies,
        amplitudes,
        fundamental_hz=fundamental_hz,
        fundamental_amplitude=fundamental_amplitude,
        nyquist_hz=decimated_rate / 2.0,
    )
    thd_ratio = float(np.sqrt(sum(harmonic.ratio**2 for harmonic in harmonics)))

    envelope_cv, cycles_analyzed = _envelope_stability(decimated, decimated_rate)

    return LineQualityMetrics(
        fundamental_hz=fundamental_hz,
        fundamental_rms_v=float(fundamental_rms),
        total_rms_v=total_rms,
        thd_ratio=thd_ratio,
        crest_factor=peak / max(total_rms, EPS),
        envelope_cv=envelope_cv,
        cycles_analyzed=cycles_analyzed,
        harmonics=harmonics,
    )


def line_quality_to_payload(metrics: LineQualityMetrics) -> dict[str, object]:
    """Канонический JSON-вид метрик качества сети для metrics.json."""
    return {
        "fundamental_hz": metrics.fundamental_hz,
        "fundamental_rms_v": metrics.fundamental_rms_v,
        "total_rms_v": metrics.total_rms_v,
        "thd_ratio": metrics.thd_ratio,
        "crest_factor": metrics.crest_factor,
        "envelope_cv": metrics.envelope_cv,
        "cycles_analyzed": metrics.cycles_analyzed,
        "harmonics": [
            {
                "order": harmonic.order,
                "frequency_hz": harmonic.frequency_hz,
                "amplitude_v": harmonic.amplitude_v,
                "ratio": harmonic.ratio,
            }
            for harmonic in metrics.harmonics
        ],
    }


def _decimate(raw: Float64Array, sample_rate_hz: float) -> tuple[Float64Array, float]:
    factor = max(1, int(sample_rate_hz // TARGET_DECIMATED_RATE_HZ))
    if factor == 1:
        return raw, sample_rate_hz
    decimated = np.asarray(signal.resample_poly(raw, up=1, down=factor), dtype=np.float64)
    return decimated, sample_rate_hz / factor


def _amplitude_spectrum(
    samples: Float64Array,
    sample_rate_hz: float,
) -> tuple[Float64Array, Float64Array]:
    window = np.hanning(samples.size)
    spectrum = np.abs(np.fft.rfft(samples * window))
    amplitudes = spectrum * 2.0 / max(float(window.sum()), EPS)
    frequencies = np.fft.rfftfreq(samples.size, 1.0 / sample_rate_hz)
    return frequencies, amplitudes


def _hann_kernel(shift: float) -> float:
    """Амплитудный отклик окна Ханна на дробном смещении от центра бина."""
    if abs(shift) < EPS:
        return 1.0
    return float(np.sinc(shift) / (1.0 - shift**2))


def _interpolated_peak(
    frequencies: Float64Array,
    amplitudes: Float64Array,
    low_hz: float,
    high_hz: float,
) -> tuple[float, float] | None:
    """Частота/амплитуда пика по оценщику Грандке (точен для окна Ханна)."""
    low = int(np.searchsorted(frequencies, low_hz))
    high = int(np.searchsorted(frequencies, high_hz))
    if high - low < 1:
        return None
    local = int(np.argmax(amplitudes[low:high])) + low
    if local <= 0 or local >= amplitudes.size - 1:
        return None
    center = float(amplitudes[local])
    if center < EPS:
        return None
    left = float(amplitudes[local - 1])
    right = float(amplitudes[local + 1])
    direction = 1.0 if right >= left else -1.0
    neighbor = right if direction > 0 else left
    alpha = neighbor / center
    shift = direction * float(np.clip((2.0 * alpha - 1.0) / (1.0 + alpha), 0.0, 0.5))
    bin_width = float(frequencies[1] - frequencies[0])
    frequency = float(frequencies[local]) + shift * bin_width
    amplitude = center / max(_hann_kernel(shift), EPS)
    return frequency, amplitude


def _find_fundamental(
    frequencies: Float64Array,
    amplitudes: Float64Array,
    *,
    nominal_line_hz: float,
) -> tuple[float, float]:
    peak = _interpolated_peak(
        frequencies,
        amplitudes,
        nominal_line_hz - FUNDAMENTAL_SEARCH_HALF_WIDTH_HZ,
        nominal_line_hz + FUNDAMENTAL_SEARCH_HALF_WIDTH_HZ,
    )
    if peak is None:
        raise AnalysisError("line-quality: полоса поиска фундаментала пуста")
    frequency, amplitude = peak
    if not MIN_LINE_HZ <= frequency <= MAX_LINE_HZ:
        raise AnalysisError(
            f"line-quality: частота фундаментала {frequency:.1f} Гц вне диапазона сети",
        )
    global_peak = float(np.max(amplitudes[1:]))
    if amplitude < 0.5 * global_peak:
        raise AnalysisError(
            "в полосе сети нет доминирующего фундаментала — вход не похож на сеть 50 Гц",
        )
    return frequency, amplitude


def _collect_harmonics(
    frequencies: Float64Array,
    amplitudes: Float64Array,
    *,
    fundamental_hz: float,
    fundamental_amplitude: float,
    nyquist_hz: float,
) -> tuple[LineHarmonic, ...]:
    harmonics: list[LineHarmonic] = []
    for order in range(2, MAX_HARMONIC_ORDER + 1):
        target_hz = fundamental_hz * order
        if target_hz + HARMONIC_SEARCH_HALF_WIDTH_HZ >= nyquist_hz:
            break
        peak = _interpolated_peak(
            frequencies,
            amplitudes,
            target_hz - HARMONIC_SEARCH_HALF_WIDTH_HZ,
            target_hz + HARMONIC_SEARCH_HALF_WIDTH_HZ,
        )
        if peak is None:
            continue
        frequency, amplitude = peak
        harmonics.append(
            LineHarmonic(
                order=order,
                frequency_hz=frequency,
                amplitude_v=amplitude,
                ratio=amplitude / max(fundamental_amplitude, EPS),
            ),
        )
    return tuple(harmonics)


def _envelope_stability(samples: Float64Array, sample_rate_hz: float) -> tuple[float, int]:
    sos = signal.butter(
        ENVELOPE_FILTER_ORDER,
        ENVELOPE_LOWPASS_HZ,
        btype="lowpass",
        fs=sample_rate_hz,
        output="sos",
    )
    lowpassed = np.asarray(signal.sosfiltfilt(sos, samples), dtype=np.float64)
    below = lowpassed[:-1] <= 0.0
    above = lowpassed[1:] > 0.0
    crossings = np.nonzero(below & above)[0]
    cycle_count = crossings.size - 1
    if cycle_count < MIN_CYCLES:
        raise AnalysisError(
            f"line-quality: найдено {max(cycle_count, 0)} циклов сети, нужно >= {MIN_CYCLES}",
        )
    peaks = np.empty(cycle_count, dtype=np.float64)
    for index in range(cycle_count):
        segment = lowpassed[crossings[index] : crossings[index + 1] + 1]
        peaks[index] = float(np.max(np.abs(segment)))
    mean_peak = float(np.mean(peaks))
    return float(np.std(peaks, ddof=1)) / max(mean_peak, EPS), cycle_count
