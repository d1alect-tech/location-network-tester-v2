"""Валидация входа захвата: частота дискретизации и диапазон (чистые помощники).

Выделено из ``lnt.acquire`` без изменения семантики: коды частоты
и диапазона для протокола драйвера. Таблица ``RANGE_CODES`` живёт здесь —
это протокол гейна драйвера, а не масштаб raw -> В (он только в
``lnt.adc_calibration``). Лист: импортирует лишь ``lnt.errors``.
"""

import math

from lnt.errors import InputError

__all__ = ["MAX_DUAL_RATE_MHZ", "MEGA", "RANGE_CODES", "_range_code", "_rate_code"]

MEGA = 1_000_000
MAX_DUAL_RATE_MHZ = 15
# Номинал диапазона CH1 (В) -> код гейна драйвера; полная шкала = +-5.12/код В.
RANGE_CODES: dict[float, int] = {5.0: 1, 1.0: 5, 0.5: 10}


def _rate_code(sample_rate_hz: float) -> int:
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("частота дискретизации должна быть конечной и положительной")
    megahertz = sample_rate_hz / MEGA
    if megahertz != round(megahertz) or not 1 <= round(megahertz) <= MAX_DUAL_RATE_MHZ:
        raise InputError(
            f"частота {sample_rate_hz:.0f} Гц: допустимы целые 1..{MAX_DUAL_RATE_MHZ} МГц (dual)",
        )
    return round(megahertz)


def _range_code(range_v: float) -> int:
    code = RANGE_CODES.get(range_v)
    if code is None:
        supported = "/".join(f"{value:g}" for value in RANGE_CODES)
        raise InputError(f"диапазон {range_v:g} В не поддерживается: допустимы {supported} В")
    return code
