"""F12: seeded magnitude-preserving FFT phase surrogates."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f12_input import zero_phase_means
from lnt.characterization.f12_scales import observe_scale

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f12_result import F12Declarations
    from lnt.characterization.f12_scales import ScaleObservation
    from lnt.characterization.phase_model import PhaseCycles

type Float64Array = NDArray[np.float64]

_INTERIOR_BIN_COUNT: Final = 2


def iter_phase_randomized_surrogates(
    residual: Float64Array,
    magnitudes: Float64Array,
    count: int,
    seed: int,
    checkpoint: Callable[[], None] | None = None,
) -> Iterator[Float64Array]:
    """Yield exact declared count из local ``default_rng(seed)`` stream.

    Все строго положительные interior bins получают независимые uniform phases
    на ``[0, 2*pi)``. DC и существующий Nyquist bin сохраняют исходные real
    endpoints; ``irfft`` тем самым задаёт exact conjugate symmetry real series.
    """
    values = np.asarray(residual, dtype=np.float64)
    amplitudes = np.asarray(magnitudes, dtype=np.float64)
    if (
        values.ndim != 1
        or values.size < 1
        or not np.all(np.isfinite(values))
        or amplitudes.shape != np.fft.rfft(values).shape
        or not np.all(np.isfinite(amplitudes))
        or np.any(amplitudes < 0.0)
        or count <= 0
        or seed < 0
    ):
        raise ValueError("F12 surrogate input or declared count/seed is invalid")
    generator = np.random.default_rng(seed)
    original = np.fft.rfft(values)
    for _ in range(count):
        if checkpoint is not None:
            checkpoint()
        randomized = np.empty(original.size, dtype=np.complex128)
        randomized[0] = complex(float(original[0].real), 0.0)
        if original.size > 1:
            randomized[-1] = complex(float(original[-1].real), 0.0)
        if original.size > _INTERIOR_BIN_COUNT:
            phases = generator.uniform(0.0, 2.0 * math.pi, size=original.size - _INTERIOR_BIN_COUNT)
            randomized[1:-1] = amplitudes[1:-1] * np.exp(1j * phases)
        yield np.fft.irfft(randomized, n=values.size)


def surrogate_global_maxima(  # noqa: PLR0913 - null pass needs every declared root
    residual: Float64Array,
    magnitudes: Float64Array,
    scales: tuple[ScaleObservation, ...],
    *,
    declarations: F12Declarations,
    phase: PhaseCycles,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> Float64Array:
    """Посчитать max SK каждого declared surrogate по всем доступным scales."""
    phase_means = zero_phase_means(declarations.phase_bins)
    maxima: list[float] = []
    for surrogate in iter_phase_randomized_surrogates(
        residual,
        magnitudes,
        declarations.surrogate_count,
        declarations.surrogate_seed,
        checkpoint,
    ):
        if checkpoint is not None:
            checkpoint()
        maximum = -math.inf
        for scale in scales:
            if scale.reason_code is not None:
                continue
            observed = observe_scale(
                surrogate,
                phase,
                phase_means,
                segment_samples=scale.segment_samples,
                declarations=declarations,
                resources=resources,
                checkpoint=checkpoint,
            )
            finite = observed.spectral_kurtosis[np.isfinite(observed.spectral_kurtosis)]
            if finite.size:
                maximum = max(maximum, float(np.max(finite)))
        maxima.append(maximum)
    return np.asarray(maxima, dtype=np.float64)
