"""Софтверный edge-триггер живого режима: конфигурация и поиск фронта.

Hantek 6022BE не даёт ни аппаратного триггера, ни предтриггерной памяти
(issues #22/#26): окно кадра НАЧИНАЕТСЯ на фронте, отсчётов до него не бывает.
Поиск идёт по уже принятым отсчётам в вольтах (масштаб — ``adc_calibration``),
векторно одним проходом по буферу; ``start`` — курсор непросмотренного потока.
"""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError

Float32Array = NDArray[np.float32]

# Пауза без фронта, после которой AUTO выдаёт кадр развёртки (как sweep на DSO).
DEFAULT_AUTO_TIMEOUT_S: Final = 0.2
# Окно входа 5 В (диапазон прибора): порог триггера живёт внутри ±5 В,
# как и клэмп уровня на клиенте (frontend TRIGGER_LEVEL_LIMIT_V).
TRIGGER_LEVEL_LIMIT_V: Final = 5.0


class TriggerSource(StrEnum):
    """Канал, на котором ищется фронт."""

    CH1 = "ch1"
    CH2 = "ch2"


class TriggerSlope(StrEnum):
    """Полярность фронта."""

    RISING = "rising"
    FALLING = "falling"


class TriggerMode(StrEnum):
    """AUTO — кадр по таймауту даже без фронта, NORMAL — только фронт, SINGLE — один кадр и стоп."""

    AUTO = "auto"
    NORMAL = "normal"
    SINGLE = "single"


@dataclass(frozen=True, slots=True, kw_only=True)
class TriggerConfig:
    """Порог, полярность, источник и режим софтверного триггера."""

    level_v: float
    slope: TriggerSlope = TriggerSlope.RISING
    source: TriggerSource = TriggerSource.CH1
    mode: TriggerMode = TriggerMode.AUTO
    auto_timeout_s: float = DEFAULT_AUTO_TIMEOUT_S

    def __post_init__(self) -> None:
        """Отклоняет порог вне окна входа −5…+5 В и неположительный таймаут AUTO."""
        if not math.isfinite(self.level_v):
            raise InputError(f"триггер: уровень {self.level_v} В должен быть конечным")
        if not -TRIGGER_LEVEL_LIMIT_V <= self.level_v <= TRIGGER_LEVEL_LIMIT_V:
            limit = f"−{TRIGGER_LEVEL_LIMIT_V:g}…+{TRIGGER_LEVEL_LIMIT_V:g} В"
            raise InputError(f"триггер: уровень {self.level_v} В вне диапазона {limit}")
        if not math.isfinite(self.auto_timeout_s) or self.auto_timeout_s <= 0.0:
            raise InputError(
                f"триггер: auto_timeout_s {self.auto_timeout_s} с должен быть конечным и > 0",
            )


def find_edge(
    samples: Float32Array,
    *,
    level_v: float,
    slope: TriggerSlope,
    start: int = 1,
) -> int | None:
    """Индекс отсчёта, НА котором сигнал пересёк порог, либо ``None``.

    Пересечение определяется парой соседних отсчётов, поэтому поиск начинается
    не раньше индекса 1; возвращённый индекс — начало окна кадра (предтриггера
    нет, отсчёты до фронта в кадр не попадают).
    """
    total = int(samples.size)
    first = max(1, start)
    if first >= total:
        return None
    previous = samples[first - 1 : total - 1]
    current = samples[first:total]
    if slope is TriggerSlope.RISING:
        crossing = (previous < level_v) & (current >= level_v)
    else:
        crossing = (previous > level_v) & (current <= level_v)
    hits = np.flatnonzero(crossing)
    if hits.size == 0:
        return None
    return int(hits[0]) + first
