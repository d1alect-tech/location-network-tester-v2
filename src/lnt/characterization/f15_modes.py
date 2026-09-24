"""F15: оркестрация детерминированного PAM по семи признакам окон."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from lnt.characterization.f15_features import extract_f15_features
from lnt.characterization.f15_pam import (
    f15_stability_scores,
    pam_build_indices,
    pam_swap_indices,
)
from lnt.characterization.f15_result import (
    EMPTY_CLUSTER,
    FEATURE_NAMES,
    FEATURE_SCALE_ZERO,
    FEATURE_UNAVAILABLE,
    INSUFFICIENT_WINDOWS,
    LABEL_LIMIT,
    STABILITY_BLOCK_TOO_SHORT,
    F15Result,
    F15Settings,
)
from lnt.characterization.records import Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.analysis_store.characterization_settings import ResourceLimits
    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.f10_result import F10Result
    from lnt.characterization.phase_model import PhaseCycles, PhaseMeans

_FEATURE_NDIM: Final = 2
_FEATURE_COUNT: Final = 7


def compute_f15_modes(  # noqa: PLR0913, PLR0917 - полный объявленный вход engine
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
) -> F15Result:
    """Извлечь объявленные признаки и вернуть канонический F15Result."""
    table = extract_f15_features(
        samples,
        phase,
        means,
        f10,
        inventory,
        bands,
        sample_rate_hz=sample_rate_hz,
        band_filter_order=band_filter_order,
        settings=settings,
        resources=resources,
        checkpoint=checkpoint,
    )
    if table.reason_code == INSUFFICIENT_WINDOWS:
        return _unavailable((INSUFFICIENT_WINDOWS,), settings.window_s, table.complete_window_count)
    if table.reason_code is not None:
        return _unavailable((FEATURE_UNAVAILABLE,), settings.window_s, table.complete_window_count)
    return fit_f15_pam(
        table.features,
        table.window_indices,
        settings=settings,
        source_window_count=table.complete_window_count,
    )


def fit_f15_pam(  # noqa: C901 - объявленные гейты и канонический порядок
    features: np.ndarray,
    window_indices: np.ndarray,
    *,
    settings: F15Settings,
    source_window_count: int | None = None,
) -> F15Result:
    """Стандартизировать окна и обучить детерминированный PAM с фиксированным k."""
    values = np.asarray(features, dtype=np.float64)
    indices = np.asarray(window_indices, dtype=np.int64)
    if values.ndim != _FEATURE_NDIM or values.shape[1] != _FEATURE_COUNT:
        raise ValueError("F15 features must have shape (windows, 7)")
    if indices.shape != (values.shape[0],):
        raise ValueError("F15 window indices must match the feature rows")
    if not np.all(np.isfinite(values)):
        raise ValueError("F15 features must be finite")
    if indices.size > 1 and bool(np.any(np.diff(indices) <= 0)):
        raise ValueError("F15 window indices must be strictly increasing")
    source_count = values.shape[0] if source_window_count is None else int(source_window_count)
    if source_count < values.shape[0] or values.shape[0] > settings.maximum_labels:
        raise ValueError("F15 source count and bounded feature rows are inconsistent")
    if values.shape[0] < settings.minimum_windows:
        return _unavailable((INSUFFICIENT_WINDOWS,), settings.window_s, source_count)
    if np.unique(values, axis=0).shape[0] < settings.cluster_count:
        return _unavailable((EMPTY_CLUSTER,), settings.window_s, source_count)
    centres = np.median(values, axis=0)
    scales = np.median(np.abs(values - centres), axis=0)
    if bool(np.any(scales == 0.0)):
        return _unavailable((FEATURE_SCALE_ZERO,), settings.window_s, source_count)
    standardized = (values - centres) / scales
    initial = pam_build_indices(standardized, cluster_count=settings.cluster_count)
    medoids, swap_passes = pam_swap_indices(
        standardized,
        initial,
        maximum_passes=settings.maximum_swap_passes,
    )
    order = sorted(
        range(settings.cluster_count),
        key=lambda cluster: (
            float(values[medoids[cluster], 0]),
            int(indices[medoids[cluster]]),
        ),
    )
    canonical = np.empty(settings.cluster_count, dtype=np.int64)
    for label, cluster in enumerate(order):
        canonical[cluster] = label
    assignments = _assign(standardized, np.asarray(medoids, dtype=np.int64))
    labels = canonical[assignments]
    medoid_rows = np.asarray([medoids[cluster] for cluster in order], dtype=np.int64)
    dwell_labels, dwell_durations = _dwell(labels, settings.window_s)
    transition_counts, transition_probabilities = _transitions(labels, settings.cluster_count)
    short_block = values.shape[0] < settings.stability_blocks * settings.cluster_count
    stability = np.empty(0, dtype=np.float64)
    if not short_block:
        scores = f15_stability_scores(
            standardized,
            standardized[medoid_rows],
            block_count=settings.stability_blocks,
            maximum_passes=settings.maximum_swap_passes,
        )
        if scores is None:
            short_block = True
        else:
            stability = scores
    reasons = tuple(
        sorted(
            code
            for code, hit in (
                (LABEL_LIMIT, source_count > settings.maximum_labels),
                (STABILITY_BLOCK_TOO_SHORT, short_block),
            )
            if hit
        )
    )
    return F15Result(
        status=Status.PARTIAL if reasons else Status.AVAILABLE,
        reason_codes=reasons,
        window_s=settings.window_s,
        feature_names=FEATURE_NAMES,
        feature_medians=centres.copy(),
        feature_mads=scales.copy(),
        standardized_features=standardized.copy(),
        window_indices=indices.copy(),
        medoid_indices=indices[medoid_rows].copy(),
        medoid_features=values[medoid_rows].copy(),
        medoid_rms_v=values[medoid_rows, 0].copy(),
        labels=labels,
        dwell_labels=dwell_labels,
        dwell_durations_s=dwell_durations,
        transition_counts=transition_counts,
        transition_probabilities=transition_probabilities,
        stability_ari=stability,
        swap_passes=swap_passes,
        complete_window_count=source_count,
        qualified_window_count=values.shape[0],
        unretained_window_count=source_count - values.shape[0],
    )


def _dwell(labels: np.ndarray, window_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Непрерывные серии сохранённых меток в объявленных единицах окна."""
    starts = np.concatenate((np.asarray([0]), np.flatnonzero(np.diff(labels)) + 1), dtype=np.int64)
    stops = np.concatenate((starts[1:], np.asarray([labels.size])), dtype=np.int64)
    return labels[starts].copy(), (stops - starts).astype(np.float64) * float(window_s)


