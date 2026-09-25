"""F12: flatten observed multiscale candidates без хранения лишних arrays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lnt.characterization.f12_scales import ScaleObservation

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class CandidateTable:
    """Плоский finite candidate domain в scale-major, frequency-minor order."""

    scale_index: Int64Array
    frequencies_hz: Float64Array
    spectral_kurtosis: Float64Array


def observed_candidates(scales: Sequence[ScaleObservation]) -> CandidateTable:
    """Собрать только positive-power SK cells в объявленном scale order."""
    scale_parts: list[Int64Array] = []
    frequency_parts: list[Float64Array] = []
    kurtosis_parts: list[Float64Array] = []
    for scale_index, scale in enumerate(scales):
        if scale.reason_code is not None or scale.spectral_kurtosis.size == 0:
            continue
        finite = np.isfinite(scale.spectral_kurtosis)
        if not np.any(finite):
            continue
        scale_parts.append(np.full(int(np.count_nonzero(finite)), scale_index, dtype=np.int64))
        frequency_parts.append(np.asarray(scale.frequencies_hz[finite], dtype=np.float64))
        kurtosis_parts.append(np.asarray(scale.spectral_kurtosis[finite], dtype=np.float64))
    if not scale_parts:
        return CandidateTable(
            scale_index=np.empty(0, dtype=np.int64),
            frequencies_hz=np.empty(0, dtype=np.float64),
            spectral_kurtosis=np.empty(0, dtype=np.float64),
        )
    return CandidateTable(
        scale_index=np.concatenate(scale_parts),
        frequencies_hz=np.concatenate(frequency_parts),
        spectral_kurtosis=np.concatenate(kurtosis_parts),
    )
