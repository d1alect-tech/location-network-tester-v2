"""Типы настроек и результатов ограниченной спектрограммы."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol, TypeGuard

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError

if TYPE_CHECKING:
    from lnt.analysis_store.settings import SpectrogramSettings

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]
UInt32Array = NDArray[np.uint32]
Detrend = Literal["constant", "linear"]
Scaling = Literal["psd", "spectrum"]
MAX_OVERVIEW_TIME_BINS: Final = 2048
MAX_OVERVIEW_FREQUENCY_BANDS: Final = 1024
MIN_SEGMENT_SAMPLES: Final = 2


class CancellationToken(Protocol):
    """Минимальный синхронный контракт отмены из Todo 20."""

    def cancelled(self) -> bool:
        """Возвращает запрос отмены без блокировки."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class StftSettings:
    """Версионированная воспроизводимая геометрия STFT."""

    version: int
    window: str
    segment_samples: int
    hop_samples: int
    detrend: Detrend
    scaling: Scaling

    def __post_init__(self) -> None:
        """Проверяет версию и геометрию окна."""
        if self.version != 1 or self.segment_samples < MIN_SEGMENT_SAMPLES:
            raise InputError("спектрограмма: неподдерживаемая версия или длина окна")
        if not 0 < self.hop_samples <= self.segment_samples:
            raise InputError("спектрограмма: шаг должен быть в пределах длины окна")
        if not self.window or not self.detrend or self.scaling not in {"psd", "spectrum"}:
            raise InputError("спектрограмма: некорректные window/detrend/scaling")

    @classmethod
    def from_recipe(cls, recipe: SpectrogramSettings) -> StftSettings:
        """Дополняет текущую recipe schema стабильными параметрами STFT v1."""
        hop = max(1, round(recipe.segment_samples * (1.0 - recipe.overlap_fraction)))
        return cls(
            version=1,
            window="hann",
            segment_samples=recipe.segment_samples,
            hop_samples=hop,
            detrend="constant",
            scaling="psd",
        )

    @classmethod
    def parse(  # noqa: PLR0913 - parser mirrors all versioned metadata fields
        cls,
        *,
        version: int,
        window: str,
        segment_samples: int,
        hop_samples: int,
        detrend: str,
        scaling: str,
    ) -> StftSettings:
        """Разбирает строковые варианты metadata на доверенной границе."""
        if not _is_detrend(detrend) or not _is_scaling(scaling):
            raise InputError("спектрограмма: metadata содержит неизвестный вариант STFT")
        return cls(
            version=version,
            window=window,
            segment_samples=segment_samples,
            hop_samples=hop_samples,
            detrend=detrend,
            scaling=scaling,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectrogramOverview:
    """Ограниченный обзор; coverage=0 всегда означает явный NaN."""

    power_db: Float32Array
    linear_power: Float64Array
    coverage: UInt32Array
    time_s: Float64Array
    frequency_hz: Float64Array
    frequency_edges_hz: Float64Array
    settings: StftSettings
    db_reference: float
    floor_db: float
    ceiling_db: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ZoomRequest:
    """Точный временной интервал и частотная полоса."""

    start_s: float
    end_s: float
    low_hz: float
    high_hz: float

    def __post_init__(self) -> None:
        """Проверяет конечность и порядок границ."""
        values = (self.start_s, self.end_s, self.low_hz, self.high_hz)
        if not all(math.isfinite(value) for value in values):
            raise InputError("спектрограмма: границы zoom должны быть конечными")
        if self.start_s < 0 or self.end_s <= self.start_s:
            raise InputError("спектрограмма: некорректный временной интервал zoom")
        if self.low_hz < 0 or self.high_hz <= self.low_hz:
            raise InputError("спектрограмма: некорректная частотная полоса zoom")


@dataclass(frozen=True, slots=True, kw_only=True)
class ZoomLimits:
    """Жёсткие пределы до первой большой аллокации."""

    max_samples: int
    max_cells: int
    max_wall_time_s: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ExactSpectrogram:
    """Точный ограниченный STFT без браузерного raw payload."""

    linear_power: Float64Array
    power_db: Float32Array
    time_s: Float64Array
    frequency_hz: Float64Array
    settings: StftSettings
    db_reference: float
    floor_db: float
    ceiling_db: float


def _is_detrend(value: str) -> TypeGuard[Detrend]:
    return value in {"constant", "linear"}


def _is_scaling(value: str) -> TypeGuard[Scaling]:
    return value in {"psd", "spectrum"}
