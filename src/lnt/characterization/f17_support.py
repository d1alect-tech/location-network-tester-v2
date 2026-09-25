"""F17: input/resource validation, null passes and family-level QC reasons."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f17_coherence import estimate_cyclic_coherence
from lnt.characterization.f17_contract import (
    CYCLIC_FREQUENCY_OFF_GRID,
    NO_SIGNIFICANT_CELL,
    PHASE_REFERENCE_UNAVAILABLE,
    ZERO_DENOMINATOR,
)
from lnt.characterization.f17_permutation import fisher_yates_order, permuted_record
from lnt.characterization.f17_spectra import align_stft, collect_stft
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f17_coherence import CoherenceEstimate
    from lnt.characterization.f17_contract import F17Declarations
    from lnt.characterization.f17_frequency import FrequencyGrid
    from lnt.characterization.f17_permutation import CycleBlocks
    from lnt.characterization.f17_spectra import StftData
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans


def validate_f17_inputs(  # noqa: PLR0913, PLR0917 - полный shared input contract
    ch1_samples: np.ndarray,
    ch2_samples: np.ndarray,
    phase: PhaseCycles,
    ch1_means: PhaseMeans,
    ch2_means: PhaseMeans,
    declarations: F17Declarations,
    resources: ResourceLimits,
) -> tuple[np.ndarray, np.ndarray]:
    """Сверить finite channels, phase means и bounded resource limits."""
    first = np.asarray(ch1_samples)
    second = np.asarray(ch2_samples)
    if (
        first.ndim != 1
        or second.ndim != 1
        or first.size != second.size
        or not np.all(np.isfinite(first))
        or not np.all(np.isfinite(second))
    ):
        raise ValueError("F17 channels must be finite vectors on one sample grid")
    if (
        phase.sample_count != first.size
        or not math.isfinite(phase.sample_rate_hz)
        or phase.sample_rate_hz <= 0.0
        or declarations.surrogate_count > resources.max_surrogates
        or resources.deterministic_seed != declarations.surrogate_seed
        or declarations.maximum_stored_cells > resources.max_stored_trajectories
        or declarations.segment_samples > resources.hard_max_chunk_samples
    ):
        raise ValueError(
            "F17 inputs exceed declared resource or sample-grid contract (surrogate cap)"
        )
    shape = (declarations.phase_bins,)
    for means in (ch1_means, ch2_means):
        if (
            means.means_v.shape != shape
            or means.counts.shape != shape
            or means.valid_bins.shape != shape
            or not np.all(np.isfinite(means.means_v))
        ):
            raise ValueError("F17 phase means do not match locked phase bins")
    return first, second


def run_f17_null_distribution(  # noqa: PLR0913, PLR0917 - объявленный 199-pass scope
    first: np.ndarray,
    blocks: CycleBlocks,
    compact_reference: PhaseCycles,
    ch1_means: PhaseMeans,
    sample_rate_hz: float,
    declarations: F17Declarations,
    resources: ResourceLimits,
    reference: StftData,
    grid: FrequencyGrid,
    observed: CoherenceEstimate,
    checkpoint: Callable[[], None] | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Посчитать add-one p по 199 seeded complete-cycle permutations."""
    counts = np.zeros(grid.available.shape, dtype=np.int64)
    valid = np.asarray(observed.available, dtype=np.bool_).copy()
    rng = np.random.default_rng(declarations.surrogate_seed)
    for _ in range(declarations.surrogate_count):
        if checkpoint is not None:
            checkpoint()
        order = fisher_yates_order(blocks.count, rng)
        surrogate = permuted_record(first, blocks, order)
        transformed = collect_stft(
            surrogate,
            compact_reference,
            ch1_means,
            sample_rate_hz,
            declarations,
            resources,
            checkpoint,
        )
        transformed, _reference = align_stft(transformed, reference)
        estimate = estimate_cyclic_coherence(
            transformed.coefficients, reference.coefficients, transformed.bin_numbers, grid
        )
        tested = valid & estimate.available
        counts[tested] += (estimate.coherence[tested] >= observed.coherence[tested]).astype(
            np.int64
        )
        valid &= estimate.available
    return counts, valid


def f17_reasons(
    grid: FrequencyGrid,
    observed: CoherenceEstimate,
    cell_available: np.ndarray,
    significant: np.ndarray,
) -> set[str]:
    """Собрать только declared F17 QC codes для построенной сетки."""
    reasons: set[str] = set()
    if not bool(np.all(grid.alpha_on_grid)):
        reasons.add(CYCLIC_FREQUENCY_OFF_GRID)
    if bool(np.any(grid.available & ~observed.available)) or bool(
        np.any(grid.available & ~cell_available)
    ):
        reasons.add(ZERO_DENOMINATOR)
    if not bool(np.any(significant)):
        reasons.add(NO_SIGNIFICANT_CELL)
    return reasons


def terminal_phase_failure(phase: PhaseCycles) -> bool:
    """Не выдавать partial phase support за total reference failure."""
    if phase.status is not Status.UNAVAILABLE:
        return False
    return (
        phase.reason_code in PHASE_ROOT_REASON_CODES
        or phase.reason_code == PHASE_REFERENCE_UNAVAILABLE
        or phase.reason_code is None
    )
