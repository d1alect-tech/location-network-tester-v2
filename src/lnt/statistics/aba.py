"""A/B/A-контраст и отдельная квалификация дрейфа A."""

from typing import Final

import numpy as np

from .models import (
    AbaUnit,
    AnalysisContext,
    ContrastRefusal,
    PairedUnit,
    QualifiedWithinRunContrast,
)
from .paired import estimate_paired, metadata_for

DRIFT_EFFECT_FRACTION: Final = 0.5
DRIFT_SD_MULTIPLIER: Final = 2.0
MIN_SD_N: Final = 2


def analyze_aba(
    units: tuple[AbaUnit, ...],
    context: AnalysisContext,
    *,
    seed: int = 0,
) -> QualifiedWithinRunContrast | ContrastRefusal:
    """Считает B−(A1+A2)/2 и отдельно A2−A1 без causal интерпретации."""
    contrast_units = tuple(
        PairedUnit(
            unit_id_a=unit.unit_id,
            unit_id_b=unit.unit_id,
            value_a=(unit.value_a1 + unit.value_a2) / 2.0,
            value_b=unit.value_b,
        )
        for unit in units
    )
    drift_units = tuple(
        PairedUnit(
            unit_id_a=unit.unit_id,
            unit_id_b=unit.unit_id,
            value_a=unit.value_a1,
            value_b=unit.value_a2,
        )
        for unit in units
    )
    effect = estimate_paired(
        contrast_units,
        context,
        seed=seed,
        estimator_name="qualified_within_run_contrast",
    )
    drift = estimate_paired(
        drift_units,
        context,
        seed=seed + 1,
        estimator_name="a2_minus_a1_drift",
    )
    contrast_differences = np.asarray(effect.stored_differences, dtype=np.float64)
    contrast_sd = (
        float(np.std(contrast_differences, ddof=1))
        if contrast_differences.size >= MIN_SD_N
        else 0.0
    )
    threshold = max(
        DRIFT_EFFECT_FRACTION * abs(effect.mean_effect),
        DRIFT_SD_MULTIPLIER * contrast_sd,
    )
    if abs(drift.mean_effect) > threshold:
        return ContrastRefusal(
            reason_code="a_drift_exceeds_half_effect_or_two_sd",
            drift_effect=drift.mean_effect,
            contrast_effect=effect.mean_effect,
            metadata=metadata_for(
                context,
                n=len(units),
                estimator_name="qualified_within_run_contrast",
                interval_method="blocked_by_a_drift",
            ),
        )
    return QualifiedWithinRunContrast(
        effect=effect,
        drift=drift,
        metadata=effect.metadata,
    )
