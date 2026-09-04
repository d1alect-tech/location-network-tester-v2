"""Измеренная swept-FR RC-тракта (CSV) + hook де-эмбеддинга 230:6 (очередь C3).

Swept-таблица переопределяет номинальную однополюсную модель только внутри
измеренного диапазона; вне его — NaN (``unavailable, never fabricated``),
экстраполяции нет. Hook трансформатора по умолчанию выключен: допущение
идеального отношения задокументировано, реальный холостой ход обязан измерить
оператор (типовой 2 ВА 230:6 даёт ~10 В, множитель 21–23, а не 38.3).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError

if TYPE_CHECKING:
    from pathlib import Path

Float64Array = NDArray[np.float64]
MIN_SWEPT_POINTS: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class SweptResponse:
    """Измеренный линейный |H(f)| на строгой монотонной сетке частот."""

    frequencies_hz: Float64Array
    gain: Float64Array
    source: str


def load_swept_response_csv(path: Path) -> SweptResponse:
    """Импортирует swept-FR (``frequency_hz,gain``); брак — ``InputError``."""
    try:
        text = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise InputError(f"swept_response: не читается {path}: {exc}") from exc
    rows = [row for row in csv.DictReader(text) if row]
    frequencies = _column(rows, "frequency_hz", path)
    gains = _column(rows, "gain", path)
    if frequencies.size < MIN_SWEPT_POINTS or np.any(np.diff(frequencies) <= 0.0):
        raise InputError(f"swept_response: {path}: частоты должны строго расти (≥2 точек)")
    if np.any(gains <= 0.0) or not np.all(np.isfinite(gains)):
        raise InputError(f"swept_response: {path}: gain должен быть конечным и > 0")
    return SweptResponse(frequencies_hz=frequencies, gain=gains, source=str(path))


def swept_gain_at(swept: SweptResponse, frequencies_hz: Float64Array) -> Float64Array:
    """Лог-линейная интерполяция |H|; вне диапазона — NaN без фабрикации."""
    log_grid = np.log(swept.frequencies_hz)
    log_query = np.log(np.asarray(frequencies_hz, dtype=np.float64))
    interpolated = np.interp(log_query, log_grid, swept.gain.astype(np.float64))
    in_range = (log_query >= log_grid[0]) & (log_query <= log_grid[-1])
    return np.where(in_range, interpolated, math.nan)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformerDeembed:
    """Hook приведения вторички к первичке; ``enabled=False`` — проброс как есть."""

    enabled: bool = False
    primary_v: float = 230.0
    secondary_v: float = 6.0

    def __post_init__(self) -> None:
        """Отклоняет нефизичное отношение витков на границе домена."""
        for name, value in (("primary_v", self.primary_v), ("secondary_v", self.secondary_v)):
            if not math.isfinite(value) or value <= 0.0:
                raise InputError(f"transformer_deembed: {name} должен быть конечным и > 0")


def apply_transformer_deembed(
    secondary_psd_v2_per_hz: Float64Array,
    frequencies_hz: Float64Array,
    *,
    hook: TransformerDeembed | None = None,
) -> Float64Array:
    """При выключенном hook возвращает вход без копий-сюрпризов; иначе ×ratio²."""
    _ = frequencies_hz
    resolved = hook if hook is not None else TransformerDeembed()
    if not resolved.enabled:
        return secondary_psd_v2_per_hz
    ratio = resolved.primary_v / resolved.secondary_v
    return secondary_psd_v2_per_hz * ratio**2


def _column(rows: list[dict[str, str | None]], name: str, path: Path) -> Float64Array:
    try:
        values = [float(row[name] or "") for row in rows]
    except (KeyError, ValueError) as exc:
        raise InputError(f"swept_response: {path}: колонка {name} битая: {exc}") from exc
    result = np.asarray(values, dtype=np.float64)
    if result.size == 0 or not np.all(np.isfinite(result)) or np.any(result <= 0.0):
        raise InputError(f"swept_response: {path}: колонка {name} должна быть > 0")
    return result
