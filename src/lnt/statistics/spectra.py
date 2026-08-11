"""Exploratory bin-wise спектры с BH FDR и contiguous clusters."""

from __future__ import annotations

import numpy as np
from scipy.stats import t

from .models import (
    AnalysisContext,
    PairedUnit,
    SpectralCluster,
    SpectralResult,
    SpectrumPair,
)
from .paired import estimate_paired, metadata_for

FDR_ALPHA = 0.05
MIN_TEST_N = 2


def benjamini_hochberg(p_values: tuple[float, ...]) -> tuple[float, ...]:
    """Возвращает монотонные BH q-values в исходном порядке бинов."""
    count = len(p_values)
    if count == 0:
        return ()
    values = np.asarray(p_values, dtype=np.float64)
    order = np.argsort(values, kind="stable")
    ranked = values[order] * count / np.arange(1, count + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    result = np.empty(count, dtype=np.float64)
    result[order] = np.minimum(adjusted, 1.0)
    return tuple(float(item) for item in result)


def analyze_spectra(
    frequencies_hz: tuple[float, ...],
    pairs: tuple[SpectrumPair, ...],
    context: AnalysisContext,
    *,
    seed: int = 0,
) -> SpectralResult:
    """Сохраняет paired bin effects, p/q-values и смежные значимые диапазоны."""
    effects = tuple(
        estimate_paired(
            tuple(
                PairedUnit(
                    unit_id_a=pair.unit_id_a,
                    unit_id_b=pair.unit_id_b,
                    value_a=pair.values_a[index],
                    value_b=pair.values_b[index],
                )
                for pair in pairs
            ),
            context,
            seed=seed + index,
        )
        for index in range(len(frequencies_hz))
    )
    p_values = tuple(_paired_p_value(effect.stored_differences) for effect in effects)
    q_values = benjamini_hochberg(p_values)
    clusters = _clusters(frequencies_hz, tuple(value <= FDR_ALPHA for value in q_values))
    return SpectralResult(
        frequencies_hz=frequencies_hz,
        effects=effects,
        p_values=p_values,
        q_values=q_values,
        clusters=clusters,
        metadata=metadata_for(
            context,
            n=len(pairs),
            estimator_name="paired_spectral_difference_bh",
            interval_method="seeded_block_bootstrap_percentile_95",
        ),
    )


def _paired_p_value(differences: tuple[float, ...]) -> float:
    values = np.asarray(differences, dtype=np.float64)
    if values.size < MIN_TEST_N:
        return 1.0
    if np.all(values == values[0]):
        return 0.0 if values[0] != 0 else 1.0
    standard_error = float(np.std(values, ddof=1)) / np.sqrt(values.size)
    statistic = float(np.mean(values)) / standard_error
    return float(2.0 * t.sf(abs(statistic), df=values.size - 1))


def _clusters(
    frequencies_hz: tuple[float, ...], significant: tuple[bool, ...]
) -> tuple[SpectralCluster, ...]:
    clusters: list[SpectralCluster] = []
    start: int | None = None
    for index, is_significant in enumerate((*significant, False)):
        if is_significant and start is None:
            start = index
        if not is_significant and start is not None:
            clusters.append(
                SpectralCluster(
                    low_hz=frequencies_hz[start],
                    high_hz=frequencies_hz[index - 1],
                    bin_count=index - start,
                )
            )
            start = None
    return tuple(clusters)
