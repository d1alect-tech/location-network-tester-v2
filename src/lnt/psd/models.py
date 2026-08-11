"""Неизменяемые настройки и результаты потокового Welch PSD."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.psd.errors import PsdSettingsError

if TYPE_CHECKING:
    from lnt.analysis_store.settings import WelchSettings

DEFAULT_LOW_HZ: Final = 3_000.0
DEFAULT_HIGH_HZ: Final = 3_000_000.0
DEFAULT_RESOLUTION_HZ: Final = 50.0
DEFAULT_MAX_CHUNK_SAMPLES: Final = 1_000_000
MIN_NPERSEG: Final = 2

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

    def __post_init__(self) -> None:
        """Проверяет частоту, размер порции и границы Найквиста."""
        if not math.isfinite(self.sample_rate_hz) or self.sample_rate_hz <= 0:
            raise PsdSettingsError("PSD: частота дискретизации должна быть конечной и > 0")
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
        expected = ("hann_periodic", 0.5, "constant", "density", "mean")
        actual = (
            welch.window,
            welch.overlap_fraction,
            welch.detrend,
            welch.scaling,
            welch.average,
        )
        if actual != expected:
            raise PsdSettingsError(
                "PSD: поддерживаются periodic Hann, overlap=0.5, constant, density, mean"
            )
        return cls(
            sample_rate_hz=sample_rate_hz,
            nperseg=welch.segment_samples,
            max_chunk_samples=max(max_chunk_samples, welch.segment_samples),
            bands=bands,
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
    psd_unit: str = "V²/Hz"
    asd_unit: str = "V/√Hz"
    level_unit: str = "dB re 1 V²/Hz"
