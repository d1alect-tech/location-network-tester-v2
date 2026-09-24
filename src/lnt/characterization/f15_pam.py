"""F15: детерминированные примитивы PAM и adjusted Rand index."""

from __future__ import annotations

from itertools import permutations
from typing import Final

import numpy as np
from numpy.typing import NDArray

type Int64Array = NDArray[np.int64]

_SWAP_DISTANCE_ELEMENTS: Final = 1_000_000
_MATRIX_NDIM: Final = 2
_VECTOR_NDIM: Final = 1
_MINIMUM_ARI_ITEMS: Final = 2


def pam_build_indices(standardized: np.ndarray, *, cluster_count: int) -> tuple[int, ...]:
    """Выбрать BUILD-медиоиды по максимальному расстоянию и младшему индексу."""
    values = np.asarray(standardized, dtype=np.float64)
    if values.ndim != _MATRIX_NDIM or values.shape[0] < cluster_count or cluster_count <= 0:
        raise ValueError("F15 BUILD requires at least cluster_count feature rows")
    medoids = [0]
    nearest = np.sum((values - values[0]) ** 2, axis=1)
    while len(medoids) < cluster_count:
        candidate = int(np.argmax(nearest))
        if nearest[candidate] <= 0.0:
            raise ValueError("F15 BUILD could not select a distinct medoid")
        medoids.append(candidate)
        distance = np.sum((values - values[candidate]) ** 2, axis=1)
        nearest = np.minimum(nearest, distance)
    return tuple(medoids)


