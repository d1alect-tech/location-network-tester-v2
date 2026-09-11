"""Shared cycle-boundary primitives."""

import numpy as np
from numpy.typing import NDArray


def rising_zero_crossings(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return linearly interpolated rising zero crossings in sample coordinates."""
    below = values[:-1] <= 0.0
    above = values[1:] > 0.0
    indices = np.nonzero(below & above)[0]
    if indices.size == 0:
        return np.empty(0, dtype=np.float64)
    fractions = -values[indices] / (values[indices + 1] - values[indices])
    return indices.astype(np.float64) + fractions
