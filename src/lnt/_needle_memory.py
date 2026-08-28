"""Ядра анализа иголок с ограниченной памятью (T17).

Пакетные варианты тяжёлых операций ``needles``: последовательный сеяный
бутстрэп вместо одного большого тиража индексов, ресемплинг циклов на
фазовую сетку фиксированными батчами в два прохода и gather-интерполяция
без глобальной оси ``xp`` (``np.arange(hf.size)`` стоил 8 байт/отсчёт).

Числа не меняются: бутстрэп побитово эквивалентен большому тиражу (numpy
расходует поток бит генератора поэлементно в C-порядке, а построчные
mean/std совпадают с редукциями axis=1 — проверено тестом на точное
равенство); gather-интерполяция повторяет формулу ``np.interp`` при
единичном шаге сетки; пакетное накопление степеней совпадает с
цельноматричным эталоном в пределах rtol=1e-12 (меняется только порядок
суммирования float).

Пиковая память фильтрации неизбежна: ``sosfiltfilt`` требует полных
float64-копий записи (вход + внутренняя паддинг-копия + выход), поэтому
фильтрация транзиентно стоит ~3×запись(f64) = 6×запись(f32); после возврата
фильтра устойчиво живёт только один массив результата.
"""

import numpy as np
from numpy.typing import NDArray

Float32Array = NDArray[np.float32]
Float64Array = NDArray[np.float64]

PHASE_BINS = 4_096
RESAMPLE_BATCH = 128
RMS_CHUNK_SAMPLES = 1 << 22


def bootstrap_quantiles(
    peaks: Float64Array,
    *,
    seed: int,
    samples: int,
    eps: float,
) -> tuple[float, float, float, float]:
    """Сеяный бутстрэп квантилей μ_pk и σ_pk/μ_pk последовательными тиражами.

    Эквивалентен одному тиражу ``integers(size=(samples, count))``: поток бит
    генератора расходуется поэлементно в C-порядке, поэтому последовательные
    тиражи ``size=(count,)`` дают те же индексы, а построчные mean/std — те же
    значения, что редукции по axis=1. Память: O(count) вместо O(samples·count).
    """
    count = int(peaks.size)
    rng = np.random.default_rng(seed)
    means = np.empty(samples, dtype=np.float64)
    sigmas = np.empty(samples, dtype=np.float64)
    for index in range(samples):
        resample = peaks[rng.integers(0, count, size=count)]
        means[index] = np.mean(resample)
        sigmas[index] = np.std(resample, ddof=1)
    mean_low, mean_high = np.quantile(means, (0.025, 0.975))
    ratio_low, ratio_high = np.quantile(sigmas / np.maximum(means, eps), (0.025, 0.975))
    return float(mean_low), float(mean_high), float(ratio_low), float(ratio_high)


def gather_interp(x: Float64Array, y: Float64Array) -> Float64Array:
    """Линейная интерполяция ``y`` в точках ``x`` без полной оси ``xp``.

    Эквивалент ``np.interp(x, arange(y.size), y)``: при единичном шаге сетки
    наклон равен ``y[i+1] - y[i]``, формула и порядок операций совпадают с
    C-реализацией numpy; края зажаты к краевым значениям.
    """
    clipped = np.clip(x, 0.0, float(y.size - 1))
    low = np.clip(np.floor(clipped), 0.0, float(y.size - 2)).astype(np.intp)
    fraction = clipped - low.astype(np.float64)
    return (y[low + 1] - y[low]) * fraction + y[low]


def _phase_points(
    starts: Float64Array,
    lengths: Float64Array,
    phase_grid: Float64Array,
) -> Float64Array:
    points = starts[:, np.newaxis] + lengths[:, np.newaxis] * phase_grid[np.newaxis, :]
    return points.ravel()


def resample_mean_cycle(
    hf: Float64Array,
    positions: Float64Array,
    *,
    batch_size: int = RESAMPLE_BATCH,
) -> Float64Array:
    """Проход 1 батчевого ресемплинга: средний цикл длиной ``PHASE_BINS``.

    Формула прежняя: ``mean_cycle[j] = mean_i cycles[i, j]``, где
    ``cycles[i, j] = interp(starts[i] + lengths[i]·j/PHASE_BINS; hf)``.
    Циклы обрабатываются батчами (batch_size×PHASE_BINS f64 ≈ 4 МБ),
    полная матрица циклов не строится.
    """
    cycle_count = positions.size - 1
    starts = positions[:-1]
    lengths = np.diff(positions)
    phase_grid = np.arange(PHASE_BINS, dtype=np.float64) / PHASE_BINS
    total = np.zeros(PHASE_BINS, dtype=np.float64)
    for low_cycle in range(0, cycle_count, batch_size):
        high_cycle = min(low_cycle + batch_size, cycle_count)
        points = _phase_points(
            starts[low_cycle:high_cycle], lengths[low_cycle:high_cycle], phase_grid
        )
        batch = gather_interp(points, hf).reshape(high_cycle - low_cycle, PHASE_BINS)
        total += batch.sum(axis=0)
    return total / cycle_count


def residual_async_power(
    hf: Float64Array,
    positions: Float64Array,
    mean_cycle: Float64Array,
    *,
    batch_size: int = RESAMPLE_BATCH,
) -> float:
    """Проход 2: асинхронная мощность ``P_async = mean((cycles − mean_cycle)²)``.

    Повторный ресемплинг тех же окон дешевле хранения матрицы циклов:
    gather касается только отсчётов вокруг пиков, не всей записи.
    Соответствие прежней математике: сумма квадратов остатка по всем парам
    (цикл, фаза), делённая на ``cycle_count · PHASE_BINS``.
    """
    cycle_count = positions.size - 1
    starts = positions[:-1]
    lengths = np.diff(positions)
    phase_grid = np.arange(PHASE_BINS, dtype=np.float64) / PHASE_BINS
    squared_total = 0.0
    for low_cycle in range(0, cycle_count, batch_size):
        high_cycle = min(low_cycle + batch_size, cycle_count)
        points = _phase_points(
            starts[low_cycle:high_cycle], lengths[low_cycle:high_cycle], phase_grid
        )
        batch = gather_interp(points, hf).reshape(high_cycle - low_cycle, PHASE_BINS)
        squared_total += float(np.sum(np.square(batch - mean_cycle)))
    return squared_total / (cycle_count * PHASE_BINS)


def chunked_rms(samples: Float32Array) -> float:
    """RMS записи с f64-накоплением блоками, без постоянной f64-копии.

    Расширение f32→f64 точное, поэтому отличие от прежнего
    ``sqrt(mean(square(lf.astype(f64))))`` — только порядок суммирования
    блоков (~1e-16 относительных); значение используется лишь порогом
    ``MIN_LF_RMS_V``.
    """
    total = 0.0
    for low in range(0, samples.size, RMS_CHUNK_SAMPLES):
        chunk = samples[low : low + RMS_CHUNK_SAMPLES].astype(np.float64)
        total += float(np.sum(np.square(chunk)))
    return float(np.sqrt(total / samples.size))
