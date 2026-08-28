"""Аудио-панель 20Гц–3кГц: ограниченный Welch PSD с пиками в полосе."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypedDict

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.errors import InputError
from lnt.psd import FrequencyBand, PsdSettings, compute_welch

if TYPE_CHECKING:
    from lnt.psd.models import PsdResult

AUDIO_LOW_HZ: Final = 20.0
AUDIO_HIGH_HZ: Final = 3000.0
MAX_PEAKS: Final = 8
AUDIO_PANEL_VERSION: Final = 1
_TARGET_RESOLUTION_HZ: Final = 10.0
_DEFAULT_CHUNK_SAMPLES: Final = 1_048_576
_MIN_NPERSEG: Final = 256
_DECIMATE_THRESHOLD_HZ: Final = 16000.0
_MIN_EFFECTIVE_HZ: Final = 7000.0
_TARGET_DECIMATED_HZ: Final = 8000.0

FloatArray = NDArray[np.floating]


class AudioPanelPeakDict(TypedDict):
    """JSON-safe пик аудио-панели."""

    frequency_hz: float
    psd_v2_per_hz: float
    prominence: float


class AudioPanelSettingsDict(TypedDict):
    """JSON-safe полные настройки аудио-панели."""

    audio_panel_version: int
    preset_name: str
    low_hz: float
    high_hz: float
    max_peaks: int
    target_resolution_hz: float
    chunk_samples: int


class AudioPanelInventoryDict(TypedDict):
    """JSON-safe инвентарь аудио-панели."""

    schema_version: int
    settings_hash: str
    settings: AudioPanelSettingsDict
    sample_rate_hz: float
    effective_sample_rate_hz: float
    low_hz: float
    high_hz: float
    band_rms_v: float
    segment_count: int
    resolution_hz: float
    peaks: list[AudioPanelPeakDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioPanelSettings:
    """Полные пороги для воспроизводимой аудио-панели."""

    audio_panel_version: int
    preset_name: str
    low_hz: float
    high_hz: float
    max_peaks: int
    target_resolution_hz: float
    chunk_samples: int

    def __post_init__(self) -> None:
        """Валидирует настройки на границе конструирования."""
        if self.audio_panel_version != AUDIO_PANEL_VERSION:
            raise InputError("аудио-панель: неподдерживаемая версия")
        if not self.preset_name or self.chunk_samples <= 0:
            raise InputError("аудио-панель: имя пресета и размер блока некорректны")
        if not math.isfinite(self.low_hz) or not math.isfinite(self.high_hz):
            raise InputError("аудио-панель: границы полосы не конечны")
        if not 0 <= self.low_hz < self.high_hz:
            raise InputError("аудио-панель: некорректная полоса")
        if self.max_peaks <= 0 or self.target_resolution_hz <= 0:
            raise InputError("аудио-панель: max_peaks и resolution должны быть >0")

    def to_dict(self) -> AudioPanelSettingsDict:
        """Сериализует настройки без неявных defaults."""
        return {
            "audio_panel_version": self.audio_panel_version,
            "preset_name": self.preset_name,
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "max_peaks": self.max_peaks,
            "target_resolution_hz": self.target_resolution_hz,
            "chunk_samples": self.chunk_samples,
        }


def audio_panel_preset(
    name: str = "audio_default",
    *,
    chunk_samples: int = _DEFAULT_CHUNK_SAMPLES,
) -> AudioPanelSettings:
    """Разворачивает preset в полные настройки."""
    if name != "audio_default":
        raise InputError(f"аудио-панель: неизвестный preset {name!r}")
    return AudioPanelSettings(
        audio_panel_version=AUDIO_PANEL_VERSION,
        preset_name=name,
        low_hz=AUDIO_LOW_HZ,
        high_hz=AUDIO_HIGH_HZ,
        max_peaks=MAX_PEAKS,
        target_resolution_hz=_TARGET_RESOLUTION_HZ,
        chunk_samples=chunk_samples,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioPanelPeak:
    """Пик PSD в полосе 20–3000 Гц."""

    frequency_hz: float
    psd_v2_per_hz: float
    prominence: float

    def to_dict(self) -> AudioPanelPeakDict:
        """Сериализует пик в JSON-безопасные примитивы."""
        return {
            "frequency_hz": self.frequency_hz,
            "psd_v2_per_hz": self.psd_v2_per_hz,
            "prominence": self.prominence,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioPanelInventory:
    """Детерминированный инвентарь аудио-пиков записи."""

    schema_version: int
    settings_hash: str
    settings: AudioPanelSettings
    sample_rate_hz: float
    effective_sample_rate_hz: float
    low_hz: float
    high_hz: float
    band_rms_v: float
    segment_count: int
    resolution_hz: float
    peaks: tuple[AudioPanelPeak, ...]

    def to_dict(self) -> AudioPanelInventoryDict:
        """Сериализует инвентарь целиком."""
        return {
            "schema_version": self.schema_version,
            "settings_hash": self.settings_hash,
            "settings": self.settings.to_dict(),
            "sample_rate_hz": self.sample_rate_hz,
            "effective_sample_rate_hz": self.effective_sample_rate_hz,
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "band_rms_v": self.band_rms_v,
            "segment_count": self.segment_count,
            "resolution_hz": self.resolution_hz,
            "peaks": [p.to_dict() for p in self.peaks],
        }


def _settings_hash(settings: AudioPanelSettings) -> str:
    """SHA-256 канонического JSON настроек."""
    payload = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate(samples: FloatArray, sample_rate_hz: float, chunk_samples: int) -> int:
    """Валидирует вход и возвращает длину."""
    view = np.asarray(samples)
    if view.ndim != 1 or view.size == 0:
        raise InputError("аудио-панель: требуется непустой одномерный ряд")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise InputError("аудио-панель: частота дискретизации должна быть конечной и >0")
    if chunk_samples <= 0:
        raise InputError("аудио-панель: размер блока должен быть >0")
    return int(view.size)


def _decimate_if_needed(
    samples: FloatArray, sample_rate_hz: float
) -> tuple[FloatArray, float, int]:
    """Децимирует поток если нужно для 20 Гц разрешения."""
    if sample_rate_hz <= _DECIMATE_THRESHOLD_HZ:
        return samples, sample_rate_hz, 1
    factor = round(sample_rate_hz / _TARGET_DECIMATED_HZ)
    factor = max(1, int(factor))
    while factor > 1 and sample_rate_hz / factor < _MIN_EFFECTIVE_HZ:
        factor -= 1
    if factor <= 1:
        return samples, sample_rate_hz, 1
    arr = np.asarray(samples, dtype=np.float64)
    decimated = signal.decimate(arr, factor, zero_phase=True)
    return decimated.astype(np.float32), sample_rate_hz / factor, factor


def _extract_peaks(result: PsdResult, low_hz: float, high_hz: float) -> tuple[AudioPanelPeak, ...]:
    """Находит до 8 пиков по prominence внутри полосы."""
    mask = (result.frequency_hz >= low_hz) & (result.frequency_hz <= high_hz)
    freq = result.frequency_hz[mask]
    psd = result.psd_v2_per_hz[mask]
    if psd.size == 0:
        return ()
    indices, props = signal.find_peaks(psd, prominence=0)
    if indices.size == 0:
        return ()
    prominences = props["prominences"]
    order = np.argsort(prominences)[::-1]
    capped = min(MAX_PEAKS, int(indices.size))
    peaks: list[AudioPanelPeak] = []
    for rank in range(capped):
        idx = int(indices[order[rank]])
        peaks.append(
            AudioPanelPeak(
                frequency_hz=float(freq[idx]),
                psd_v2_per_hz=float(psd[idx]),
                prominence=float(prominences[order[rank]]),
            )
        )
    return tuple(peaks)


def compute_audio_panel(
    samples: FloatArray,
    sample_rate_hz: float,
    chunk_samples: int = _DEFAULT_CHUNK_SAMPLES,
) -> AudioPanelInventory:
    """Считает ограниченный Welch PSD в 20–3000 Гц и до 8 пиков."""
    sample_count = _validate(samples, sample_rate_hz, chunk_samples)
    settings = audio_panel_preset(chunk_samples=chunk_samples)
    eff_samples, eff_rate, _ = _decimate_if_needed(samples, sample_rate_hz)
    eff_count = int(np.asarray(eff_samples).size)
    target_res = settings.target_resolution_hz
    nperseg = round(eff_rate / target_res)
    nperseg = max(_MIN_NPERSEG, int(nperseg))
    nperseg = min(nperseg, eff_count)
    if eff_count < nperseg:
        raise InputError("аудио-панель: запись слишком короткая")
    high_eff = min(AUDIO_HIGH_HZ, eff_rate / 2.0 - 1e-9)
    low_eff = AUDIO_LOW_HZ
    if low_eff >= high_eff:
        raise InputError("аудио-панель: полоса вне Найквиста")
    band = FrequencyBand(name="audio", low_hz=low_eff, high_hz=high_eff)
    psd_settings = PsdSettings(
        sample_rate_hz=eff_rate,
        nperseg=nperseg,
        max_chunk_samples=max(chunk_samples, nperseg),
        bands=(band,),
    )
    result = compute_welch(eff_samples, settings=psd_settings)
    peaks = _extract_peaks(result, low_eff, high_eff)
    band_rms_v = float(result.band_rms[0].rms_v) if result.band_rms else 0.0
    _ = sample_count
    return AudioPanelInventory(
        schema_version=AUDIO_PANEL_VERSION,
        settings_hash=_settings_hash(settings),
        settings=settings,
        sample_rate_hz=float(sample_rate_hz),
        effective_sample_rate_hz=float(eff_rate),
        low_hz=low_eff,
        high_hz=high_eff,
        band_rms_v=band_rms_v,
        segment_count=int(result.segment_count),
        resolution_hz=float(psd_settings.resolution_hz),
        peaks=peaks,
    )
