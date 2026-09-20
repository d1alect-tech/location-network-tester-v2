"""F02 template-gain-delay least-squares fit of every delimited root event."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from lnt.characterization.records import Status

if TYPE_CHECKING:
    from lnt.characterization.event_models import RootEvent

METHOD: Final = "template_gain_delay_least_squares"
TEMPLATE_FAMILY_ID: Final = "f01_phase_cycle"
TEMPLATE_FIELD: Final = "x_template_v"
COARSE_DELAY_METHOD: Final = "fft_cross_correlation"
DELAY_REFINEMENT: Final = "parabolic"
SUBSAMPLE_DIVISOR: Final = 64
MINIMUM_EVENT_SNR_DB: Final = 10.0
RESIDUAL_FRACTION_MAX: Final = 0.25
MAXIMUM_EVENTS: Final = 4096

_EPS: Final = 1e-30

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]

__all__ = [
    "COARSE_DELAY_METHOD",
    "DELAY_REFINEMENT",
    "MAXIMUM_EVENTS",
    "METHOD",
    "MINIMUM_EVENT_SNR_DB",
    "RESIDUAL_FRACTION_MAX",
    "SUBSAMPLE_DIVISOR",
    "TEMPLATE_FAMILY_ID",
    "TEMPLATE_FIELD",
    "F02Result",
    "compute_f02_amplitude_time_shape",
    "resample_cycle_template",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class F02Result:
    """Bounded F02 outcome over the declared event inventory."""

    status: Status
    reason_codes: tuple[str, ...]
    amplitudes: tuple[float | None, ...]
    delays_s: tuple[float | None, ...]
    residual_fractions: tuple[float | None, ...]
    residual_energies_v2_s: tuple[float | None, ...]
    evaluated_event_count: int
    omitted_event_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _Fit:
    """One least-squares fit at a single point of the sub-sample lattice."""

    cost: float
    tau_samples: float
    gain: float
    residual_v2: float


@dataclass(frozen=True, slots=True, kw_only=True)
class _Limits:
    """The declared recipe gates applied to every event fit."""

    subsample_divisor: int
    minimum_event_snr_db: float
    residual_fraction_max: float
    maximum_events: int


def _snr_db(snr_ratio: float) -> float:
    """Event SNR in dB; a non-positive ratio carries no signal at all."""
    ratio = float(snr_ratio)
    return 20.0 * float(np.log10(ratio)) if ratio > 0.0 else -float("inf")


def resample_cycle_template(
    template: FloatInput,
    *,
    f1_hz: float,
    sample_rate_hz: float,
) -> Float64Array:
    """Map the F01 unit-cycle template onto one f1 cycle of the record grid.

    ``x_template_v`` is one cycle on a 1000-point theta grid, independent of fs,
    while an event span lives on the record grid where one cycle holds
    ``fs / f1`` samples. Linear interpolation, the F01-locked rule.
    """
    source = np.asarray(template, dtype=np.float64)
    cycle_samples = round(float(sample_rate_hz) / float(f1_hz))
    # The template is periodic with endpoint=False, so one cycle spans exactly
    # `size` points; the wrap-around segment needs the first sample repeated.
    size = int(source.size)
    grid = np.arange(size + 1, dtype=np.float64)
    values = np.concatenate((source, source[:1]))
    target = np.arange(cycle_samples, dtype=np.float64) * (float(size) / float(cycle_samples))
    return np.interp(target, grid, values).astype(np.float64)


def _baseline_median(record: Float64Array, start: int, end: int, length: int) -> float | None:
    """Median of both event-length windows flanking the span; None if either is absent."""
    if start - length < 0 or end + 1 + length > int(record.size):
        return None
    before = record[start - length : start]
    after = record[end + 1 : end + 1 + length]
    return float(np.median(np.concatenate((before, after))))


def _span(
    record: Float64Array, event: RootEvent, limits: _Limits
) -> tuple[Float64Array | None, str | None]:
    """Baseline-removed event span, or the declared reason it cannot be fitted."""
    start = int(event.start_sample)
    end = int(event.end_sample)
    if start < 0 or end >= int(record.size):
        return None, "event_truncated"
    if _snr_db(event.snr_ratio) < limits.minimum_event_snr_db:
        return None, "below_snr"
    baseline = _baseline_median(record, start, end, end - start + 1)
    if baseline is None:
        return None, "baseline_unavailable"
    y = np.asarray(record[start : end + 1], dtype=np.float64) - baseline
    if float(np.dot(y, y)) < _EPS:
        return None, "below_snr"
    return y, None


def _shifted(template: Float64Array, tau: float, size: int) -> Float64Array:
    """Template delayed by tau samples, linearly interpolated, zero outside its support."""
    source = np.arange(size, dtype=np.float64) - float(tau)
    grid = np.arange(int(template.size), dtype=np.float64)
    return np.interp(source, grid, template, left=0.0, right=0.0)


def _cost(y: Float64Array, v_tau: Float64Array) -> tuple[float, float, float]:
    """J(tau), the closed-form gain, and ||y - a v_tau||^2 measured directly."""
    norm = float(np.dot(v_tau, v_tau))
    y_energy = float(np.dot(y, y))
    if norm < _EPS:
        return float("inf"), 0.0, y_energy
    dot = float(np.dot(y, v_tau))
    gain = dot / norm
    residual = y - gain * v_tau
    return y_energy - dot * dot / norm, gain, float(np.dot(residual, residual))


def _lattice(y: Float64Array, template: Float64Array, coarse: float, limits: _Limits) -> _Fit:
    """Best fit on the declared sub-sample lattice within one sample of the coarse lag."""
    size = int(y.size)
    step = 1.0 / float(limits.subsample_divisor)
    best = _Fit(cost=float("inf"), tau_samples=float(coarse), gain=0.0, residual_v2=float("inf"))
    for offset in range(-limits.subsample_divisor, limits.subsample_divisor + 1):
        cost, gain, residual = _cost(y, _shifted(template, coarse + offset * step, size))
        if cost < best.cost:
            best = _Fit(
                cost=cost,
                tau_samples=coarse + offset * step,
                gain=gain,
                residual_v2=residual,
            )
    return best


def _refine(y: Float64Array, template: Float64Array, fit: _Fit, limits: _Limits) -> _Fit:
    """Parabolic vertex, kept only when it lowers J: an exact fit stays on the lattice."""
    step = 1.0 / float(limits.subsample_divisor)
    size = int(y.size)
    minus = _cost(y, _shifted(template, fit.tau_samples - step, size))[0]
    plus = _cost(y, _shifted(template, fit.tau_samples + step, size))[0]
    denominator = minus - 2.0 * fit.cost + plus
    if not np.isfinite(denominator) or abs(denominator) < _EPS:
        return fit
    delta = 0.5 * (minus - plus) / denominator
    if not -1.0 <= delta <= 1.0:
        return fit
    tau = fit.tau_samples + delta * step
    cost, gain, residual = _cost(y, _shifted(template, tau, size))
    if cost >= fit.cost:
        return fit
    return _Fit(cost=cost, tau_samples=tau, gain=gain, residual_v2=residual)


def _coarse_lag(y: Float64Array, template: Float64Array) -> float:
    """Integer FFT cross-correlation lag under the convention y[i] ~ v[i - lag]."""
    correlation = signal.correlate(y, template, mode="full", method="fft")
    lags = signal.correlation_lags(int(y.size), int(template.size), mode="full")
    return float(lags[int(np.argmax(correlation))])


def _fit_event(
    record: Float64Array,
    template: Float64Array,
    event: RootEvent,
    sample_rate_hz: float,
    limits: _Limits,
) -> tuple[tuple[float, float, float, float] | None, str | None]:
    """(tau_samples, gain, residual fraction, residual energy V^2 s) or a rejection code."""
    y, code = _span(record, event, limits)
    if y is None:
        return None, code
    fit = _refine(y, template, _lattice(y, template, _coarse_lag(y, template), limits), limits)
    y_norm = float(np.sqrt(float(np.dot(y, y))))
    rho = float(np.sqrt(fit.residual_v2)) / y_norm
    return (fit.tau_samples, fit.gain, rho, fit.residual_v2 / sample_rate_hz), None


def _overlaps(events: tuple[RootEvent, ...]) -> bool:
    """Detect two delimited spans colliding, which makes (a, tau) non-unique."""
    ordered = sorted(events, key=lambda item: item.start_sample)
    return any(
        current.start_sample <= previous.end_sample for previous, current in pairwise(ordered)
    )


def _unavailable(codes: tuple[str, ...], total: int, evaluated: int, omitted: int) -> F02Result:
    """Unavailable result with no fabricated amplitude or delay."""
    blanks: tuple[None, ...] = (None,) * total
    return F02Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        amplitudes=blanks,
        delays_s=blanks,
        residual_fractions=blanks,
        residual_energies_v2_s=blanks,
        evaluated_event_count=evaluated,
        omitted_event_count=omitted,
    )


def compute_f02_amplitude_time_shape(  # noqa: PLR0913 - declared recipe gates are explicit knobs
    record: FloatInput,
    template: FloatInput | None,
    events: tuple[RootEvent, ...],
    *,
    sample_rate_hz: float,
    subsample_divisor: int = SUBSAMPLE_DIVISOR,
    minimum_event_snr_db: float = MINIMUM_EVENT_SNR_DB,
    residual_fraction_max: float = RESIDUAL_FRACTION_MAX,
    maximum_events: int = MAXIMUM_EVENTS,
) -> F02Result:
    """Fit the F01 cycle template gain and delay to every delimited root event."""
    total = len(events)
    limits = _Limits(
        subsample_divisor=int(subsample_divisor),
        minimum_event_snr_db=float(minimum_event_snr_db),
        residual_fraction_max=float(residual_fraction_max),
        maximum_events=int(maximum_events),
    )
    if template is None or int(np.asarray(template).size) == 0:
        return _unavailable(("template_unavailable",), total, 0, 0)
    if not events:
        # No delimited event means no pair of flanking event-length intervals, so
        # the baseline the method requires does not exist for any event to be
        # fitted against. Declared code, never a fabricated (a, tau) pair.
        return _unavailable(("baseline_unavailable",), total, 0, 0)
    if _overlaps(events):
        return _unavailable(("overlapping_events",), total, 0, 0)
    samples = np.asarray(record, dtype=np.float64)
    shape = np.asarray(template, dtype=np.float64)
    fs = float(sample_rate_hz)
    kept = events[: limits.maximum_events]
    omitted = total - len(kept)
    outcomes = [_fit_event(samples, shape, event, fs, limits) for event in kept]
    codes: set[str] = set()
    accepted: list[tuple[float, float, float, float] | None] = []
    for fit, code in outcomes:
        # rho above the declared ceiling means the template explains too little of the
        # span, so the fit's own signal-to-residual ratio is below threshold: the event
        # is dropped under below_snr instead of reported as a plausible (a, tau) pair.
        if fit is None or fit[2] > limits.residual_fraction_max:
            codes.add("below_snr" if code is None else code)
            accepted.append(None)
            continue
        accepted.append(fit)
    if not any(item is not None for item in accepted):
        return _unavailable(tuple(sorted(codes)) or ("below_snr",), total, len(kept), omitted)
    tail: tuple[None, ...] = (None,) * omitted
    return F02Result(
        status=Status.AVAILABLE if not codes else Status.PARTIAL,
        reason_codes=tuple(sorted(codes)),
        amplitudes=(*(i[1] if i is not None else None for i in accepted), *tail),
        delays_s=(*(i[0] / fs if i is not None else None for i in accepted), *tail),
        residual_fractions=(*(i[2] if i is not None else None for i in accepted), *tail),
        residual_energies_v2_s=(*(i[3] if i is not None else None for i in accepted), *tail),
        evaluated_event_count=len(kept),
        omitted_event_count=omitted,
    )
