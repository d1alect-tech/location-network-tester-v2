"""Public records for bounded local transforms."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

_DECAY_TARGET = 1e-6

__all__ = ["TransformChunk", "TransformSpec", "required_sos_halo"]


def required_sos_halo(sos: NDArray[np.float64]) -> int:
    """Return the default pad or 1e-6 pole-decay starting halo, whichever is larger."""
    sections = int(sos.shape[0])
    padlen = 3 * (
        2 * sections
        + 1
        - min(int(np.count_nonzero(sos[:, 2] == 0.0)), int(np.count_nonzero(sos[:, 5] == 0.0)))
    )
    radius = max(
        (float(abs(pole)) for section in sos for pole in np.roots(section[3:])),
        default=0.0,
    )
    if radius == 0.0:
        return padlen
    if not radius < 1.0:
        raise ValueError("SOS denominator poles must lie inside the unit circle")
    return max(padlen, math.ceil(math.log(_DECAY_TARGET) / math.log(radius)))


@dataclass(frozen=True, slots=True)
class TransformSpec:
    """One zero-phase SOS transform, optionally detrended and made analytic."""

    sos: NDArray[np.float64]
    analytic: bool = False
    detrend: bool = False
    analytic_halo_samples: int = 0

    def __post_init__(self) -> None:
        """Reject an impossible finite Hilbert window."""
        if self.analytic_halo_samples < 0:
            raise ValueError("analytic_halo_samples must be nonnegative")


@dataclass(frozen=True, slots=True)
class TransformChunk:
    """A supported or explicitly unavailable half-open sample interval."""

    start_sample: int
    stop_sample: int
    values: NDArray[np.float64] | NDArray[np.complex128] | None
    halo_samples: int
    reason_code: str | None
