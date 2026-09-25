"""F18: два declared surrogate null-ансамбля, по одному суррогату в памяти."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f18_frames import triad_coefficients
from lnt.characterization.f18_math import triad_bicoherence
from lnt.characterization.f18_surrogate import (
    F18ExceedanceCounter,
    iaaft_surrogate,
    phase_randomized_surrogate,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

    from lnt.analysis_store.characterization_settings import ResourceLimits, StftSettings
    from lnt.characterization.f18_result import F18Declarations
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type Checkpoint = Callable[[], None] | None

_PHASE_RANDOMIZED_STREAM: Final = 0
_IAAFT_STREAM: Final = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class F18NullPlan:
    """Один declared null pass: источник, framing и куда складывать превышения."""

    residual: Float64Array
    phase: PhaseCycles
    means: PhaseMeans
    declarations: F18Declarations
    settings: StftSettings
    resources: ResourceLimits
    sample_rate_hz: float
    distinct_bins: Int64Array
    rows: Int64Array
    observed: Float64Array


def run_both_nulls(
    plan: F18NullPlan, checkpoint: Checkpoint
) -> tuple[F18ExceedanceCounter, F18ExceedanceCounter, int]:
    """Прогнать оба declared ансамбля и вернуть их счётчики и число IAAFT-сходимостей."""
    phase_counter = _phase_randomized_pass(plan, checkpoint)
    iaaft_counter, converged = _iaaft_pass(plan, checkpoint)
    return phase_counter, iaaft_counter, converged


def _phase_randomized_pass(plan: F18NullPlan, checkpoint: Checkpoint) -> F18ExceedanceCounter:
    """Surrogate-only null: модули record FFT, случайные фазы из child-потока seed."""
    declarations = plan.declarations
    rng = np.random.default_rng([declarations.surrogate_seed, _PHASE_RANDOMIZED_STREAM])
    counter = F18ExceedanceCounter(observed=plan.observed)
    for _ in range(declarations.phase_randomized_surrogate_count):
        _checkpoint(checkpoint)
        counter.add(
            _surrogate_bicoherence(
                plan, phase_randomized_surrogate(plan.residual, rng=rng), checkpoint
            )
        )
    return counter


def _iaaft_pass(plan: F18NullPlan, checkpoint: Checkpoint) -> tuple[F18ExceedanceCounter, int]:
    """Консервативный IAAFT null; несошедшийся суррогат исключается и учитывается."""
    declarations = plan.declarations
    rng = np.random.default_rng([declarations.surrogate_seed, _IAAFT_STREAM])
    counter = F18ExceedanceCounter(observed=plan.observed)
    converged = 0
    for _ in range(declarations.iaaft_surrogate_count):
        _checkpoint(checkpoint)
        surrogate, error = iaaft_surrogate(
            plan.residual,
            rng=rng,
            iterations=declarations.iaaft_iterations,
            tolerance=declarations.iaaft_relative_rms_magnitude_tolerance,
        )
        if error <= declarations.iaaft_relative_rms_magnitude_tolerance:
            converged += 1
            counter.add(_surrogate_bicoherence(plan, surrogate, checkpoint))
    return counter, converged


def _surrogate_bicoherence(
    plan: F18NullPlan, surrogate: Float64Array, checkpoint: Checkpoint
) -> Float64Array:
    """Прогнать один суррогат по тому же shared framing-пути, что и наблюдение."""
    coefficients = triad_coefficients(
        surrogate,
        plan.phase,
        plan.means,
        sample_rate_hz=plan.sample_rate_hz,
        settings=plan.settings,
        resources=plan.resources,
        distinct_bins=plan.distinct_bins,
        checkpoint=checkpoint,
    )
    return triad_bicoherence(coefficients, plan.rows).bicoherence_squared


def _checkpoint(checkpoint: Checkpoint) -> None:
    if checkpoint is not None:
        checkpoint()
