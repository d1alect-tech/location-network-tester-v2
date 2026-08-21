"""Прореживание рядов графиков панели с сохранением экстремумов и краёв."""

# ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: первые ~4 КБ файла утрачены при сбое диска;
# голова реконструирована по tests/test_ui_decimation.py, строкам байткода
# и модулям-потребителям; хвост оригинальный.

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError

type Float32Array = NDArray[np.float32]
type Float64Array = NDArray[np.float64]
type FloatArray = NDArray[np.float32] | NDArray[np.float64]
type IndexArray = NDArray[np.intp]

_MIN_POINTS: Final = 4


@dataclass(frozen=True, slots=True, kw_only=True)
class DecimatedSeries:
    """Прореженный ряд точек графика для передачи в панель (uPlot)."""

    x: tuple[float, ...]
    y: tuple[float, ...]
    point_count: int


def decimate_waveform(
    samples: Float32Array,
    *,
    sample_rate_hz: float,
    max_points: int,
) -> DecimatedSeries:
    """Прореживает форму волны канала, сохраняя экстремумы и края."""
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise InputError("частота дискретизации должна быть конечной и положительной")
    if samples.ndim != 1:
        raise InputError("канал должен быть одномерным массивом")
    _require_point_budget(max_points)
    values = np.asarray(samples)
    indices = _selected_indices(values, max_points)
    return DecimatedSeries(
        x=tuple(float(index) / sample_rate_hz for index in indices),
        y=tuple(float(values[index]) for index in indices),
        point_count=int(indices.size),
    )


def decimate_spectrum(
    frequency_hz: Float64Array,
    psd_v2_per_hz: Float64Array,
    *,
    max_points: int,
) -> DecimatedSeries:
    """Отбрасывает пары, небезопасные для log-осей, и прореживает остаток."""
    _require_vector_pair(frequency_hz, psd_v2_per_hz)
    _require_point_budget(max_points)
    safe = (
        np.isfinite(frequency_hz)
        & np.isfinite(psd_v2_per_hz)
        & (frequency_hz > 0.0)
        & (psd_v2_per_hz > 0.0)
    )
    return _decimated_xy(frequency_hz[safe], psd_v2_per_hz[safe], max_points)


def min_max_envelope(
    x: Float64Array,
    y: Float64Array,
    *,
    max_points: int,
) -> DecimatedSeries:
    """Строит min/max-огибающую ряда, сохраняя порядок и крайние точки."""
    _require_vector_pair(x, y)
    _require_point_budget(max_points)
    return _decimated_xy(x, y, max_points)


def _require_point_budget(max_points: int) -> None:
    if max_points < _MIN_POINTS:
        raise InputError("max_points должен быть не меньше 4")


def _require_vector_pair(x: FloatArray, y: FloatArray) -> None:
    if x.ndim != 1 or y.ndim != 1:
        raise InputError("координаты графика должны быть одномерными массивами")
    if x.size != y.size:
        raise InputError("координаты графика должны иметь одинаковую длину")


def _decimated_xy(x: FloatArray, y: FloatArray, max_points: int) -> DecimatedSeries:
    indices = _selected_indices(y, max_points)
    return DecimatedSeries(
        x=tuple(float(value) for value in x[indices]),
        y=tuple(float(value) for value in y[indices]),
        point_count=int(indices.size),
    )


def _selected_indices(values: FloatArray, max_points: int) -> IndexArray:
    point_count = int(values.size)
    if point_count <= max_points:
        return np.arange(point_count, dtype=np.intp)
    bucket_count = (max_points - 2) // 2
    interior_count = point_count - 2
    narrow_width = interior_count // bucket_count
    wider_count = interior_count - narrow_width * bucket_count
    wider_width = narrow_width + 1
    wider_length = wider_count * wider_width

    parts: list[IndexArray] = [np.array([0], dtype=np.intp)]
    if wider_count > 0:
        wider_starts = 1 + np.arange(wider_count, dtype=np.intp) * wider_width
        wider_values = values[1 : 1 + wider_length].reshape(wider_count, wider_width)
        parts.append(_extrema_indices(wider_values, wider_starts))

    narrow_count = bucket_count - wider_count
    if narrow_count > 0:
        narrow_start = 1 + wider_length
        narrow_starts = narrow_start + np.arange(narrow_count, dtype=np.intp) * narrow_width
        narrow_values = values[narrow_start:-1].reshape(narrow_count, narrow_width)
        parts.append(_extrema_indices(narrow_values, narrow_starts))

    parts.append(np.array([point_count - 1], dtype=np.intp))
    selected = np.concatenate(parts)
    keep = np.concatenate((np.ones(1, dtype=np.bool_), np.diff(selected) != 0))
    return np.asarray(selected[keep], dtype=np.intp)


def _extrema_indices(bucketed_values: FloatArray, starts: IndexArray) -> IndexArray:
    minima = np.asarray(np.argmin(bucketed_values, axis=1), dtype=np.intp)
    maxima = np.asarray(np.argmax(bucketed_values, axis=1), dtype=np.intp)
    local_extrema = np.stack((minima, maxima), axis=1)
    absolute_extrema = local_extrema + starts[:, np.newaxis]
    return np.asarray(np.sort(absolute_extrema, axis=1).reshape(-1), dtype=np.intp)
