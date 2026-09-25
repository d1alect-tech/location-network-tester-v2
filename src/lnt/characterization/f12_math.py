"""F12: формула Antoni's spectral kurtosis и phase-support normalization."""

from __future__ import annotations

from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f12_contract import PHASE_REFERENCE_UNAVAILABLE
from lnt.characterization.phase import PHASE_ROOT_REASON_CODES

type Float64Array = NDArray[np.float64]

_COEFFICIENT_NDIM: Final = 2
_MINIMUM_ESTIMATOR_FRAMES: Final = 2


def declared_phase_reason(code: str) -> str:
    """Нормализовать любой phase-root code в closed F12 vocabulary."""
    return PHASE_REFERENCE_UNAVAILABLE if code in PHASE_ROOT_REASON_CODES else code


def antoni_spectral_kurtosis(coefficients: NDArray[np.complex128]) -> Float64Array:
    """Вычислить объявленный estimator для каждой строки STFT.

    ``M`` — число полных frame columns. Нулевой frequency-bin second moment
    не получает выдуманное число: ячейка остаётся NaN и не входит в конечный
    family-wide p-value list.
    """
    values = np.asarray(coefficients, dtype=np.complex128)
    if (
        values.ndim != _COEFFICIENT_NDIM
        or values.shape[1] < _MINIMUM_ESTIMATOR_FRAMES
        or not np.all(np.isfinite(values))
    ):
        raise ValueError("F12 Antoni estimator needs a finite coefficient matrix with M >= 2")
    frame_count = values.shape[1]
    power = np.abs(values) ** 2
    second_moment = np.sum(power, axis=1)
    fourth_moment = np.sum(power * power, axis=1)
    return antoni_from_moments(second_moment, fourth_moment, frame_count)


def antoni_from_moments(
    second_moment: Float64Array, fourth_moment: Float64Array, frame_count: int
) -> Float64Array:
    """Применить exact formula к уже накопленным per-frequency moments."""
    second = np.asarray(second_moment, dtype=np.float64)
    fourth = np.asarray(fourth_moment, dtype=np.float64)
    if (
        second.shape != fourth.shape
        or second.ndim != 1
        or frame_count < _MINIMUM_ESTIMATOR_FRAMES
        or not np.all(np.isfinite(second))
        or not np.all(np.isfinite(fourth))
    ):
        raise ValueError("F12 Antoni moments need matching finite vectors and M >= 2")
    result = np.full(second.shape, np.nan, dtype=np.float64)
    supported = second > 0.0
    result[supported] = (
        frame_count
        / (frame_count - 1.0)
        * ((frame_count + 1.0) * fourth[supported] / second[supported] ** 2 - 2.0)
    )
    return result
