"""Display-only пересчёт уровней рядом с дБВ/Гц (очередь C3).

Хранимый формат неизменен (``spectrum.csv`` — В²/Гц); функции — чистые
пересчёты для отображения и подписей. Опоры: дБмкВ — +120 дБ к дБВ,
дБм — мощность в 50 Ом относительно 1 мВт (+10·log10(20) дБ к дБВ).
"""

from __future__ import annotations

import math
from typing import Final

DBUV_OFFSET_DB: Final = 120.0
DBM_50R_OFFSET_DB: Final = 10.0 * math.log10(20.0)
DISPLAY_UNITS: Final = ("dbv", "dbuv", "dbm_50r")
UNIT_LABELS_RU: Final = {
    "dbv": "дБВ/Гц (отн. 1 В²/Гц)",
    "dbuv": "дБмкВ/Гц",
    "dbm_50r": "дБм/Гц · 50 Ом",
}


def dbv_per_hz(psd_v2_per_hz: float) -> float:
    """Уровень PSD относительно 1 В²/Гц."""
    return 10.0 * math.log10(psd_v2_per_hz)


def dbuv_per_hz(psd_v2_per_hz: float) -> float:
    """Тот же уровень в дБмкВ/Гц (display-only сдвиг +120 дБ)."""
    return dbv_per_hz(psd_v2_per_hz) + DBUV_OFFSET_DB


def dbm_per_hz_50r(psd_v2_per_hz: float) -> float:
    """Мощность в 50 Ом относительно 1 мВт (display-only, 50 Ом явно)."""
    return dbv_per_hz(psd_v2_per_hz) + DBM_50R_OFFSET_DB


def shift_level_db(level_db_ref_1v2_per_hz: float, unit: str) -> float:
    """Сдвигает готовый дБ-уровень под единицу отображения; дельты инвариантны."""
    match unit:
        case "dbv":
            return level_db_ref_1v2_per_hz
        case "dbuv":
            return level_db_ref_1v2_per_hz + DBUV_OFFSET_DB
        case "dbm_50r":
            return level_db_ref_1v2_per_hz + DBM_50R_OFFSET_DB
        case _:
            raise ValueError(f"units: неизвестная единица отображения {unit!r}")
