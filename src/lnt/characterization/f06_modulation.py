"""F06 butterworth_hilbert_analytic_trajectory over the declared carrier band."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.bands import ResolvedBand
from lnt.characterization.envelopes import stream_band_analytic
from lnt.characterization.f06_gates import BAND_INVALID, gate_reasons, spectral_gates
from lnt.characterization.f06_stream import Trajectory
from lnt.characterization.records import Status
from lnt.features.bands import BandDefinition, EstimandDirection, FrequencyUnit

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

    from lnt.analysis_store.characterization_settings import ResourceLimits

type FloatInput = NDArray[np.float32] | NDArray[np.float64]
type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

METHOD: Final = "butterworth_hilbert_analytic_trajectory"

__all__ = ["METHOD", "F06Result", "compute_f06_modulation_trajectories"]


@dataclass(frozen=True, slots=True, kw_only=True)
class F06Result:
    """Ограниченный результат F06 по объявленной несущей полосе."""

    status: Status
    reason_codes: tuple[str, ...]
    stored_indices: Int64Array
    amplitudes_v: Float64Array
    phases_rad: Float64Array
    frequencies_hz: Float64Array
    start_sample: int
    stop_sample: int
    observation_count: int
    missing_count: int
    stored_count: int
    snr_db: float | None
    components: int | None


def compute_f06_modulation_trajectories(  # noqa: PLR0913 - объявленные гейты рецепта
    samples: FloatInput,
    *,
    sample_rate_hz: float,
    band_low_hz: float,
    band_high_hz: float,
    nyquist_fraction_max: float,
    filter_order: int,
    minimum_snr_db: float,
    maximum_components_in_band: int,
    phase_increment_max_rad: float,
    envelope_zero_fraction_of_median: float,
    maximum_stored_samples: int,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F06Result:
    """Проследить огибающую, развёрнутую фазу и мгновенную частоту полосового сигнала.

    Проход однократный и ограниченный: чанки берёт общее потоковое преобразование,
    спектральные гейты считаются по сегментам фиксированной длины, а хранимая
    траектория выбирается объявленным правилом ``even_floor_index`` (кандидаты
    ``floor(k * N / M)`` по записи). Позиции известны заранее, поэтому спан не нужно
    знать до конца прохода. Траектория описывает ПЕРВЫЙ непрерывный поддержанный спан:
    непрерывность развёрнутой фазы и разности частот за разрывом не определены, а
    остаток записи честно уходит в ``missing_count``.
    """
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive and finite")
    order = int(filter_order)
    if order <= 0:
        raise ValueError("filter order must be positive")
    limit = int(maximum_stored_samples)
    if limit <= 0:
        raise ValueError("maximum_stored_samples must be positive")
    if band_high_hz <= band_low_hz:
        raise ValueError("declared band must be ordered")
    record = int(np.asarray(samples).size)
    band = _band(float(band_low_hz), float(band_high_hz), nyquist_fraction_max * sample_rate_hz)
    if band.effective is None or record == 0:
        return _unavailable(record, (BAND_INVALID,))
    trajectory = Trajectory(sample_rate_hz, limit, record, float(phase_increment_max_rad))
    for chunk in stream_band_analytic(
        samples,
        band,
        sample_rate_hz=sample_rate_hz,
        filter_order=order,
        resources=resources,
        checkpoint=checkpoint,
        detrend=True,
    ):
        trajectory.feed(chunk)
    trajectory.flush_pending()
    if trajectory.span_start is None or trajectory.count == 0:
        # Ни одного поддержанного отсчёта с траекторией: объявленного кода
        # «нет поддержки» в словаре F06 нет, и выдумывать его не будем.
        return _unavailable(record, (BAND_INVALID,))
    effective = band.effective
    snr_db, components = spectral_gates(
        trajectory, float(effective.low_hz), float(effective.high_hz), float(minimum_snr_db)
    )
    reasons = gate_reasons(
        trajectory,
        snr_db=snr_db,
        components=components,
        minimum_snr_db=float(minimum_snr_db),
        maximum_components_in_band=int(maximum_components_in_band),
        envelope_zero_fraction_of_median=float(envelope_zero_fraction_of_median),
    )
    if reasons:
        refused = _unavailable(record, reasons)
        return replace(refused, snr_db=snr_db, components=components)
    span = trajectory.span_stop - trajectory.span_start
    return F06Result(
        status=Status.AVAILABLE,
        reason_codes=(),
        stored_indices=trajectory.stored[: trajectory.count].copy(),
        amplitudes_v=trajectory.amplitudes[: trajectory.count].copy(),
        phases_rad=trajectory.phases[: trajectory.count].copy(),
        frequencies_hz=trajectory.frequencies[: trajectory.count].copy(),
        start_sample=trajectory.span_start,
        stop_sample=trajectory.span_stop,
        observation_count=span,
        missing_count=record - span,
        stored_count=trajectory.count,
        snr_db=snr_db,
        components=components,
    )


def _band(low_hz: float, high_hz: float, maximum_hz: float) -> ResolvedBand:
    """Объявленная полоса F06, зажатая пределом Найквиста (полосы F13 не переиспользуем)."""
    requested = BandDefinition(
        name="f06_carrier",
        low=low_hz,
        high=high_hz,
        unit=FrequencyUnit.HZ,
        direction=EstimandDirection.DESCRIPTIVE,
    )
    effective_high = min(high_hz, maximum_hz)
    if effective_high <= low_hz:
        return ResolvedBand(requested=requested, effective=None, reason_code=BAND_INVALID)
    if effective_high >= high_hz:
        return ResolvedBand(requested=requested, effective=requested, reason_code=None)
    effective = BandDefinition(
        name="f06_carrier",
        low=low_hz,
        high=effective_high,
        unit=FrequencyUnit.HZ,
        direction=EstimandDirection.DESCRIPTIVE,
    )
    return ResolvedBand(requested=requested, effective=effective, reason_code=None)


def _unavailable(record: int, codes: tuple[str, ...]) -> F06Result:
    """Отказ без выдуманных значений и без траектории."""
    empty = np.empty(0, dtype=np.float64)
    return F06Result(
        status=Status.UNAVAILABLE,
        reason_codes=codes,
        stored_indices=np.empty(0, dtype=np.int64),
        amplitudes_v=empty,
        phases_rad=empty.copy(),
        frequencies_hz=empty.copy(),
        start_sample=0,
        stop_sample=0,
        observation_count=0,
        missing_count=record,
        stored_count=0,
        snr_db=None,
        components=None,
    )
