"""F15 признаки на общей сетке 20 мс и каноническом остатке F10."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from lnt.characterization.event_models import TaggedEvent, TaggedExclusion, TaggedGap
from lnt.characterization.f15_bands import band_window_rms_v, checked_f15_bands
from lnt.characterization.f15_result import (
    FEATURE_UNAVAILABLE,
    INSUFFICIENT_WINDOWS,
    F15Settings,
)
from lnt.characterization.phase_stats import phase_residual_impl
from lnt.characterization.records import Status
from lnt.characterization.sync_grid import (
    complete_window_count,
    nominal_window_samples,
    window_start_sample,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.f10_result import F10Result
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans


@dataclass(frozen=True, slots=True, kw_only=True)
class F15FeatureTable:
    """Квалифицированные семь признаков и исходные индексы полных окон."""

    features: np.ndarray
    window_indices: np.ndarray
    complete_window_count: int
    reason_code: str | None


def extract_f15_features(  # noqa: PLR0913, PLR0917 - все объявленные входы F15
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    f10: F10Result,
    inventory: RootEvents,
    bands: tuple[ResolvedBand, ...],
    *,
    sample_rate_hz: float,
    band_filter_order: int,
    settings: F15Settings,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> F15FeatureTable:
    """Собрать семь признаков на общих непересекающихся окнах записи."""
    sample_count = int(np.asarray(samples).size)
    rate = float(sample_rate_hz)
    if not math.isfinite(rate) or rate <= 0.0:
        raise ValueError("F15 sample rate must be finite and positive")
    if phase.sample_count != sample_count or phase.sample_rate_hz != rate:
        raise ValueError("F15 phase grid does not match the measured record")
    if inventory.sample_count != sample_count or inventory.sample_rate_hz != rate:
        raise ValueError("F15 event inventory does not match the measured record")
    if f10.sample_count != sample_count:
        raise ValueError("F15 F10 result does not match the measured record")
    n_nominal = nominal_window_samples(settings.window_s, rate)
    total_windows = complete_window_count(sample_count, n_nominal)
    reason = _upstream_reason(phase, means, f10, inventory)
    if reason is not None:
        return _empty_table(total_windows, reason)
    band_reason = checked_f15_bands(bands, band_filter_order)
    if band_reason is not None:
        return _empty_table(total_windows, band_reason)
    if total_windows < settings.minimum_windows:
        return _empty_table(total_windows, INSUFFICIENT_WINDOWS)
    selected = even_floor_indices(total_windows, settings.maximum_labels)
    starts = np.asarray(
        [window_start_sample(int(index), n_nominal) for index in selected], dtype=np.int64
    )
    stops = starts + n_nominal
    features = np.full((selected.size, 7), np.nan, dtype=np.float64)
    valid = np.ones(selected.size, dtype=np.bool_)
    _raw_features(samples, starts, stops, features, valid)
    _occupancy_features(
        samples,
        phase,
        means,
        f10,
        starts,
        stops,
        features,
        valid,
        resources=resources,
        checkpoint=checkpoint,
    )
    _event_features(inventory, features, n_nominal, selected, checkpoint=checkpoint)
    for index, band in enumerate(bands):
        values = band_window_rms_v(
            samples,
            band,
            selected,
            n_nominal,
            sample_rate_hz=rate,
            filter_order=band_filter_order,
            resources=resources,
            checkpoint=checkpoint,
        )
        features[:, index + 2] = values
        valid &= np.isfinite(values)
    valid &= np.all(np.isfinite(features), axis=1)
    qualified = np.flatnonzero(valid)
    return F15FeatureTable(
        features=features[qualified].copy(),
        window_indices=selected[qualified].copy(),
        complete_window_count=total_windows,
        reason_code=(FEATURE_UNAVAILABLE if qualified.size < settings.minimum_windows else None),
    )


def even_floor_indices(total_windows: int, maximum_labels: int) -> np.ndarray:
    """Выбрать ``floor(i * W / limit)`` либо каждое окно при меньшей записи."""
    total = int(total_windows)
    limit = int(maximum_labels)
    if total < 0 or limit <= 0:
        raise ValueError("F15 window counts must be nonnegative and limit positive")
    if total <= limit:
        return np.arange(total, dtype=np.int64)
    return np.floor(np.arange(limit, dtype=np.float64) * total / limit).astype(np.int64)


def f10_occupancy_5mad(  # noqa: PLR0913, PLR0917 - явный срез остатка F10
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    f10: F10Result,
    start_sample: int,
    stop_sample: int,
    *,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None = None,
) -> float | None:
    """Доля квалифицированных отсчётов с ``abs(residual) >= 5 * F10.scale``."""
    if f10.status is Status.UNAVAILABLE or f10.scale is None:
        raise ValueError("F15 requires the available F10 scale")
    if not math.isfinite(f10.scale) or f10.scale <= 0.0:
        raise ValueError("F15 requires a finite positive F10 scale")
    residual, valid = phase_residual_impl(
        samples, phase, means, start_sample, stop_sample, resources=resources
    )
    qualified = int(np.count_nonzero(valid))
    if qualified == 0:
        return None
    if checkpoint is not None:
        checkpoint()
    above = valid & (np.abs(residual) >= 5.0 * f10.scale)
    return float(np.count_nonzero(above)) / qualified


def _upstream_reason(
    phase: PhaseCycles, means: PhaseMeans, f10: F10Result, inventory: RootEvents
) -> str | None:
    """Проверить готовые корни без пересчёта F10 или детектора событий."""
    if phase.status is Status.UNAVAILABLE or means.status is Status.UNAVAILABLE:
        return FEATURE_UNAVAILABLE
    if inventory.status is Status.UNAVAILABLE:
        return FEATURE_UNAVAILABLE
    if f10.status is Status.UNAVAILABLE or f10.scale is None:
        return FEATURE_UNAVAILABLE
    if not math.isfinite(f10.scale) or f10.scale <= 0.0:
        return FEATURE_UNAVAILABLE
    return None


def _raw_features(
    samples: np.ndarray,
    starts: np.ndarray,
    stops: np.ndarray,
    features: np.ndarray,
    valid: np.ndarray,
) -> None:
    """RMS и crest каждого окна из измеренного напряжения."""
    for row, (start, stop) in enumerate(zip(starts, stops, strict=True)):
        values = np.asarray(samples[int(start) : int(stop)], dtype=np.float64)
        if values.size != int(stop - start) or not np.all(np.isfinite(values)):
            valid[row] = False
            continue
        rms = float(np.sqrt(np.mean(values**2)))
        if rms <= 0.0:
            valid[row] = False
            continue
        features[row, 0] = rms
        features[row, 1] = float(np.max(np.abs(values))) / rms


def _occupancy_features(  # noqa: PLR0913, PLR0917 - все входы канонического остатка
    samples: np.ndarray,
    phase: PhaseCycles,
    means: PhaseMeans,
    f10: F10Result,
    starts: np.ndarray,
    stops: np.ndarray,
    features: np.ndarray,
    valid: np.ndarray,
    *,
    resources: ResourceLimits,
    checkpoint: Callable[[], None] | None,
) -> None:
    """Заполнить occupancy из того же phase_residual_impl, что использует F10."""
    for row, (start, stop) in enumerate(zip(starts, stops, strict=True)):
        occupancy = f10_occupancy_5mad(
            samples,
            phase,
            means,
            f10,
            int(start),
            int(stop),
            resources=resources,
            checkpoint=checkpoint,
        )
        if occupancy is None:
            valid[row] = False
        else:
            features[row, 6] = occupancy


def _event_features(
    inventory: RootEvents,
    features: np.ndarray,
    n_nominal: int,
    selected: np.ndarray,
    *,
    checkpoint: Callable[[], None] | None,
) -> None:
    """Посчитать полный replay-инвентарь по окну, содержащему peak события."""
    counts = np.zeros(features.shape[0], dtype=np.int64)
    for item in inventory.replay(checkpoint):
        match item:
            case TaggedEvent():
                window = int(item.event.peak_sample) // n_nominal
            case TaggedGap() | TaggedExclusion():
                continue
        position = int(np.searchsorted(selected, window))
        if position < selected.size and int(selected[position]) == window:
            counts[position] += 1
    features[:, 5] = counts


def _empty_table(complete_window_count: int, reason_code: str) -> F15FeatureTable:
    """Явная пустая область при отказе, без нулевых измерений."""
    return F15FeatureTable(
        features=np.empty((0, 7), dtype=np.float64),
        window_indices=np.empty(0, dtype=np.int64),
        complete_window_count=complete_window_count,
        reason_code=reason_code,
    )
