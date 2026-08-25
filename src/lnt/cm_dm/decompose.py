"""Чистая математика CM/DM-декомпозиции усреднённых спектров (план CM/DM, задача T2).

Вход — сегментно-усреднённые автоспектры каналов L/N и их комплексный взаимный
спектр; выход — PSD синфазной (CM) и дифференциальной (DM) составляющих плюс
дебиасированная оценка magnitude-squared coherence. Модуль не знает ни про
файлы, ни про acquisition: только numpy-массивы.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy import signal

Float64Array = NDArray[np.float64]
ComplexArray = NDArray[np.complex128]
BoolArray = NDArray[np.bool_]

Mode = Literal["cm", "dm"]

# Нижняя граница полосы проводимых помех по CISPR 16-2-1.
CM_DM_LOW_HZ = 9_000.0

DEFAULT_MAX_PEAKS = 8
MIN_PROMINENCE_DB = 6.0
# Пол перед логарифмированием — те же соглашения, что в lnt.spectrum.
PSD_FLOOR = 1e-30


@dataclass(frozen=True, slots=True, kw_only=True)
class DecomposedSpectra:
    """Результат разложения: PSD CM/DM и дебиасированная когерентность."""

    cm_psd: Float64Array
    dm_psd: Float64Array
    coherence: Float64Array


@dataclass(frozen=True, slots=True, kw_only=True)
class PeakAttribution:
    """Пик, отнесённый к своему режиму (CM или DM)."""

    frequency_hz: float
    mode: Mode
    level_db: float


def decompose(
    s_ll: Float64Array,
    s_nn: Float64Array,
    s_ln_cplx: ComplexArray,
    segment_count: int,
) -> DecomposedSpectra:
    """Разлагает усреднённые спектры на CM/DM и считает дебиасированную когерентность.

    P_CM = (S_LL + S_NN + 2·Re S_LN)/4; P_DM = (S_LL + S_NN − 2·Re S_LN)/4.
    Когерентность дебиасируется по числу усреднений N:
    γ_adj = max(0, (N·γ̂ − 1)/(N − 1)); при N <= 1 и нулевых автоспектрах — 0.
    """
    ll = np.asarray(s_ll, dtype=np.float64)
    nn = np.asarray(s_nn, dtype=np.float64)
    ln = np.asarray(s_ln_cplx, dtype=np.complex128)
    total = ll + nn
    twice_re_ln = 2.0 * ln.real
    cm_psd = (total + twice_re_ln) / 4.0
    dm_psd = (total - twice_re_ln) / 4.0
    if segment_count <= 1:
        # Одно усреднение не даёт степени свободы: оценка несостоятельна.
        return DecomposedSpectra(
            cm_psd=cm_psd,
            dm_psd=dm_psd,
            coherence=np.zeros_like(cm_psd),
        )
    denominator = ll * nn
    gamma_hat = np.zeros_like(cm_psd)
    # Нулевой бин любого автоспектра => деление невозможно => когерентность 0.
    np.divide(np.abs(ln) ** 2, denominator, out=gamma_hat, where=denominator > 0.0)
    debiased = (segment_count * gamma_hat - 1.0) / (segment_count - 1.0)
    return DecomposedSpectra(
        cm_psd=cm_psd,
        dm_psd=dm_psd,
        coherence=np.maximum(debiased, 0.0),
    )


def band_mask(frequency_hz: Float64Array, low_hz: float, high_hz: float) -> BoolArray:
    """Маска бинов внутри полосы [low_hz, high_hz] включительно."""
    freqs = np.asarray(frequency_hz, dtype=np.float64)
    return (freqs >= low_hz) & (freqs <= high_hz)


def band_rms(
    psd: Float64Array,
    frequency_hz: Float64Array,
    low_hz: float,
    high_hz: float,
) -> float:
    """RMS полосы: sqrt интеграла PSD по маске, численно трапецией."""
    freqs = np.asarray(frequency_hz, dtype=np.float64)
    values = np.asarray(psd, dtype=np.float64)
    mask = band_mask(freqs, low_hz, high_hz)
    band_power = float(np.trapezoid(values[mask], freqs[mask]))
    return math.sqrt(max(band_power, 0.0))


def _peak_candidates(
    psd_db: Float64Array,
    *,
    min_prominence_db: float,
) -> list[tuple[float, int]]:
    """Ищет пики в dB-домене: возвращает пары (prominence_db, индекс бина)."""
    indices_raw, props = signal.find_peaks(psd_db, prominence=min_prominence_db)
    indices = np.asarray(indices_raw, dtype=np.intp)
    prominences = np.asarray(props["prominences"], dtype=np.float64)
    return [
        (float(prominences[position]), int(indices[position])) for position in range(indices.size)
    ]


def pick_peaks(
    frequency_hz: Float64Array,
    cm_psd: Float64Array,
    dm_psd: Float64Array,
    max_peaks: int = DEFAULT_MAX_PEAKS,
    min_prominence_db: float = MIN_PROMINENCE_DB,
) -> list[PeakAttribution]:
    """Ищет пики в обоих спектрах и относит каждый к своему режиму, топ по prominence.

    Соглашения те же, что в lnt.spectrum: домен 10·log10 с полом PSD_FLOOR,
    порог prominence в дБ, сортировка по убыванию prominence.
    """
    freqs = np.asarray(frequency_hz, dtype=np.float64)
    spectra: tuple[tuple[Mode, Float64Array], ...] = (("cm", cm_psd), ("dm", dm_psd))
    tagged: list[tuple[float, Mode, int, float]] = []
    for mode, psd in spectra:
        values = np.asarray(psd, dtype=np.float64)
        psd_db = 10.0 * np.log10(np.maximum(values, PSD_FLOOR))
        for prominence_db, index in _peak_candidates(psd_db, min_prominence_db=min_prominence_db):
            tagged.append((prominence_db, mode, index, float(psd_db[index])))
    tagged.sort(key=lambda item: item[0], reverse=True)
    return [
        PeakAttribution(
            frequency_hz=float(freqs[index]),
            mode=mode,
            level_db=level_db,
        )
        for _, mode, index, level_db in tagged[:max_peaks]
    ]
