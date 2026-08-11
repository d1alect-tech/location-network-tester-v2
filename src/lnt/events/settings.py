"""Versioned, fully explicit settings for candidate-event detection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, TypedDict

from lnt.errors import InputError

EVENT_DETECTION_VERSION: Final = 1
MAD_TO_SIGMA: Final = 1.4826


class FrequencyBandDict(TypedDict):
    """JSON-safe frequency-band settings."""

    name: str
    low_hz: float
    high_hz: float


class DetectionSettingsDict(TypedDict):
    """JSON-safe complete effective detector settings."""

    event_detection_version: int
    preset_name: str
    noise_window_samples: int
    noise_step_samples: int
    minimum_noise_samples: int
    threshold_sigma: float
    max_gap_samples: int
    minimum_event_samples: int
    minimum_snr: float
    chunk_samples: int
    fft_max_samples: int
    rail_low_v: float
    rail_high_v: float
    rail_tolerance_v: float
    bands: list[FrequencyBandDict]


@dataclass(frozen=True, slots=True, kw_only=True)
class FrequencyBand:
    """Named half-open frequency interval; the last band includes its upper edge."""

    name: str
    low_hz: float
    high_hz: float

    def __post_init__(self) -> None:
        """Validate finite, increasing bounds."""
        if not self.name or not math.isfinite(self.low_hz) or not math.isfinite(self.high_hz):
            raise InputError("кандидаты событий: некорректная частотная полоса")
        if self.low_hz < 0.0 or self.high_hz <= self.low_hz:
            raise InputError("кандидаты событий: границы полосы должны строго возрастать")

    def to_dict(self) -> FrequencyBandDict:
        """Serialize the band to JSON-safe primitives."""
        return {"name": self.name, "low_hz": self.low_hz, "high_hz": self.high_hz}


@dataclass(frozen=True, slots=True, kw_only=True)
class DetectionSettings:
    """All thresholds needed to reproduce event detection exactly."""

    event_detection_version: int
    preset_name: str
    noise_window_samples: int
    noise_step_samples: int
    minimum_noise_samples: int
    threshold_sigma: float
    max_gap_samples: int
    minimum_event_samples: int
    minimum_snr: float
    chunk_samples: int
    rail_low_v: float
    rail_high_v: float
    rail_tolerance_v: float
    bands: tuple[FrequencyBand, ...]
    fft_max_samples: int = 65_536

    def __post_init__(self) -> None:
        """Validate every effective threshold at the construction boundary."""
        counts = (
            self.noise_window_samples,
            self.noise_step_samples,
            self.minimum_noise_samples,
            self.minimum_event_samples,
            self.chunk_samples,
            self.fft_max_samples,
        )
        scalars = (
            self.threshold_sigma,
            self.minimum_snr,
            self.rail_low_v,
            self.rail_high_v,
            self.rail_tolerance_v,
        )
        if self.event_detection_version != EVENT_DETECTION_VERSION:
            raise InputError("кандидаты событий: неподдерживаемая версия алгоритма")
        if not self.preset_name or any(value <= 0 for value in counts):
            raise InputError("кандидаты событий: размеры окон и блоков должны быть > 0")
        if self.max_gap_samples < 0 or any(not math.isfinite(value) for value in scalars):
            raise InputError("кандидаты событий: пороги должны быть конечными числами")
        if self.threshold_sigma <= 0.0 or self.minimum_snr <= 0.0:
            raise InputError("кандидаты событий: sigma-пороги должны быть > 0")
        if self.minimum_noise_samples > self.noise_window_samples:
            raise InputError("кандидаты событий: minimum_noise_samples больше окна")
        if self.rail_low_v >= self.rail_high_v or self.rail_tolerance_v < 0.0:
            raise InputError("кандидаты событий: некорректные уровни ограничения")
        if not self.bands or any(
            left.high_hz > right.low_hz
            for left, right in zip(self.bands, self.bands[1:], strict=False)
        ):
            raise InputError("кандидаты событий: полосы пусты, пересекаются или не упорядочены")

    def to_dict(self) -> DetectionSettingsDict:
        """Serialize all effective thresholds without implicit defaults."""
        return {
            "event_detection_version": self.event_detection_version,
            "preset_name": self.preset_name,
            "noise_window_samples": self.noise_window_samples,
            "noise_step_samples": self.noise_step_samples,
            "minimum_noise_samples": self.minimum_noise_samples,
            "threshold_sigma": self.threshold_sigma,
            "max_gap_samples": self.max_gap_samples,
            "minimum_event_samples": self.minimum_event_samples,
            "minimum_snr": self.minimum_snr,
            "chunk_samples": self.chunk_samples,
            "fft_max_samples": self.fft_max_samples,
            "rail_low_v": self.rail_low_v,
            "rail_high_v": self.rail_high_v,
            "rail_tolerance_v": self.rail_tolerance_v,
            "bands": [band.to_dict() for band in self.bands],
        }


_BANDS: Final = (
    FrequencyBand(name="low", low_hz=0.0, high_hz=3_000.0),
    FrequencyBand(name="mid", low_hz=3_000.0, high_hz=30_000.0),
    FrequencyBand(name="high", low_hz=30_000.0, high_hz=3_000_000.0),
)


def event_preset(name: str) -> DetectionSettings:
    """Return a named preset expanded into complete persisted settings."""
    match name:
        case "impulses_default":
            max_gap_samples, minimum_event_samples = 8, 1
        case "bursts_default":
            max_gap_samples, minimum_event_samples = 64, 4
        case _:
            raise InputError(f"кандидаты событий: неизвестный preset {name!r}")
    return DetectionSettings(
        event_detection_version=EVENT_DETECTION_VERSION,
        preset_name=name,
        noise_window_samples=4_001,
        noise_step_samples=256,
        minimum_noise_samples=2_000,
        threshold_sigma=6.0,
        max_gap_samples=max_gap_samples,
        minimum_event_samples=minimum_event_samples,
        minimum_snr=6.0,
        chunk_samples=1_048_576,
        rail_low_v=-1.0,
        rail_high_v=1.0,
        rail_tolerance_v=1e-6,
        bands=_BANDS,
    )
