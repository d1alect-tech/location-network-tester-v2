"""Канонические окна Welch-PSD: реестр, ENBW и когерентное усиление.

ENBW (эквивалентная шумовая полоса, в бинах) и когерентное усиление
выводятся только из весов окна::

    enbw_bins = N · Σw² / (Σw)²
    coherent_gain = Σw / N

Все окна периодические (``fftbins=True``) — стандарт Welch; дефолт Hann
бит-в-бит совпадает с прежним ``signal.get_window("hann", N, fftbins=True)``.
Kaiser зафиксирован на β=14 (боковые лепестки ≈ −90 дБ).
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.psd.errors import PsdSettingsError

Float64Array = NDArray[np.float64]

WINDOW_HANN: Final = "hann"
WINDOW_FLATTOP: Final = "flattop"
WINDOW_KAISER: Final = "kaiser"
WINDOW_BLACKMAN: Final = "blackman"
LEGACY_HANN_PERIODIC: Final = "hann_periodic"

WINDOW_OPTIONS: Final = (WINDOW_HANN, WINDOW_FLATTOP, WINDOW_KAISER, WINDOW_BLACKMAN)
KNOWN_WINDOWS: Final = (*WINDOW_OPTIONS, LEGACY_HANN_PERIODIC)

RBW_OPTIONS_HZ: Final = (10.0, 30.0, 50.0, 100.0, 300.0)
DEFAULT_RBW_HZ: Final = 50.0
DEFAULT_WINDOW: Final = WINDOW_HANN
KAISER_BETA: Final = 14.0


def canonical_window_name(name: str) -> str:
    """Возвращает каноническое имя окна; legacy ``hann_periodic`` это ``hann``."""
    if name == LEGACY_HANN_PERIODIC:
        return WINDOW_HANN
    if name in WINDOW_OPTIONS:
        return name
    raise PsdSettingsError(f"PSD: неизвестное окно {name!r}, ожидалось одно из {KNOWN_WINDOWS}")


def get_window(name: str, nperseg: int) -> Float64Array:
    """Возвращает периодические веса окна длиной ``nperseg`` как float64."""
    canonical = canonical_window_name(name)
    scipy_name: str | tuple[str, float] = canonical
    if canonical == WINDOW_KAISER:
        scipy_name = (WINDOW_KAISER, KAISER_BETA)
    return np.asarray(signal.get_window(scipy_name, nperseg, fftbins=True), dtype=np.float64)


def enbw_bins(name: str, nperseg: int) -> float:
    """Возвращает ENBW окна в бинах: ``N · Σw² / (Σw)²``."""
    weights = get_window(name, nperseg)
    return float(nperseg) * float(np.sum(weights * weights)) / float(np.sum(weights)) ** 2


def enbw_hz(name: str, nperseg: int, sample_rate_hz: float) -> float:
    """Возвращает ENBW окна в герцах: ``fs · Σw² / (Σw)²``."""
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise PsdSettingsError("PSD: частота дискретизации должна быть конечной и > 0")
    weights = get_window(name, nperseg)
    return sample_rate_hz * float(np.sum(weights * weights)) / float(np.sum(weights)) ** 2


def coherent_gain(name: str, nperseg: int) -> float:
    """Возвращает когерентное усиление окна: ``Σw / N``."""
    return float(np.sum(get_window(name, nperseg))) / float(nperseg)


def validate_rbw_hz(value: float) -> float:
    """Проверяет RBW-селектор: только 10/30/50/100/300 Гц."""
    if not math.isfinite(value) or float(value) not in RBW_OPTIONS_HZ:
        raise PsdSettingsError(
            f"PSD: rbw_hz должен быть одним из {list(RBW_OPTIONS_HZ)}, получено {value!r}"
        )
    return float(value)
