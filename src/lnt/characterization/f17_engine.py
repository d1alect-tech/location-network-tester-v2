"""F17: bounded two-channel cyclic coherence with cycle-permutation null."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.f17_coherence import estimate_cyclic_coherence
from lnt.characterization.f17_contract import (
    ARTIFACT_LIMIT,
    CYCLIC_FREQUENCY_OFF_GRID,
    INSUFFICIENT_CYCLES,
    INSUFFICIENT_FRAMES,
    PHASE_REFERENCE_UNAVAILABLE,
    ZERO_DENOMINATOR,
)
from lnt.characterization.f17_frequency import build_frequency_grid
from lnt.characterization.f17_multiplicity import (
    benjamini_hochberg_masked,
    significant_cells,
)
from lnt.characterization.f17_permutation import (
    compact_phase,
    compact_samples,
    qualified_cycle_blocks,
)
from lnt.characterization.f17_result import F17Result, select_stored_cells, unavailable_f17
from lnt.characterization.f17_spectra import align_stft, collect_stft
from lnt.characterization.f17_support import (
    f17_reasons,
    run_f17_null_distribution,
    terminal_phase_failure,
    validate_f17_inputs,
)
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f17_contract import F17Declarations
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

__all__ = ["compute_f17_cyclic_spectral_coherence"]


def compute_f17_cyclic_spectral_coherence(  # noqa: C901, PLR0911, PLR0913
    *,
    ch1_samples: np.ndarray,
    ch2_samples: np.ndarray,
    phase: PhaseCycles,
    ch1_means: PhaseMeans,
    ch2_means: PhaseMeans,
    declarations: F17Declarations,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F17Result:
    """Считать F17 из синхронных каналов, shared phase и 199 cycle surrogates."""
    if checkpoint is not None:
        checkpoint()
    first, second = validate_f17_inputs(
        ch1_samples, ch2_samples, phase, ch1_means, ch2_means, declarations, resources
    )
    sample_count = int(first.size)
    if terminal_phase_failure(phase):
        return unavailable_f17((PHASE_REFERENCE_UNAVAILABLE,), sample_count)
    if ch1_means.status is Status.UNAVAILABLE or ch2_means.status is Status.UNAVAILABLE:
        return unavailable_f17((PHASE_REFERENCE_UNAVAILABLE,), sample_count)
    blocks = qualified_cycle_blocks(phase)
    if blocks.count < declarations.minimum_complete_cycles:
        return unavailable_f17((INSUFFICIENT_CYCLES,), sample_count)
    compact_first = compact_samples(first, blocks)
    compact_second = compact_samples(second, blocks)
    compact_reference = compact_phase(phase, blocks)
    measured = collect_stft(
        compact_first,
        compact_reference,
        ch1_means,
        float(phase.sample_rate_hz),
        declarations,
        resources,
        checkpoint,
    )
    reference = collect_stft(
        compact_second,
        compact_reference,
        ch2_means,
        float(phase.sample_rate_hz),
        declarations,
        resources,
        checkpoint,
    )
    measured, reference = align_stft(measured, reference)
    if measured.frame_indices.size < declarations.minimum_frames:
        return unavailable_f17((INSUFFICIENT_FRAMES,), sample_count)
    grid = build_frequency_grid(declarations, float(phase.sample_rate_hz))
    observed = estimate_cyclic_coherence(
        measured.coefficients, reference.coefficients, measured.bin_numbers, grid
    )
    if not bool(np.any(grid.available)):
        return unavailable_f17((CYCLIC_FREQUENCY_OFF_GRID,), sample_count)
    if not bool(np.any(observed.available)):
        codes = {ZERO_DENOMINATOR}
        if not bool(np.all(grid.alpha_on_grid)):
            codes.add(CYCLIC_FREQUENCY_OFF_GRID)
        return unavailable_f17(tuple(sorted(codes)), sample_count)
    null_counts, cell_available = run_f17_null_distribution(
        first,
        blocks,
        compact_reference,
        ch1_means,
        phase.sample_rate_hz,
        declarations,
        resources,
        reference,
        grid,
        observed,
        checkpoint,
    )
    if not bool(np.any(cell_available)):
        codes = {ZERO_DENOMINATOR}
        if not bool(np.all(grid.alpha_on_grid)):
            codes.add(CYCLIC_FREQUENCY_OFF_GRID)
        return unavailable_f17(tuple(sorted(codes)), sample_count)
    raw_p = np.full(grid.available.shape, np.nan, dtype=np.float64)
    raw_p[cell_available] = (null_counts[cell_available] + 1.0) / (
        float(declarations.surrogate_count) + 1.0
    )
    adjusted = benjamini_hochberg_masked(raw_p, cell_available)
    significant = significant_cells(adjusted, cell_available, declarations.false_discovery_rate)
    reasons = f17_reasons(grid, observed, cell_available, significant)
    stored = select_stored_cells(
        observed.cyclic_spectrum,
        observed.coherence,
        raw_p,
        adjusted,
        observed.segment_support,
        significant,
        maximum=declarations.maximum_stored_cells,
    )
    stored_spectrum, stored_coherence, stored_raw, stored_adjusted, stored_support, capped = stored
    if capped:
        reasons.add(ARTIFACT_LIMIT)
    flat = np.flatnonzero(significant.ravel())[: int(stored_spectrum.size)]
    shape = grid.frequencies_hz.size
    stored_alpha = np.empty(0, dtype=np.float64)
    stored_frequency = np.empty(0, dtype=np.float64)
    if flat.size:
        stored_alpha = np.asarray(declarations.cyclic_frequencies_hz)[flat // shape]
        stored_frequency = grid.frequencies_hz[flat % shape]
    cyclic = np.where(cell_available, observed.cyclic_spectrum, np.nan + 1j * np.nan)
    coherence = np.where(cell_available, observed.coherence, np.nan)
    support = np.where(cell_available, observed.segment_support, 0).astype(np.int64)
    return F17Result(
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=tuple(sorted(reasons)),
        cyclic_frequencies_hz=np.asarray(declarations.cyclic_frequencies_hz, dtype=np.float64),
        frequencies_hz=grid.frequencies_hz,
        cyclic_spectrum=cyclic,
        coherence=coherence,
        raw_p_value=raw_p,
        bh_p_value=adjusted,
        segment_support=support,
        cell_available=cell_available,
        significant=significant,
        stored_alpha_hz=stored_alpha,
        stored_frequency_hz=stored_frequency,
        stored_cyclic_spectrum=stored_spectrum,
        stored_coherence=stored_coherence,
        stored_raw_p_value=stored_raw,
        stored_bh_p_value=stored_adjusted,
        stored_segment_support=stored_support,
        sample_count=sample_count,
        qualified_sample_count=int(compact_first.size),
        qualified_cycle_count=blocks.count,
        frame_count=int(measured.frame_indices.size),
        tested_cell_count=int(np.count_nonzero(cell_available)),
        significant_cell_count=int(np.count_nonzero(significant)),
        stored_cell_count=int(stored_spectrum.size),
        omitted_cell_count=int(np.count_nonzero(significant) - stored_spectrum.size),
    )
