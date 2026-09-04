"""Межсессионное усреднение спектра повторов серии (очередь B2).

Чистая функция поверх готовых ``spectrum.csv``: mean разбавляет выбросы
одиночных повторов, max-hold след хранит их уровень. Частотные сетки
повторов обязаны совпадать строго — иначе честная ошибка вместо
тихого смешения несопоставимых бинов. Формат spectrum.csv не тронут.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.analysis import SPECTRUM_FILENAME
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

Float64Array = NDArray[np.float64]

_CSV_COLUMNS: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class SeriesAverage:
    """Усреднённый спектр серии повторов с max-hold следом."""

    frequency_hz: Float64Array
    psd_mean_v2_per_hz: Float64Array
    psd_max_hold_v2_per_hz: Float64Array
    repeat_count: int


def average_repeat_spectra(grids: Sequence[tuple[Float64Array, Float64Array]]) -> SeriesAverage:
    """Усредняет повторы с идентичной сеткой: mean + поточечный max-hold."""
    if not grids:
        raise InputError("усреднение серии: нужен хотя бы один повтор")
    frequency = np.asarray(grids[0][0], dtype=np.float64)
    _require_grid(frequency)
    stacked = [np.asarray(grids[0][1], dtype=np.float64)]
    _require_power(stacked[0])
    for other_frequency, other_psd in grids[1:]:
        candidate_frequency = np.asarray(other_frequency, dtype=np.float64)
        candidate_psd = np.asarray(other_psd, dtype=np.float64)
        if candidate_frequency.shape != frequency.shape or not np.array_equal(
            candidate_frequency, frequency
        ):
            raise InputError("усреднение серии: частотные сетки повторов не совпадают")
        _require_power(candidate_psd)
        stacked.append(candidate_psd)
    block = np.stack(stacked)
    return SeriesAverage(
        frequency_hz=frequency.copy(),
        psd_mean_v2_per_hz=np.mean(block, axis=0),
        psd_max_hold_v2_per_hz=np.max(block, axis=0),
        repeat_count=len(stacked),
    )


def average_series_sessions(session_dirs: Sequence[Path]) -> SeriesAverage:
    """Читает ``spectrum.csv`` каталогов повторов и усредняет их."""
    grids = [_read_session_grid(session_dir) for session_dir in session_dirs]
    return average_repeat_spectra(grids)


def _read_session_grid(session_dir: Path) -> tuple[Float64Array, Float64Array]:
    path = session_dir / SPECTRUM_FILENAME
    try:
        table = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float64, ndmin=2)
    except (OSError, ValueError) as error:
        raise InputError(f"усреднение серии: не читается {path}") from error
    if table.ndim != _CSV_COLUMNS or table.shape[1] != _CSV_COLUMNS or table.shape[0] == 0:
        raise InputError(f"усреднение серии: повреждён {path}")
    return table[:, 0].copy(), table[:, 1].copy()


def _require_grid(frequency: Float64Array) -> None:
    if frequency.ndim != 1 or frequency.size == 0 or not np.all(np.isfinite(frequency)):
        raise InputError("усреднение серии: некорректная частотная сетка")
    if np.any(frequency <= 0.0):
        raise InputError("усреднение серии: частотная сетка должна быть положительной")


def _require_power(psd: Float64Array) -> None:
    if psd.ndim != 1 or psd.size == 0 or not np.all(np.isfinite(psd)):
        raise InputError("усреднение серии: спектр повтора содержит NaN или бесконечность")
    if np.any(psd <= 0.0):
        raise InputError("усреднение серии: спектр повтора должен быть положительным")
