"""Валидация входа захвата: частота дискретизации и диапазон (чистые помощники).

Выделено из ``lnt.acquire`` без изменения семантики: коды частоты
и диапазона для протокола драйвера. Таблица ``RANGE_CODES`` живёт здесь —
это протокол гейна драйвера, а не масштаб raw -> В (он только в
``lnt.adc_calibration``). Лист: импортирует лишь ``lnt.errors``.
"""

import math

from lnt.errors import InputError

__all__ = [
    "MAX_DUAL_RATE_MHZ",
    "MEGA",
    "RANGE_CODES",
    "SLOW_RATE_CODES",
    "_range_code",
    "_rate_code",
]

MEGA = 1_000_000
MAX_DUAL_RATE_MHZ = 15
# Номинал диапазона CH1 (В) -> код гейна драйвера; полная шкала = +-5.12/код В.
RANGE_CODES: dict[float, int] = {5.0: 1, 1.0: 5, 0.5: 10}
# Медленные коды FX2 dual-режима: pins PyHT6022/LibUsbScope.py:74-99 (Ho-Ro
# e65d52b). Директива владельца 2026-10-19: 20..640 кС/с доступны захвату —
# та же пара каналов, тот же bulk-поток, другой код управления 0xE2.
SLOW_RATE_CODES: dict[float, int] = {
    20_000.0: 102,
    32_000.0: 103,
    40_000.0: 104,
    50_000.0: 105,
    64_000.0: 106,
    100_000.0: 110,
    128_000.0: 113,
    200_000.0: 120,
    400_000.0: 140,
    500_000.0: 150,
    640_000.0: 164,
}


def _rate_code(sample_rate_hz: float) -> int:
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("частота дискретизации должна быть конечной и положительной")
    slow_code = SLOW_RATE_CODES.get(sample_rate_hz)
    if slow_code is not None:
        return slow_code
    megahertz = sample_rate_hz / MEGA
    if megahertz != round(megahertz) or not 1 <= round(megahertz) <= MAX_DUAL_RATE_MHZ:
        slow = "и медленная лестница 20..640 кГц (dual)"
        raise InputError(
            f"частота {sample_rate_hz:.0f} Гц: допустимы целые 1..{MAX_DUAL_RATE_MHZ} МГц {slow}",
        )
    return round(megahertz)


def _range_code(range_v: float) -> int:
    code = RANGE_CODES.get(range_v)
    if code is None:
        supported = "/".join(f"{value:g}" for value in RANGE_CODES)
        raise InputError(f"диапазон {range_v:g} В не поддерживается: допустимы {supported} В")
    return code
