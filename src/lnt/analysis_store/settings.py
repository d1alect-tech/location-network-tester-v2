"""Frozen-группы настроек AnalysisRecipe schema 1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from lnt.analysis_store.errors import RecipeError
from lnt.psd.windows import DEFAULT_RBW_HZ, KNOWN_WINDOWS, RBW_OPTIONS_HZ

MIN_SEGMENT_SAMPLES: Final = 2


def _finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise RecipeError(f"рецепт анализа: {name} должен быть конечным числом")


@dataclass(frozen=True, slots=True, kw_only=True)
class BandGridSettings:
    """Рабочая полоса и частотная сетка."""

    low_hz: float
    high_hz: float
    grid_hz: float

    def __post_init__(self) -> None:
        """Проверяет конечность и порядок границ."""
        for name, value in (
            ("low_hz", self.low_hz),
            ("high_hz", self.high_hz),
            ("grid_hz", self.grid_hz),
        ):
            _finite(name, value)
        if self.low_hz < 0 or self.high_hz <= self.low_hz or self.grid_hz <= 0:
            raise RecipeError("рецепт анализа: некорректная полоса или сетка")


@dataclass(frozen=True, slots=True, kw_only=True)
class WelchSettings:
    """Настройки оценки PSD методом Welch."""

    window: str
    segment_samples: int
    overlap_fraction: float
    detrend: str
    scaling: str
    average: str
    rbw_hz: float = DEFAULT_RBW_HZ

    def __post_init__(self) -> None:
        """Проверяет параметры Welch, включая RBW-селектор и окно."""
        _finite("welch.overlap_fraction", self.overlap_fraction)
        _finite("welch.rbw_hz", self.rbw_hz)
        if (
            self.window not in KNOWN_WINDOWS
            or self.segment_samples < MIN_SEGMENT_SAMPLES
            or not 0 <= self.overlap_fraction < 1
        ):
            raise RecipeError("рецепт анализа: некорректные настройки Welch")
        if float(self.rbw_hz) not in RBW_OPTIONS_HZ:
            raise RecipeError(
                f"рецепт анализа: welch.rbw_hz должен быть одним из {list(RBW_OPTIONS_HZ)}"
            )
        if not self.detrend or not self.scaling or not self.average:
            raise RecipeError("рецепт анализа: строковые настройки Welch не должны быть пустыми")


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectrogramSettings:
    """Настройки временно-частотного представления."""

    enabled: bool
    segment_samples: int
    overlap_fraction: float

    def __post_init__(self) -> None:
        """Проверяет параметры спектрограммы."""
        _finite("spectrogram.overlap_fraction", self.overlap_fraction)
        if self.segment_samples < MIN_SEGMENT_SAMPLES or not 0 <= self.overlap_fraction < 1:
            raise RecipeError("рецепт анализа: некорректные настройки спектрограммы")


@dataclass(frozen=True, slots=True, kw_only=True)
class EventSettings:
    """Настройки обнаружения событий."""

    enabled: bool
    threshold_sigma: float

    def __post_init__(self) -> None:
        """Проверяет положительный конечный порог."""
        _finite("events.threshold_sigma", self.threshold_sigma)
        if self.threshold_sigma <= 0:
            raise RecipeError("рецепт анализа: threshold_sigma должен быть > 0")


@dataclass(frozen=True, slots=True, kw_only=True)
class BandsSettings:
    """Границы агрегируемых частотных полос."""

    edges_hz: tuple[float, ...]

    def __post_init__(self) -> None:
        """Проверяет строгий порядок конечных границ."""
        for value in self.edges_hz:
            _finite("bands.edges_hz", value)
        if len(self.edges_hz) < MIN_SEGMENT_SAMPLES or any(
            left >= right for left, right in zip(self.edges_hz, self.edges_hz[1:], strict=False)
        ):
            raise RecipeError("рецепт анализа: edges_hz должны строго возрастать")


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectionSettings:
    """Настройки поправок измерительного тракта."""

    method: str

    def __post_init__(self) -> None:
        """Проверяет непустой идентификатор метода."""
        if not self.method:
            raise RecipeError("рецепт анализа: correction.method не должен быть пустым")


@dataclass(frozen=True, slots=True, kw_only=True)
class UncertaintySettings:
    """Настройки оценки неопределённости."""

    enabled: bool
    confidence_level: float
    bootstrap_samples: int

    def __post_init__(self) -> None:
        """Проверяет confidence level и число bootstrap повторов."""
        _finite("uncertainty.confidence_level", self.confidence_level)
        if not 0 < self.confidence_level < 1 or self.bootstrap_samples < 0:
            raise RecipeError("рецепт анализа: некорректные настройки неопределённости")
