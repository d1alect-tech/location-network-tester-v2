"""Назначение канонических F15 мод окну пика для F11."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from lnt.characterization.records import Status
from lnt.characterization.sync_grid import nominal_window_samples

if TYPE_CHECKING:
    from lnt.characterization.f11_result import F15ModeSource, FeatureVector

F15_WINDOW_S: Final = 0.02
F15_OVERLAP_FRACTION: Final = 0.0
F15_FEATURE_COUNT: Final = 7


@dataclass(frozen=True, slots=True, kw_only=True)
class ModeModel:
    """Проверенное представление успешного результата F15."""

    window_samples: int
    feature_medians: FeatureVector
    feature_mads: FeatureVector
    canonical_labels: tuple[str, ...]
    canonical_features: tuple[FeatureVector, ...]
    window_features: tuple[FeatureVector | None, ...]
    window_labels: tuple[str | None, ...]


def build_mode_model(source: F15ModeSource, *, sample_rate_hz: float) -> ModeModel | None:
    """Проверить F15 и подготовить сетку 20 мс; недоступный F15 возвращает None."""
    if source.status is not Status.AVAILABLE:
        return None
    if (
        not math.isfinite(source.window_s)
        or source.window_s != F15_WINDOW_S
        or source.overlap_fraction != F15_OVERLAP_FRACTION
        or not math.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0.0
    ):
        raise ValueError("F11 requires the declared available 20 ms nonoverlapping F15 window")
    window_samples = nominal_window_samples(source.window_s, sample_rate_hz)
    if window_samples <= 0:
        raise ValueError("F15 window must contain at least one sample")
    labels = source.canonical_labels
    medoids = source.canonical_standardized_features
    if not labels or len(labels) != len(medoids) or len(set(labels)) != len(labels):
        raise ValueError("F15 canonical labels and medoids must be non-empty and aligned")
    if any(not _finite_vector(vector, F15_FEATURE_COUNT) for vector in medoids):
        raise ValueError("F15 medoids must contain seven finite features")
    if not _finite_vector(source.feature_medians, F15_FEATURE_COUNT) or not _finite_vector(
        source.feature_mads, F15_FEATURE_COUNT
    ):
        raise ValueError("F15 standardization must contain seven finite values")
    if any(value <= 0.0 for value in source.feature_mads):
        raise ValueError("F15 feature MAD values must be positive")
    if len(source.window_features) != len(source.window_labels):
        raise ValueError("F15 window features and labels must be aligned")
    if any(label is not None and label not in labels for label in source.window_labels):
        raise ValueError("F15 window label is not a canonical medoid label")
    return ModeModel(
        window_samples=window_samples,
        feature_medians=source.feature_medians,
        feature_mads=source.feature_mads,
        canonical_labels=labels,
        canonical_features=medoids,
        window_features=source.window_features,
        window_labels=source.window_labels,
    )


def assign_mode(model: ModeModel, peak_sample: int) -> str | None:
    """Вернуть сохранённую метку окна либо ближайший канонический медоид."""
    if peak_sample < 0:
        return None
    window_index = peak_sample // model.window_samples
    if window_index >= len(model.window_features):
        return None
    stored = model.window_labels[window_index]
    if stored is not None:
        return stored
    features = model.window_features[window_index]
    if features is None or not _finite_vector(features, F15_FEATURE_COUNT):
        return None
    standardized = tuple(
        (value - center) / scale
        for value, center, scale in zip(
            features, model.feature_medians, model.feature_mads, strict=True
        )
    )
    best_label: str | None = None
    best_distance = math.inf
    for label, medoid in sorted(
        zip(model.canonical_labels, model.canonical_features, strict=True), key=lambda pair: pair[0]
    ):
        distance = math.fsum(
            (value - center) ** 2 for value, center in zip(standardized, medoid, strict=True)
        )
        if distance < best_distance:
            best_label = label
            best_distance = distance
    return best_label


def _finite_vector(values: FeatureVector, expected: int) -> bool:
    """Проверить длину и конечность вектора признаков."""
    return len(values) == expected and all(math.isfinite(value) for value in values)
