"""Морфология одного объявленного события F08: прямые меры и фит затухания."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray
from scipy import optimize, signal

from lnt.characterization.f08_result import (
    BELOW_SNR,
    CLIPPED,
    MULTIMODE,
    SINGLE_EXPONENTIAL_POOR,
    TOO_FEW_SAMPLES,
)
from lnt.characterization.f08_shape import (
    Gates,
    gate_band,
    guard_span_bounds,
    initial_damped_sinusoid_seed,
    mode_count,
    rise_time,
    snr_db,
    zero_crossings,
)

if TYPE_CHECKING:
    from lnt.characterization.event_models import RootEvent

type Float64Array = NDArray[np.float64]

_MINIMUM_SPAN_SAMPLES: Final = 2

__all__ = ["EventOutcome", "event_outcome"]


@dataclass(frozen=True, slots=True, kw_only=True)
class EventOutcome:
    """Итог одного события: прямые величины, параметры фита и код отказа."""

    t_rise_s: float | None
    v_peak_v: float | None
    v2_s: float | None
    n_zc: int | None
    f_d_hz: float | None
    tau_d_s: float | None
    zeta: float | None
    residual_fraction: float | None
    code: str | None


def event_outcome(  # noqa: PLR0911 - гейты рецепта отказывают каждый своим кодом
    samples: Float64Array, event: RootEvent, gates: Gates
) -> EventOutcome:
    """Прямые величины и фит одного события, либо объявленный код отказа."""
    span = _guarded_span(samples, event)
    if span is None:
        return _refused()
    v_peak = float(np.max(np.abs(span)))
    if v_peak <= 0.0:
        return _refused()
    count = zero_crossings(span)
    rise = rise_time(span, gates.rate_hz, v_peak)
    energy = float(np.dot(span, span) / gates.rate_hz)

    def refuse(code: str) -> EventOutcome:
        """Отказ формы: прямые величины измерены, параметры фита пусты."""
        return EventOutcome(
            t_rise_s=rise,
            v_peak_v=v_peak,
            v2_s=energy,
            n_zc=count,
            f_d_hz=None,
            tau_d_s=None,
            zeta=None,
            residual_fraction=None,
            code=code,
        )

    if event.clipped is not False:
        return refuse(CLIPPED)
    if snr_db(event.snr_ratio) < gates.minimum_snr_db:
        return refuse(BELOW_SNR)
    if count < gates.minimum_zero_crossings:
        return refuse(TOO_FEW_SAMPLES)
    low_hz, high_hz = gate_band(gates)
    seed = initial_damped_sinusoid_seed(
        span,
        sample_rate_hz=gates.rate_hz,
        ringing_frequency_low_hz=low_hz,
        ringing_frequency_high_hz=high_hz,
        decay_time_minimum_samples=gates.tau_min_samples,
        decay_time_max_s=gates.tau_max_s,
    )
    if seed.f_d_hz is None or seed.tau_d_s is None:
        return refuse(SINGLE_EXPONENTIAL_POOR)
    fit = _bounded_fit(span, gates, v_peak, seed.f_d_hz, seed.tau_d_s)
    if fit is None:
        return refuse(SINGLE_EXPONENTIAL_POOR)
    rho, f_d, tau_d, zeta = fit
    if mode_count(span, gates.rate_hz, low_hz, high_hz) > 1:
        return refuse(MULTIMODE)
    return EventOutcome(
        t_rise_s=rise,
        v_peak_v=v_peak,
        v2_s=energy,
        n_zc=count,
        f_d_hz=f_d,
        tau_d_s=tau_d,
        zeta=zeta,
        residual_fraction=rho,
        code=None,
    )


def _guarded_span(samples: Float64Array, event: RootEvent) -> Float64Array | None:
    """Линейно детрендованный спан внутри записи, либо None без поддержки отсчётов."""
    start = int(event.start_sample)
    end = int(event.end_sample)
    size = int(samples.size)
    if start < 0 or end >= size or end - start + 1 < _MINIMUM_SPAN_SAMPLES:
        return None
    low, high = guard_span_bounds(start, end, size)
    window = samples[low:high]
    if window.size < _MINIMUM_SPAN_SAMPLES or not bool(np.all(np.isfinite(window))):
        return None
    return signal.detrend(window, type="linear")[start - low : end + 1 - low]


def _bounded_fit(
    span: Float64Array,
    gates: Gates,
    v_peak: float,
    f_seed: float,
    tau_seed: float,
) -> tuple[float, float, float, float] | None:
    """Ограниченный фит спеки:401-412, либо None при остатке выше объявленного порога."""
    grid = np.arange(int(span.size), dtype=np.float64) / gates.rate_hz
    ceiling = gates.amplitude_multiple * v_peak
    low = np.array([0.0, gates.tau_floor_s, gates.ringing_low_hz, gates.phase_low_rad, -ceiling])
    high = np.array([ceiling, gates.tau_max_s, gates.nyquist_hz, gates.phase_high_rad, ceiling])
    start = np.clip(np.array([0.5 * min(v_peak, ceiling), tau_seed, f_seed, 0.0, 0.0]), low, high)

    def residual(parameters: Float64Array) -> Float64Array:
        amplitude, tau_d, f_d, phase, offset = parameters
        model = amplitude * np.exp(-grid / tau_d) * np.sin(2.0 * np.pi * f_d * grid + phase)
        return model + offset - span

    solution = optimize.least_squares(
        residual,
        start,
        bounds=(low, high),
        max_nfev=gates.maximum_evaluations,
        # Настройка шкалы объявлена здесь: при единичной шкале фит уходит в ложную
        # моду на зашумлённом спане (замерено в evidence, решение F08-8).
        x_scale="jac",
    )
    norm = float(np.linalg.norm(span))
    rho = float(np.linalg.norm(residual(solution.x)) / norm) if norm > 0.0 else 1.0
    if not math.isfinite(rho) or rho > gates.residual_fraction_max:
        return None
    tau_d = float(solution.x[1])
    f_d = float(solution.x[2])
    if not (math.isfinite(tau_d) and math.isfinite(f_d)) or tau_d <= 0.0 or f_d <= 0.0:
        return None
    delta = 1.0 / (f_d * tau_d)
    return rho, f_d, tau_d, delta / math.sqrt(4.0 * math.pi**2 + delta**2)


def _refused() -> EventOutcome:
    """Спан без поддержки отсчётов: ни прямой величины, ни параметра фита."""
    return EventOutcome(
        t_rise_s=None,
        v_peak_v=None,
        v2_s=None,
        n_zc=None,
        f_d_hz=None,
        tau_d_s=None,
        zeta=None,
        residual_fraction=None,
        code=TOO_FEW_SAMPLES,
    )
