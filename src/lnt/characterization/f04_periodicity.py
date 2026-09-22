"""F04 overlapping_allan_deviation_and_cycle_autocorrelation поверх корней фазы и F06."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f04_allan import (
    autocorrelate_durations,
    overlapping_adev,
    phase_slip_cycles,
    valid_averaging_factors,
)
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from numpy.typing import NDArray

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.f06_modulation import F06Result
    from lnt.characterization.phase_model import PhaseCycles

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

METHOD: Final = "overlapping_allan_deviation_and_cycle_autocorrelation"

RECORD_TOO_SHORT: Final = "record_too_short_for_tau"
CARRIER_UNAVAILABLE: Final = "carrier_unavailable"
PHASE_UNWRAP_FAILED: Final = "phase_unwrap_failed"
NOT_ENOUGH_SAMPLES: Final = "not_enough_samples"
GRID_UNSTABLE: Final = "grid_unstable"
DECLARED_CODES: Final = (
    RECORD_TOO_SHORT,
    CARRIER_UNAVAILABLE,
    PHASE_UNWRAP_FAILED,
    NOT_ENOUGH_SAMPLES,
    GRID_UNSTABLE,
)

__all__ = ["METHOD", "F04Result", "compute_f04_multicycle_periodicity"]


@dataclass(frozen=True, slots=True, kw_only=True)
class F04Result:
    """Ограниченный результат F04: сетка tau, ADEV двух путей, АКФ и сводки."""

    status: Status
    reason_codes: tuple[str, ...]
    tau_s: Float64Array
    adev_mains: Float64Array | None
    adev_carrier: Float64Array | None
    acf_lag_cycles: Int64Array
    cycle_acf: Float64Array
    carrier_to_mains_ratio: float | None
    phase_slip_cycles: float | None
    sample_count: int
    observation_count: int
    missing_count: int
    stored_count: int
    start_s: float | None
    end_s: float | None


def compute_f04_multicycle_periodicity(  # noqa: PLR0913 - объявленные гейты рецепта
    samples: FloatInput,
    *,
    sample_rate_hz: float,
    phase: PhaseCycles,
    carrier: FloatInput,
    f06_result: F06Result,
    line_frequency_hz: float,
    averaging_factors: Sequence[int],
    maximum_averaging_fraction_of_record: float,
    minimum_cycles: int,
    carrier_minimum_snr_db: float,
    autocorrelation_lags_cycles: Sequence[int],
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F04Result:
    """Посчитать перекрывающуюся ADEV сети и несущей и АКФ длительностей циклов.

    Путь (b) «сеть»: границы циклов берёт из готового ``PhaseCycles`` (F04-2),
    ``f0`` — объявленный номинал манифеста, ``y`` по стандартам ``(f-f0)/f0``
    (F04-3). Путь (a) «несущая»: частота цикла — среднее частот F06 по хранимым
    отсчётам внутри цикла сети (F04-9); цикл без отсчётов — отказ без
    интерполяции (F04-10). ``samples`` и ``carrier`` — записи, к которым
    привязаны ``phase`` и ``f06_result``: интервал клиппится записью сети,
    хранимые индексы F06 проверяются записью несущей.
    """
    if checkpoint is not None:
        checkpoint()
    rate = float(sample_rate_hz)
    f0 = float(line_frequency_hz)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("sample rate must be positive and finite")
    if not math.isfinite(f0) or f0 <= 0:
        raise ValueError("line frequency must be positive and finite")
    # Объявленный бюджет не расходуется: работа O(N·L) по циклам и факторам
    # усреднения (спека `method-notes-families-1-9.md:239-240`), ограничивать нечего.
    _ = resources
    if phase.status is not Status.AVAILABLE:
        return _unavailable(phase, (GRID_UNSTABLE,))
    starts = np.asarray(phase.cycle_start_samples, dtype=np.float64)
    picked = np.asarray(phase.cycle_valid, dtype=np.bool_)
    good_starts = starts[picked]
    good_ends = np.asarray(phase.cycle_end_samples, dtype=np.float64)[picked]
    observation = int(good_starts.size)
    if observation < int(minimum_cycles):
        return _unavailable(phase, (NOT_ENOUGH_SAMPLES,))
    durations = (good_ends - good_starts) / rate
    mains_freqs = 1.0 / durations
    tau0 = 1.0 / f0
    kept, truncated = valid_averaging_factors(
        observation, averaging_factors, float(maximum_averaging_fraction_of_record)
    )
    if not kept:
        return _unavailable(phase, (RECORD_TOO_SHORT,))
    tau_s, adev_mains = overlapping_adev((mains_freqs - f0) / f0, kept, tau0)
    lags, acf = autocorrelate_durations(durations, autocorrelation_lags_cycles)
    record_s = int(np.asarray(samples).size) / rate
    adev_carrier, ratio, carrier_code = _carrier_path(
        f06_result,
        carrier,
        good_starts,
        good_ends,
        float(np.mean(mains_freqs)),
        kept,
        tau0,
        float(carrier_minimum_snr_db),
    )
    raw: list[str] = [RECORD_TOO_SHORT] if truncated else []
    if carrier_code is not None:
        raw.append(carrier_code)
    codes = tuple(code for code in DECLARED_CODES if code in raw)
    total = int(starts.size)
    return F04Result(
        status=Status.PARTIAL if codes else Status.AVAILABLE,
        reason_codes=codes,
        tau_s=tau_s,
        adev_mains=adev_mains,
        adev_carrier=adev_carrier,
        acf_lag_cycles=lags,
        cycle_acf=acf,
        carrier_to_mains_ratio=ratio,
        phase_slip_cycles=phase_slip_cycles(good_starts, rate, f0),
        sample_count=total,
        observation_count=observation,
        missing_count=total - observation,
        stored_count=observation,
        start_s=max(0.0, float(good_starts[0]) / rate),
        end_s=min(record_s, float(good_ends[-1]) / rate),
    )


def _carrier_path(  # noqa: PLR0913, PLR0917 - путь (a) читает все гейты несущей явно
    f06: F06Result,
    carrier: FloatInput,
    starts: Float64Array,
    ends: Float64Array,
    mains_mean_hz: float,
    factors: tuple[int, ...],
    tau0_s: float,
    minimum_snr_db: float,
) -> tuple[Float64Array | None, float | None, str | None]:
    """Путь (a): гейт SNR, средние частоты по циклам, ADEV на общей сетке tau."""
    snr = f06.snr_db
    if f06.status is not Status.AVAILABLE or snr is None or float(snr) < minimum_snr_db:
        return None, None, CARRIER_UNAVAILABLE
    per_cycle = _carrier_cycle_means(f06, carrier, starts, ends)
    if per_cycle is None:
        return None, None, PHASE_UNWRAP_FAILED
    mean_carrier = float(np.mean(per_cycle))
    if not math.isfinite(mean_carrier) or mean_carrier <= 0:
        return None, None, PHASE_UNWRAP_FAILED
    _, adev = overlapping_adev((per_cycle - mean_carrier) / mean_carrier, factors, tau0_s)
    return adev, mean_carrier / mains_mean_hz, None


def _carrier_cycle_means(
    f06: F06Result, carrier: FloatInput, starts: Float64Array, ends: Float64Array
) -> Float64Array | None:
    """Средняя частота несущей по хранимым отсчётам внутри каждого цикла сети."""
    indices = np.asarray(f06.stored_indices, dtype=np.int64)
    freqs = np.asarray(f06.frequencies_hz, dtype=np.float64)
    span = int(np.asarray(carrier).size)
    if indices.size == 0 or indices.size != freqs.size:
        return None
    usable = (indices >= 0) & (indices < span) & np.isfinite(freqs)
    out = np.empty(starts.size, dtype=np.float64)
    for pos in range(int(starts.size)):
        low = math.floor(float(starts[pos]))
        high = math.ceil(float(ends[pos]))
        selected = usable & (indices >= low) & (indices < high)
        if not bool(np.any(selected)):
            return None
        out[pos] = float(np.mean(freqs[selected]))
    return out if bool(np.all(np.isfinite(out))) else None


def _unavailable(phase: PhaseCycles, codes: tuple[str, ...]) -> F04Result:
    """Отказ без выдуманных значений: пустые сетки и None вместо интервалов."""
    total = int(np.asarray(phase.cycle_start_samples).size)
    observed = int(np.count_nonzero(np.asarray(phase.cycle_valid, dtype=np.bool_)))
    empty = np.empty(0, dtype=np.float64)
    return F04Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        tau_s=empty,
        adev_mains=None,
        adev_carrier=None,
        acf_lag_cycles=np.empty(0, dtype=np.int64),
        cycle_acf=empty.copy(),
        carrier_to_mains_ratio=None,
        phase_slip_cycles=None,
        sample_count=total,
        observation_count=observed,
        missing_count=total - observed,
        stored_count=observed,
        start_s=None,
        end_s=None,
    )
