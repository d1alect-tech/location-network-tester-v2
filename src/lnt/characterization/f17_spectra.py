"""F17: bounded reuse of shared phase-residual STFT для observed и surrogate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.analysis_store.characterization_settings import StftSettings
from lnt.characterization.stft import ResidualStftChunk, stream_phase_residual_stft

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f17_contract import F17Declarations
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

    type FloatInput = NDArray[np.float32] | NDArray[np.float64]

type Int64Array = NDArray[np.int64]
type Complex128Array = NDArray[np.complex128]


@dataclass(frozen=True, slots=True, kw_only=True)
class StftData:
    """Полный positive-frequency cube для одного bounded channel pass."""

    bin_numbers: Int64Array
    frame_indices: Int64Array
    coefficients: Complex128Array


def extraction_settings(declarations: F17Declarations, sample_rate_hz: float) -> StftSettings:
    """Расширить declared STFT только до positive FFT grid для sideband lookup."""
    return StftSettings(
        window=declarations.window,
        segment_samples=declarations.segment_samples,
        overlap_fraction=declarations.overlap_fraction,
        detrend="constant",
        analysis_low_hz=0.0,
        analysis_high_hz=float(sample_rate_hz) / 2.0,
        nyquist_fraction_max=float(np.nextafter(0.5, 0.0)),
    )


def collect_stft(  # noqa: PLR0913, PLR0917 - полный bounded STFT вход
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    sample_rate_hz: float,
    declarations: F17Declarations,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None,
) -> StftData:
    """Собрать один shared-STFT pass, не материализуя surrogates заранее."""
    settings = extraction_settings(declarations, sample_rate_hz)
    chunks = list(
        stream_phase_residual_stft(
            samples,
            phase,
            means,
            sample_rate_hz=sample_rate_hz,
            settings=settings,
            resources=resources,
            checkpoint=checkpoint,
        )
    )
    return _assemble(chunks, sample_rate_hz / float(declarations.segment_samples))


def align_stft(first: StftData, second: StftData) -> tuple[StftData, StftData]:
    """Оставить только общие frame indices, чтобы cross-spectrum был aligned."""
    if not np.array_equal(first.bin_numbers, second.bin_numbers):
        raise ValueError("F17 channel STFT frequency grids differ")
    common, first_indices, second_indices = np.intersect1d(
        first.frame_indices, second.frame_indices, assume_unique=True, return_indices=True
    )
    return (
        StftData(
            bin_numbers=first.bin_numbers,
            frame_indices=common,
            coefficients=first.coefficients[:, first_indices],
        ),
        StftData(
            bin_numbers=second.bin_numbers,
            frame_indices=common,
            coefficients=second.coefficients[:, second_indices],
        ),
    )


def _assemble(chunks: list[ResidualStftChunk], resolution: float) -> StftData:
    """Склеить bounded STFT chunks по frame axis и сохранить exact bin labels."""
    if not chunks:
        return StftData(
            bin_numbers=np.empty(0, dtype=np.int64),
            frame_indices=np.empty(0, dtype=np.int64),
            coefficients=np.empty((0, 0), dtype=np.complex128),
        )
    bins = np.rint(chunks[0].frequencies_hz / resolution).astype(np.int64)
    for chunk in chunks[1:]:
        if not np.array_equal(bins, np.rint(chunk.frequencies_hz / resolution).astype(np.int64)):
            raise ValueError("F17 STFT chunks changed frequency grid")
    return StftData(
        bin_numbers=bins,
        frame_indices=np.concatenate([chunk.frame_indices for chunk in chunks]),
        coefficients=np.concatenate([chunk.coefficients for chunk in chunks], axis=1).astype(
            np.complex128, copy=False
        ),
    )
