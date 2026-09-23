"""F08 bounded_single_damped_sinusoid_fit поверх готового корневого инвентаря."""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.f08_event import event_outcome
from lnt.characterization.f08_result import (
    OVERLAPPING_EVENTS,
    TOO_FEW_SAMPLES,
    F08Result,
)
from lnt.characterization.f08_shape import (
    LOCKED_BASELINE,
    Gates,
    guard_span_bounds,
    initial_damped_sinusoid_seed,
    validate_gates,
)
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.event_models import RootEvent

type FloatInput = NDArray[np.float32] | NDArray[np.float64]

__all__ = [
    "LOCKED_BASELINE",
    "Gates",
    "compute_f08_transient_morphology",
    "guard_span_bounds",
    "initial_damped_sinusoid_seed",
]


def compute_f08_transient_morphology(  # noqa: PLR0913 - объявленные гейты рецепта явны
    record: FloatInput,
    events: tuple[RootEvent, ...],
    *,
    sample_rate_hz: float,
    baseline: str,
    ringing_frequency_low_hz: float,
    ringing_frequency_high_hz: float,
    decay_time_minimum_samples: int,
    decay_time_max_s: float,
    amplitude_maximum_peak_multiple: float,
    phase_low_rad: float,
    phase_high_rad: float,
    maximum_function_evaluations: int,
    minimum_snr_db: float,
    residual_fraction_max: float,
    minimum_zero_crossings: int,
    maximum_events: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F08Result:
    """Морфология каждого объявленного события: прямые величины и фит затухания.

    События берутся из готового корневого инвентаря (как у F02 и F05), поэтому
    детектор здесь не вызывается и не дублируется. По каждому событию: детренд
    внутри границ плюс guard одной длительности с каждой стороны (``baseline``
    залочен рецептом как ``linear_detrend``), прямые величины ``t_rise_s``,
    ``v_peak_v``, ``v2_s``, ``n_zc``, затем ограниченный фит
    ``y = A exp(-t / tau_d) sin(2 pi f_d t + phi) + c`` по спеку:401-412. Отказ
    формы оставляет ``f_d_hz``, ``tau_d_s``, ``zeta`` и остаточную долю пустыми:
    частота, выведенная из неописанной формы, была бы выдумана.
    """
    if checkpoint is not None:
        checkpoint()
    if baseline != LOCKED_BASELINE:
        raise ValueError(f"baseline must be {LOCKED_BASELINE!r}")
    gates = Gates(
        rate_hz=float(sample_rate_hz),
        ringing_low_hz=float(ringing_frequency_low_hz),
        ringing_high_hz=float(ringing_frequency_high_hz),
        tau_min_samples=int(decay_time_minimum_samples),
        tau_max_s=float(decay_time_max_s),
        amplitude_multiple=float(amplitude_maximum_peak_multiple),
        phase_low_rad=float(phase_low_rad),
        phase_high_rad=float(phase_high_rad),
        maximum_evaluations=int(maximum_function_evaluations),
        minimum_snr_db=float(minimum_snr_db),
        residual_fraction_max=float(residual_fraction_max),
        minimum_zero_crossings=int(minimum_zero_crossings),
        maximum_events=int(maximum_events),
    )
    validate_gates(gates)
    # Объявленный бюджет не расходуется: сложность O(K * L * iters) (спека:422),
    # ограничивают её maximum_function_evaluations и maximum_events.
    _ = resources
    samples = np.asarray(record, dtype=np.float64)
    total = len(events)
    if total == 0:
        return _unavailable((TOO_FEW_SAMPLES,), 0)
    if _overlaps(events):
        return _unavailable((OVERLAPPING_EVENTS,), total)
    kept = events[: gates.maximum_events]
    omitted = total - len(kept)
    outcomes = [event_outcome(samples, event, gates) for event in kept]
    codes = tuple(sorted({item.code for item in outcomes if item.code is not None}))
    fitted = any(item.f_d_hz is not None for item in outcomes)
    # Отказ ни одного события не прячет уже измеренные прямые величины (F08-18):
    # измеренная амплитуда, интеграл и пересечения от фита не зависят.
    tail: tuple[None, ...] = (None,) * omitted
    return F08Result(
        status=_status(codes, fitted=fitted),
        reason_codes=codes,
        t_rise_s=(*(item.t_rise_s for item in outcomes), *tail),
        v_peak_v=(*(item.v_peak_v for item in outcomes), *tail),
        v2_s=(*(item.v2_s for item in outcomes), *tail),
        n_zc=(*(item.n_zc for item in outcomes), *tail),
        f_d_hz=(*(item.f_d_hz for item in outcomes), *tail),
        tau_d_s=(*(item.tau_d_s for item in outcomes), *tail),
        zeta=(*(item.zeta for item in outcomes), *tail),
        residual_fraction=(*(item.residual_fraction for item in outcomes), *tail),
        evaluated_event_count=len(kept),
        omitted_event_count=omitted,
    )


def _status(codes: tuple[str, ...], *, fitted: bool) -> Status:
    """Статус инвентаря: без подогнанного события — UNAVAILABLE, иначе по кодам."""
    if not fitted:
        return Status.UNAVAILABLE
    return Status.PARTIAL if codes else Status.AVAILABLE


def _overlaps(events: tuple[RootEvent, ...]) -> bool:
    """Пересечение объявленных спанов делает guard-окна неоднозначными."""
    ordered = sorted(events, key=lambda item: item.start_sample)
    return any(
        current.start_sample <= previous.end_sample for previous, current in pairwise(ordered)
    )


def _unavailable(codes: tuple[str, ...], total: int) -> F08Result:
    """Отказ без выдуманных величин: None на каждое объявленное событие."""
    blanks: tuple[None, ...] = (None,) * total
    return F08Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        t_rise_s=blanks,
        v_peak_v=blanks,
        v2_s=blanks,
        n_zc=blanks,
        f_d_hz=blanks,
        tau_d_s=blanks,
        zeta=blanks,
        residual_fraction=blanks,
        evaluated_event_count=0,
        omitted_event_count=0,
    )
