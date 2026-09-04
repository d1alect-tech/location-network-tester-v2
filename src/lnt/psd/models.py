"""Неизменяемые настройки и результаты потокового Welch PSD."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

import numpy as np
from numpy.typing import NDArray

from lnt.psd.errors import PsdSettingsError
from lnt.psd.windows import (
    DEFAULT_WINDOW,
    KNOWN_WINDOWS,
    canonical_window_name,
    coherent_gain,
    enbw_hz,
)

if TYPE_CHECKING:
    from lnt.analysis_store.settings import WelchSettings

DEFAULT_LOW_HZ: Final = 3_000.0
DEFAULT_HIGH_HZ: Final = 3_000_000.0
DEFAULT_RESOLUTION_HZ: Final = 50.0
DEFAULT_MAX_CHUNK_SAMPLES: Final = 1_000_000
MIN_NPERSEG: Final = 2

TraceDetector = Literal["mean", "rms", "max-hold", "min-hold"]
KNOWN_DETECTORS: Final = ("mean", "rms", "max-hold", "min-hold")
DEFAULT_DETECTOR: Final = "mean"

Float64Array = NDArray[np.float64]


@dataclass(frozen=True, slots=True, kw_only=True)
class FrequencyBand:
    """Замкнутая именованная полоса интегрирования."""

    name: str
    low_hz: float
    high_hz: float

    def __post_init__(self) -> None:
        """Проверяет локальные инварианты полосы."""
        if (
            not self.name
            or not math.isfinite(self.low_hz)
            or not math.isfinite(self.high_hz)
            or self.low_hz < 0
            or self.high_hz <= self.low_hz
        ):
            raise PsdSettingsError("PSD: некорректная частотная полоса")


@dataclass(frozen=True, slots=True, kw_only=True)
class PsdSettings:
    """Проверенные настройки строго определённого одностороннего Welch."""

    sample_rate_hz: float
    nperseg: int
    max_chunk_samples: int
    bands: tuple[FrequencyBand, ...]
    window: str = DEFAULT_WINDOW
    overlap_fraction: float = 0.5
    detector: str = DEFAULT_DETECTOR
    track_max_hold: bool = False

    def __post_init__(self) -> None:
        """Проверяет частоту, размер порции, окно, детектор и границы Найквиста."""
        if not math.isfinite(self.sample_rate_hz) or self.sample_rate_hz <= 0:
            raise PsdSettingsError("PSD: частота дискретизации должна быть конечной и > 0")
        if self.window not in KNOWN_WINDOWS:
            raise PsdSettingsError(f"PSD: неизвестное окно {self.window!r}")
        if self.detector not in KNOWN_DETECTORS:
            raise PsdSettingsError(f"PSD: неизвестный детектор {self.detector!r}")
        if not math.isfinite(self.overlap_fraction) or not 0 <= self.overlap_fraction < 1:
            raise PsdSettingsError("PSD: overlap_fraction должен быть в [0, 1)")
        if self.nperseg < MIN_NPERSEG:
            raise PsdSettingsError("PSD: nperseg должен быть >= 2")
        if self.max_chunk_samples < self.nperseg:
            raise PsdSettingsError("PSD: порция должна вмещать хотя бы один сегмент")
        if not self.bands:
            raise PsdSettingsError("PSD: требуется хотя бы одна полоса")
        nyquist_hz = self.sample_rate_hz / 2.0
        if any(band.high_hz > nyquist_hz for band in self.bands):
            raise PsdSettingsError(f"PSD: полоса выходит за частоту Найквиста {nyquist_hz:g} Гц")

    @classmethod
    def from_recipe(
        cls,
        *,
        sample_rate_hz: float,
        welch: WelchSettings,
        bands: tuple[FrequencyBand, ...],
        max_chunk_samples: int = DEFAULT_MAX_CHUNK_SAMPLES,
    ) -> PsdSettings:
        """Строит контракт из группы ``AnalysisRecipe.welch``."""
        expected = ("constant", "density", "mean")
        actual = (welch.detrend, welch.scaling, welch.average)
        if actual != expected:
            raise PsdSettingsError("PSD: поддерживаются только constant, density, mean")
        canonical_window_name(welch.window)
        return cls(
            sample_rate_hz=sample_rate_hz,
            nperseg=welch.segment_samples,
            max_chunk_samples=max(max_chunk_samples, welch.segment_samples),
            bands=bands,
            window=welch.window,
            overlap_fraction=welch.overlap_fraction,
        )

    @classmethod
    def default(cls, *, sample_rate_hz: float) -> PsdSettings:
        """Создаёт исторический preset 3 кГц–3 МГц с разрешением 50 Гц."""
        nperseg = round(sample_rate_hz / DEFAULT_RESOLUTION_HZ)
        high_hz = min(DEFAULT_HIGH_HZ, sample_rate_hz / 2.0)
        return cls(
            sample_rate_hz=sample_rate_hz,
            nperseg=nperseg,
            max_chunk_samples=max(DEFAULT_MAX_CHUNK_SAMPLES, nperseg),
            bands=(FrequencyBand(name="measurement", low_hz=DEFAULT_LOW_HZ, high_hz=high_hz),),
        )

    @property
    def resolution_hz(self) -> float:
        """Возвращает точный шаг ``fs / nperseg``."""
        return self.sample_rate_hz / self.nperseg

    @property
    def window_enbw_hz(self) -> float:
        """Возвращает ENBW выбранного окна в герцах."""
        return enbw_hz(self.window, self.nperseg, self.sample_rate_hz)

    @property
    def window_coherent_gain(self) -> float:
        """Возвращает когерентное усиление выбранного окна."""
        return coherent_gain(self.window, self.nperseg)

    @property
    def noverlap(self) -> int:
        """Возвращает перекрытие сегментов в отсчётах."""
        return min(round(self.nperseg * self.overlap_fraction), self.nperseg - 1)


@dataclass(frozen=True, slots=True, kw_only=True)
class BandRms:
    """Интегральное RMS-напряжение одной полосы."""

    band: FrequencyBand
    rms_v: float
    unit: str = "V"


@dataclass(frozen=True, slots=True, kw_only=True)
class PsdResult:
    """Односторонние PSD, ASD, dB и полосовые RMS с единицами."""

    frequency_hz: Float64Array
    psd_v2_per_hz: Float64Array
    asd_v_per_sqrt_hz: Float64Array
    level_db_v2_per_hz: Float64Array
    band_rms: tuple[BandRms, ...]
    segment_count: int
    window: str = DEFAULT_WINDOW
    enbw_hz: float = 0.0
    detector: str = DEFAULT_DETECTOR
    psd_max_hold_v2_per_hz: Float64Array | None = None
    psd_unit: str = "V²/Hz"
    asd_unit: str = "V/√Hz"
    level_unit: str = "dB re 1 V²/Hz"
