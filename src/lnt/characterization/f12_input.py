"""F12: bounded phase-residual materialization и qualified span для record-spectrum null."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f16_segments import qualified_spans, replay_gaps
from lnt.characterization.phase import phase_residual
from lnt.characterization.phase_model import PhaseCycles, PhaseMeans
from lnt.characterization.records import Status
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvents

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type Span = tuple[int, int]


def materialize_phase_residual(
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[Float64Array, int]:
    """Собрать полный residual bounded chunks без смены sample grid."""
    sample_count = int(samples.size)
    if sample_count * np.dtype(np.float64).itemsize > resources.max_work_bytes:
        raise InputError("F12 full residual exceeds max_work_bytes")
    capacity = min(
        int(resources.chunk_samples),
        int(resources.hard_max_chunk_samples),
        int(resources.max_work_bytes) // 64,
    )
    if capacity <= 0:
        raise InputError("F12 residual chunk capacity is zero")
    result = np.empty(sample_count, dtype=np.float64)
    qualified = 0
    for start in range(0, sample_count, capacity):
        if checkpoint is not None:
            checkpoint()
        stop = min(sample_count, start + capacity)
        values, valid = phase_residual(samples, phase, means, start, stop, resources=resources)
        result[start:stop] = values
        qualified += int(np.count_nonzero(valid))
    return result, qualified


def longest_qualified_span(  # noqa: PLR0913, PLR0917 - shared phase root, gaps и остаток
    samples: FloatInput,
    phase: PhaseCycles,
    means: PhaseMeans,
    inventory: RootEvents,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[Span, PhaseCycles] | None:
    """Выбрать самый длинный qualified span и перебазировать корень фазы на него.

    Span берётся из того же :func:`qualified_spans`, что и F16, поэтому корень
    фазы не покрывает запись целиком, а выход за его край и root-event gaps
    одинаково исключаются: измерение никогда не сшивает разрыв. ``None`` означает
    структурное отсутствие span, а не нулевой остаток.
    """
    gaps = replay_gaps(inventory, int(samples.size), checkpoint)
    support = qualified_spans(samples, phase, means, gaps, resources, checkpoint)
    if not support.spans:
        return None
    # max берёт первый максимум при равенстве, поэтому выбор детерминирован.
    # ponytail: считается только самый длинный span, более короткие отбрасываются.
    # Потолок — запись с несколькими разрывами теряет их хвосты; учёт честный через
    # пару sample_count/qualified_sample_count. Склейка спанов дала бы ложные
    # спектральные скачки на стыках, поэтому путь улучшения — не суммирование, а
    # отдельный declared код «несколько спанов», если понадобится явный caveat.
    start, stop = max(support.spans, key=lambda span: span[1] - span[0])
    return (start, stop), _rebased_phase(phase, start, stop)


def _rebased_phase(phase: PhaseCycles, start: int, stop: int) -> PhaseCycles:
    """Сдвинуть границы циклов на ``start``, не обрезая и не ограничивая концы.

    Доли ``(position - cycle_start) / (cycle_end - cycle_start)`` при общем
    сдвиге обоих концов сохраняются точно, поэтому номер phase bin, вычитаемая
    средняя и все значения куртозиса остаются прежними. Отрицательное начало
    первого цикла и конец последнего цикла за ``sample_count`` допустимы:
    :func:`phase_bins_impl` требует только ``cycles >= 0`` и ``position <
    cycle_end``. Clamp конца перемасштабировал бы долю и молча сменил бы bin.
    """
    keep = (phase.cycle_end_samples > start) & (phase.cycle_start_samples < stop)
    return PhaseCycles(
        sample_rate_hz=phase.sample_rate_hz,
        sample_count=stop - start,
        cycle_start_samples=phase.cycle_start_samples[keep] - start,
        cycle_end_samples=phase.cycle_end_samples[keep] - start,
        cycle_valid=phase.cycle_valid[keep],
        status=phase.status,
        reason_code=phase.reason_code,
    )


def zero_phase_means(phase_bins: int) -> PhaseMeans:
    """Создать явное zero-mean root, не меняющий STFT implementation."""
    return PhaseMeans(
        means_v=np.zeros(phase_bins, dtype=np.float64),
        counts=np.ones(phase_bins, dtype=np.int64),
        valid_bins=np.ones(phase_bins, dtype=np.bool_),
        status=Status.AVAILABLE,
        reason_code=None,
    )
