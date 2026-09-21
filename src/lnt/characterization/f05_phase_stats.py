"""F05 uniform phase-bin moments of the measured channel over the CH2 cycles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.phase_model import phase_bins_impl
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

    from lnt.characterization.event_models import RootEvent
    from lnt.characterization.phase_model import PhaseCycles

METHOD: Final = "uniform_phase_bin_moments"
PHASE_BINS: Final = 64
MINIMUM_SUPPORT_PER_BIN: Final = 20
VARIANCE_DDOF: Final = 1
EVENT_SOURCE: Final = "root_events"
CIRCULAR_AVERAGE: Final = "unit_vector"

_PHASE_UNAVAILABLE: Final = "phase_reference_unavailable"
_INSUFFICIENT_SUPPORT: Final = "insufficient_support"

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type BoolArray = NDArray[np.bool_]

__all__ = [
    "CIRCULAR_AVERAGE",
    "EVENT_SOURCE",
    "METHOD",
    "MINIMUM_SUPPORT_PER_BIN",
    "PHASE_BINS",
    "VARIANCE_DDOF",
    "F05Result",
    "compute_f05_phase_conditioned_statistics",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class F05Result:
    """Bounded F05 outcome over the declared uniform phase bins."""

    status: Status
    reason_codes: tuple[str, ...]
    means_v: Float64Array
    variances_v2: Float64Array
    mean_squares_v2: Float64Array
    event_probabilities: Float64Array
    counts: Int64Array
    valid_bins: BoolArray
    event_phase_resultant: float | None
    event_phase_mean_rad: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _Accumulators:
    """Per-bin accumulators, never a record-sized temporary."""

    sums: Float64Array
    sum_squares: Float64Array
    counts: Int64Array
    indicator_counts: Int64Array


def compute_f05_phase_conditioned_statistics(  # noqa: PLR0913 - объявленные гейты рецепта
    samples: FloatInput,
    phase: PhaseCycles,
    events: tuple[RootEvent, ...],
    *,
    phase_bins: int = PHASE_BINS,
    minimum_support_per_bin: int = MINIMUM_SUPPORT_PER_BIN,
    variance_ddof: int = VARIANCE_DDOF,
    checkpoint: Callable[[], None] | None = None,
) -> F05Result:
    """Accumulate per-bin moments of the measured channel over the CH2 cycles.

    Обход идёт по циклам, поэтому временные массивы ограничены длиной цикла
    (её ограничивают бюджеты корня фазы), а не размером записи. Бин считается
    валидным при ``n_b >= minimum_support_per_bin``; значения невалидных бинов
    остаются нулями и объявляются маской, а не выдаются за измерение.
    """
    bins = int(phase_bins)
    if bins <= 0:
        raise ValueError("phase_bins must be positive")
    ddof = int(variance_ddof)
    if ddof < 1:
        raise ValueError("variance_ddof must be positive")
    if phase.status is Status.UNAVAILABLE:
        # Отказ корня фазы сворачивается в объявленный код F05: чужие коды
        # (no_sync_reference, grid_unstable, ...) в словаре семейства нет.
        return _unavailable(bins)
    if checkpoint is not None:
        checkpoint()
    accumulators = _accumulate(samples, phase, events, bins, checkpoint)
    counts = accumulators.counts
    valid = counts >= int(minimum_support_per_bin)
    means, variances, mean_squares, probabilities = _moments(accumulators, valid, ddof)
    resultant, direction = _event_phase(phase, events)
    if np.all(valid):
        status, reasons = Status.AVAILABLE, ()
    else:
        status = Status.PARTIAL if np.any(valid) else Status.UNAVAILABLE
        reasons = (_INSUFFICIENT_SUPPORT,)
    return F05Result(
        status=status,
        reason_codes=reasons,
        means_v=means,
        variances_v2=variances,
        mean_squares_v2=mean_squares,
        event_probabilities=probabilities,
        counts=counts,
        valid_bins=valid,
        event_phase_resultant=resultant,
        event_phase_mean_rad=direction,
    )


def _accumulate(
    samples: FloatInput,
    phase: PhaseCycles,
    events: tuple[RootEvent, ...],
    bins: int,
    checkpoint: Callable[[], None] | None,
) -> _Accumulators:
    """One pass over the qualified cycles, chunked by cycle rather than by record."""
    sums = np.zeros(bins, dtype=np.float64)
    sum_squares = np.zeros(bins, dtype=np.float64)
    counts = np.zeros(bins, dtype=np.int64)
    indicator_counts = np.zeros(bins, dtype=np.int64)
    size = min(int(np.asarray(samples).size), int(phase.sample_count))
    for index in range(int(phase.cycle_start_samples.size)):
        if checkpoint is not None:
            checkpoint()
        if not bool(phase.cycle_valid[index]):
            continue
        start = max(0, int(np.floor(float(phase.cycle_start_samples[index]))))
        stop = min(size, int(np.ceil(float(phase.cycle_end_samples[index]))))
        if stop <= start:
            continue
        values = np.asarray(samples[start:stop], dtype=np.float64)
        indices, valid = phase_bins_impl(phase, start, stop, bins)
        valid &= np.isfinite(values)
        sums += np.bincount(indices[valid], weights=values[valid], minlength=bins)
        sum_squares += np.bincount(indices[valid], weights=values[valid] ** 2, minlength=bins)
        counts += np.bincount(indices[valid], minlength=bins)
        covered = _covered(start, stop, events)
        indicator_counts += np.bincount(indices[valid & covered], minlength=bins)
    return _Accumulators(
        sums=sums,
        sum_squares=sum_squares,
        counts=counts,
        indicator_counts=indicator_counts,
    )


def _moments(
    accumulators: _Accumulators,
    valid: BoolArray,
    ddof: int,
) -> tuple[Float64Array, Float64Array, Float64Array, Float64Array]:
    """Mean, variance, mean square and event probability; invalid bins stay zero.

    Дисперсия берётся из сумм, а не двухпроходно: это потоковый обход с
    ограниченной памятью, поэтому при большом среднем и малом разбросе теряется
    точность — тот же компромисс, что у корневых потоковых аккумуляторов.
    """
    counts = accumulators.counts
    safe = np.where(valid, counts, 1).astype(np.float64)
    spread = counts > ddof
    squared = np.where(
        spread, accumulators.sum_squares - accumulators.sums**2 / np.where(spread, counts, 1), 0.0
    )
    return (
        np.where(valid, accumulators.sums / safe, 0.0),
        np.where(spread, squared / np.where(spread, counts - ddof, 1), 0.0),
        np.where(valid, accumulators.sum_squares / safe, 0.0),
        np.where(valid, accumulators.indicator_counts / safe, 0.0),
    )


def _covered(start: int, stop: int, events: tuple[RootEvent, ...]) -> BoolArray:
    """Event indicator over one slice: the whole delimited span, not just the peak."""
    covered = np.zeros(stop - start, dtype=np.bool_)
    for event in events:
        low = max(int(event.start_sample), start)
        high = min(int(event.end_sample) + 1, stop)
        if low < high:
            covered[low - start : high - start] = True
    return covered


def _event_phase(
    phase: PhaseCycles, events: tuple[RootEvent, ...]
) -> tuple[float | None, float | None]:
    """Circular resultant and mean direction of every event peak, by unit vectors.

    Линейное среднее углов запрещено спекой: пики на 350 и 10 градусах дали бы
    направление 180 градусов вместо 0. События, чей пик не попал в валидный
    цикл, в распределение не входят и фазы им не приписываются.
    """
    if not events or phase.cycle_start_samples.size == 0:
        return None, None
    peaks = np.array([int(event.peak_sample) for event in events], dtype=np.float64)
    starts = phase.cycle_start_samples
    ends = phase.cycle_end_samples
    cycles = np.searchsorted(starts, peaks, side="right") - 1
    present = cycles >= 0
    safe = np.maximum(cycles, 0)
    present &= phase.cycle_valid[safe]
    present &= peaks < ends[safe]
    if not np.any(present):
        return None, None
    angles = (
        ((peaks[present] - starts[safe[present]]) / (ends[safe[present]] - starts[safe[present]]))
        * 2.0
        * np.pi
    )
    total_cos = float(np.sum(np.cos(angles)))
    total_sin = float(np.sum(np.sin(angles)))
    count = float(np.count_nonzero(present))
    return float(np.hypot(total_cos, total_sin)) / count, float(np.arctan2(total_sin, total_cos))


def _unavailable(bins: int) -> F05Result:
    """Unavailable result with the declared code and no fabricated bin value."""
    zeros = np.zeros(bins, dtype=np.float64)
    return F05Result(
        status=Status.UNAVAILABLE,
        reason_codes=(_PHASE_UNAVAILABLE,),
        means_v=zeros,
        variances_v2=zeros.copy(),
        mean_squares_v2=zeros.copy(),
        event_probabilities=zeros.copy(),
        counts=np.zeros(bins, dtype=np.int64),
        valid_bins=np.zeros(bins, dtype=np.bool_),
        event_phase_resultant=None,
        event_phase_mean_rad=None,
    )
