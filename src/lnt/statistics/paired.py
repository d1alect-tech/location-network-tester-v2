"""Парные линейные оценки по одному агрегату независимой единицы."""

from __future__ import annotations

import math
from typing import Final

import numpy as np

from lnt.experiments import Protocol

from .models import (
    AnalysisContext,
    DescriptiveEffect,
    EffectInterval,
    EffectResult,
    InferentialEffect,
    PairedUnit,
    PairingError,
    ResultMetadata,
)

BOOTSTRAP_SAMPLES: Final = 10_000
MIN_INFERENCE_N: Final = 3


def metadata_for(
    context: AnalysisContext,
    *,
    n: int,
    estimator_name: str,
    interval_method: str,
) -> ResultMetadata:
    """Формирует обязательную provenance-маркировку результата."""
    return ResultMetadata(
        sampling_unit=context.protocol.sampling_unit,
        hierarchy=context.hierarchy,
        n=n,
        missing_count=context.missing_count,
        exclusions=context.exclusions,
        estimator_name=estimator_name,
        interval_method=interval_method,
    )


def estimate_paired(
    units: tuple[PairedUnit, ...],
    context: AnalysisContext,
    *,
    seed: int = 0,
    estimator_name: str | None = None,
) -> EffectResult:
    """Оценивает B−A из ровно одной сохранённой дельты каждой единицы."""
    for unit in units:
        if unit.unit_id_a != unit.unit_id_b:
            raise PairingError(unit.unit_id_a, unit.unit_id_b)
    differences = tuple(float(unit.value_b - unit.value_a) for unit in units)
    count = len(differences)
    array = np.asarray(differences, dtype=np.float64)
    mean_effect = float(np.mean(array)) if count else math.nan
    median_effect = float(np.median(array)) if count else math.nan
    robust_effect = _trimmed_mean(array)
    name = estimator_name or (
        "block_paired" if context.protocol.kind is Protocol.REPEATED_BLOCKS else "paired_difference"
    )
    inference_n = max(MIN_INFERENCE_N, context.protocol.minimum_n)
    if count < inference_n:
        return DescriptiveEffect(
            mean_effect=mean_effect,
            median_effect=median_effect,
            robust_effect=robust_effect,
            stored_differences=differences,
            metadata=metadata_for(
                context,
                n=count,
                estimator_name=name,
                interval_method="none_insufficient_n",
            ),
        )
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, count, size=(BOOTSTRAP_SAMPLES, count))
    bootstrap = np.mean(array[indices], axis=1)
    low, high = np.quantile(bootstrap, (0.025, 0.975))
    return InferentialEffect(
        mean_effect=mean_effect,
        median_effect=median_effect,
        robust_effect=robust_effect,
        interval=EffectInterval(low=float(low), high=float(high)),
        stored_differences=differences,
        metadata=metadata_for(
            context,
            n=count,
            estimator_name=name,
            interval_method="seeded_block_bootstrap_percentile_95",
        ),
    )


def _trimmed_mean(values: np.ndarray[tuple[int], np.dtype[np.float64]]) -> float:
    """Возвращает 20%-trimmed mean, устойчивое при N=5 и более."""
    if values.size == 0:
        return math.nan
    ordered = np.sort(values)
    trim = math.floor(values.size * 0.2)
    retained = ordered[trim : values.size - trim] if trim else ordered
    return float(np.mean(retained))


def linear_ratio_to_db(*, estimate: float) -> float:
    """Преобразует уже оценённое отношение линейных мощностей в dB."""
    if estimate <= 0:
        return math.nan
    return 10.0 * math.log10(estimate)
