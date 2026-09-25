"""F17: полные qualified mains cycles и seeded Fisher-Yates surrogates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.phase_model import PhaseCycles

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.random import Generator

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True, kw_only=True)
class CycleBlocks:
    """Границы полных qualified cycles и их целочисленные half-open blocks."""

    starts: Float64Array
    ends: Float64Array
    sample_starts: Int64Array
    sample_ends: Int64Array
    valid: BoolArray

    @property
    def count(self) -> int:
        """Число полных qualified cycles."""
        return int(self.sample_starts.size)


def qualified_cycle_blocks(phase: PhaseCycles) -> CycleBlocks:
    """Оставить только полные finite valid cycles с положительным sample block."""
    starts = np.asarray(phase.cycle_start_samples, dtype=np.float64)
    ends = np.asarray(phase.cycle_end_samples, dtype=np.float64)
    valid = np.asarray(phase.cycle_valid, dtype=np.bool_)
    if starts.shape != ends.shape or valid.shape != starts.shape:
        raise ValueError("F17 phase cycle arrays do not share one shape")
    finite = np.isfinite(starts) & np.isfinite(ends)
    inside = (starts >= 0.0) & (ends <= float(phase.sample_count))
    positive = ends > starts
    keep = valid & finite & inside & positive
    starts = starts[keep]
    ends = ends[keep]
    sample_starts = np.ceil(starts).astype(np.int64)
    sample_ends = np.ceil(ends).astype(np.int64)
    nonempty = sample_ends > sample_starts
    starts = starts[nonempty]
    ends = ends[nonempty]
    sample_starts = sample_starts[nonempty]
    sample_ends = sample_ends[nonempty]
    if sample_starts.size > 1 and bool(np.any(sample_starts[1:] < sample_ends[:-1])):
        raise ValueError("F17 qualified cycle blocks overlap")
    return CycleBlocks(
        starts=starts,
        ends=ends,
        sample_starts=sample_starts,
        sample_ends=sample_ends,
        valid=np.ones(sample_starts.size, dtype=np.bool_),
    )


def cycle_sample_blocks(samples: np.ndarray, blocks: CycleBlocks) -> list[NDArray[np.float64]]:
    """Получить immutable-by-convention source blocks без разрезания циклов."""
    values = np.asarray(samples, dtype=np.float64)
    return [
        values[int(start) : int(stop)].copy()
        for start, stop in zip(blocks.sample_starts, blocks.sample_ends, strict=True)
    ]


def compact_samples(samples: np.ndarray, blocks: CycleBlocks) -> NDArray[np.float64]:
    """Склеить только qualified cycles в общий компактный record."""
    values = np.asarray(samples, dtype=np.float64)
    pieces = cycle_sample_blocks(values, blocks)
    if not pieces:
        return np.empty(0, dtype=np.float64)
    return np.concatenate(pieces).astype(np.float64, copy=False)


def compact_phase(phase: PhaseCycles, blocks: CycleBlocks) -> PhaseCycles:
    """Сохранить phase-cycle boundaries при compact surrogate record."""
    lengths = blocks.sample_ends - blocks.sample_starts
    starts = np.concatenate((np.asarray([0], dtype=np.int64), np.cumsum(lengths)[:-1]))
    ends = np.cumsum(lengths, dtype=np.int64)
    return PhaseCycles(
        sample_rate_hz=float(phase.sample_rate_hz),
        sample_count=int(ends[-1]) if ends.size else 0,
        cycle_start_samples=starts.astype(np.float64),
        cycle_end_samples=ends.astype(np.float64),
        cycle_valid=np.ones(ends.size, dtype=np.bool_),
        status=phase.status,
        reason_code=None,
    )


def fisher_yates_order(count: int, rng: Generator) -> Int64Array:
    """Сделать один seeded in-place Fisher-Yates permutation без global RNG."""
    if count <= 0:
        raise ValueError("F17 cycle count must be positive")
    order = np.arange(count, dtype=np.int64)
    for index in range(count - 1, 0, -1):
        swap = int(rng.integers(0, index + 1))
        left = int(order[index])
        order[index] = order[swap]
        order[swap] = left
    return order


def permute_cycle_samples(
    blocks: Sequence[NDArray[np.float64]], order: Int64Array
) -> NDArray[np.float64]:
    """Переставить целые cycle blocks в указанном порядке."""
    indices = np.asarray(order, dtype=np.int64)
    if (
        indices.ndim != 1
        or indices.size != len(blocks)
        or not np.array_equal(np.sort(indices), np.arange(len(blocks), dtype=np.int64))
    ):
        raise ValueError("F17 permutation must contain each cycle exactly once")
    if len(blocks) == 0:
        return np.empty(0, dtype=np.float64)
    lengths = {int(block.size) for block in blocks}
    if len(lengths) != 1:
        return np.concatenate([blocks[int(index)] for index in indices])
    return np.stack([blocks[int(index)] for index in indices])


def permuted_record(
    samples: np.ndarray, blocks: CycleBlocks, order: Int64Array
) -> NDArray[np.float64]:
    """Переставить source samples blockwise и вернуть compact one-dimensional record."""
    source = cycle_sample_blocks(samples, blocks)
    if len(source) == 0:
        return np.empty(0, dtype=np.float64)
    return np.concatenate([source[int(index)] for index in np.asarray(order, dtype=np.int64)])