def _transitions(labels: np.ndarray, cluster_count: int) -> tuple[np.ndarray, np.ndarray]:
    """Точные счётчики соседних меток и нормированные по строкам вероятности."""
    counts = np.zeros((cluster_count, cluster_count), dtype=np.int64)
    if labels.size > 1:
        np.add.at(counts, (labels[:-1], labels[1:]), 1)
    totals = np.sum(counts, axis=1, keepdims=True)
    probabilities = counts / np.maximum(totals, 1)
    return counts, probabilities


def _assign(standardized: np.ndarray, medoids: np.ndarray) -> np.ndarray:
    """Назначить строку ближайшему медиоиду; ``argmin`` выбирает первый слот при ничьей."""
    delta = standardized[:, None, :] - standardized[medoids][None, :, :]
    return np.argmin(np.sum(delta * delta, axis=2), axis=1).astype(np.int64)


def _unavailable(
    reason_codes: tuple[str, ...], window_s: float, complete_window_count: int
) -> F15Result:
    """Собрать честную пустую форму с объявленным кодом отказа."""
    empty_float = np.empty(0, dtype=np.float64)
    empty_int = np.empty(0, dtype=np.int64)
    return F15Result(
        status=Status.UNAVAILABLE,
        reason_codes=reason_codes,
        window_s=window_s,
        feature_names=FEATURE_NAMES,
        feature_medians=empty_float,
        feature_mads=empty_float,
        standardized_features=np.empty((0, 7), dtype=np.float64),
        window_indices=empty_int,
        medoid_indices=empty_int,
        medoid_features=np.empty((0, 7), dtype=np.float64),
        medoid_rms_v=empty_float,
        labels=empty_int,
        dwell_labels=empty_int,
        dwell_durations_s=empty_float,
        transition_counts=np.empty((0, 0), dtype=np.int64),
        transition_probabilities=np.empty((0, 0), dtype=np.float64),
        stability_ari=empty_float,
        swap_passes=0,
        complete_window_count=complete_window_count,
        qualified_window_count=0,
        unretained_window_count=complete_window_count,
    )