def pam_swap_indices(
    standardized: np.ndarray,
    initial: tuple[int, ...],
    *,
    maximum_passes: int,
) -> tuple[tuple[int, ...], int]:
    """Выполнять детерминированные SWAP до неизменности назначений."""
    values = np.asarray(standardized, dtype=np.float64)
    if values.ndim != _MATRIX_NDIM or not initial or maximum_passes <= 0:
        raise ValueError("F15 SWAP requires a feature matrix, medoids, and positive passes")
    medoids = np.asarray(initial, dtype=np.int64)
    if medoids.shape != (len(initial),) or np.unique(medoids).size != medoids.size:
        raise ValueError("F15 SWAP medoids must be unique local row indices")
    if int(np.max(medoids)) >= values.shape[0] or int(np.min(medoids)) < 0:
        raise ValueError("F15 SWAP medoid index is outside the feature matrix")
    passes = 0
    for _ in range(maximum_passes):
        columns = _distance_columns(values, medoids)
        previous = columns.T.argmin(axis=1).astype(np.int64)
        best_delta = 0.0
        best_candidate = -1
        best_slot = -1
        current_cost = float(np.sum(np.min(columns, axis=0)))
        candidates = np.setdiff1d(np.arange(values.shape[0], dtype=np.int64), medoids)
        for slot in range(medoids.size):
            alternative = np.min(np.delete(columns, slot, axis=0), axis=0)
            block_size = max(1, _SWAP_DISTANCE_ELEMENTS // values.shape[0])
            for start in range(0, candidates.size, block_size):
                block = candidates[start : start + block_size]
                delta = values[block, None, :] - values[None, :, :]
                replacement = np.sum(delta * delta, axis=2)
                costs = np.sum(np.minimum(replacement, alternative[None, :]), axis=1)
                position = int(np.argmin(costs))
                improvement = current_cost - float(costs[position])
                if improvement > best_delta:
                    best_delta = improvement
                    best_candidate = int(block[position])
                    best_slot = slot
        if best_candidate < 0:
            break
        proposed = medoids.tolist()
        proposed[best_slot] = best_candidate
        medoids = np.asarray(sorted(proposed), dtype=np.int64)
        passes += 1
        if np.array_equal(_nearest(values, medoids), previous):
            break
    return tuple(int(value) for value in medoids), passes


def _nearest(values: np.ndarray, medoids: np.ndarray) -> Int64Array:
    """Метки ближайших медиоидов; при ничьей выбирается младший упорядоченный индекс."""
    return _distance_columns(values, medoids).T.argmin(axis=1).astype(np.int64)


def _value_distance_columns(values: np.ndarray, references: np.ndarray) -> np.ndarray:
    """Квадраты расстояний от опорных медиоидов до каждой строки признаков."""
    delta = references[:, None, :] - values[None, :, :]
    return np.sum(delta * delta, axis=2)


def _distance_columns(values: np.ndarray, medoids: np.ndarray) -> np.ndarray:
    """Квадраты расстояний от каждого медиоида до каждой строки."""
    delta = values[medoids][:, None, :] - values[None, :, :]
    return np.sum(delta * delta, axis=2)


def f15_stability_scores(
    standardized: np.ndarray,
    full_medoids: np.ndarray,
    *,
    block_count: int,
    maximum_passes: int,
) -> np.ndarray | None:
    """Переобучить нисходящие блоки и сравнить метки с полными медиоидами."""
    values = np.asarray(standardized, dtype=np.float64)
    reference = np.asarray(full_medoids, dtype=np.float64)
    cluster_count = reference.shape[0]
    if (
        values.ndim != _MATRIX_NDIM
        or reference.shape != (cluster_count, values.shape[1])
        or block_count <= 0
        or cluster_count <= 0
    ):
        raise ValueError("F15 stability inputs must keep four medoids and seven features")
    scores: list[float] = []
    descending = np.arange(values.shape[0] - 1, -1, -1, dtype=np.int64)
    for descending_positions in np.array_split(descending, block_count):
        if descending_positions.size < cluster_count:
            return None
        positions = np.sort(descending_positions)
        block = values[positions]
        if np.unique(block, axis=0).shape[0] < cluster_count:
            return None
        centres = np.median(block, axis=0)
        scales = np.median(np.abs(block - centres), axis=0)
        if bool(np.any(scales == 0.0)):
            return None
        block_standardized = (block - centres) / scales
        initial = pam_build_indices(block_standardized, cluster_count=cluster_count)
        medoids, _ = pam_swap_indices(
            block_standardized,
            initial,
            maximum_passes=maximum_passes,
        )
        block_medoids = block_standardized[np.asarray(medoids, dtype=np.int64)]
        block_labels = _nearest(block_standardized, np.asarray(medoids, dtype=np.int64))
        mapping = _match_medoids(block_medoids, reference)
        nearest_full = _value_distance_columns(block_standardized, reference).T.argmin(axis=1)
        scores.append(adjusted_rand_index(mapping[block_labels], nearest_full))
    return np.asarray(scores, dtype=np.float64)


def _match_medoids(block_medoids: np.ndarray, full_medoids: np.ndarray) -> Int64Array:
    """Сопоставить медиоиды один к одному по минимальной суммарной дистанции."""
    best: tuple[float, tuple[int, ...]] | None = None
    for candidate in permutations(range(full_medoids.shape[0])):
        delta = block_medoids - full_medoids[np.asarray(candidate, dtype=np.int64)]
        cost = float(np.sum(delta * delta))
        if best is None or cost < best[0]:
            best = (cost, candidate)
    if best is None:
        raise ValueError("F15 stability requires at least one medoid matching")
    return np.asarray(best[1], dtype=np.int64)


def adjusted_rand_index(first: np.ndarray, second: np.ndarray) -> float:
    """Вычислить adjusted Rand index по целочисленным формулам пар."""
    left = np.asarray(first, dtype=np.int64)
    right = np.asarray(second, dtype=np.int64)
    if left.ndim != _VECTOR_NDIM or left.shape != right.shape:
        raise ValueError("ARI inputs must be equal-length vectors")
    if left.size < _MINIMUM_ARI_ITEMS:
        return 0.0
    _, left_inverse = np.unique(left, return_inverse=True)
    _, right_inverse = np.unique(right, return_inverse=True)
    left_count = int(left_inverse.max()) + 1
    right_count = int(right_inverse.max()) + 1
    joint = np.zeros((left_count, right_count), dtype=np.int64)
    np.add.at(joint, (left_inverse, right_inverse), 1)
    total_pairs = _pairs(left.size)
    left_pairs = sum(_pairs(int(value)) for value in np.sum(joint, axis=1))
    right_pairs = sum(_pairs(int(value)) for value in np.sum(joint, axis=0))
    joint_pairs = sum(_pairs(int(value)) for value in joint.ravel())
    if total_pairs == 0:
        return 0.0
    cross = left_pairs * right_pairs
    denominator = (left_pairs + right_pairs) * total_pairs - 2 * cross
    if denominator == 0:
        return 1.0 if joint_pairs == left_pairs == right_pairs else 0.0
    numerator = 2 * joint_pairs * total_pairs - 2 * cross
    return numerator / denominator


def _pairs(value: int) -> int:
    """Число неупорядоченных пар в одной ячейке таблицы сопряжённости."""
    return value * (value - 1) // 2
