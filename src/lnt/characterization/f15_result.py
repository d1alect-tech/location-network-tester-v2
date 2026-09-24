"""F15: опубликованная запись, проверки и зафиксированные настройки."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.records import Status, Unit, validate_unit_name

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

METHOD: Final = "deterministic_pam_fixed_k_medoids"
_FEATURE_COUNT: Final = 7
_CLUSTER_COUNT: Final = 4
_MAXIMUM_SWAP_PASSES: Final = 100
_STABILITY_BLOCK_COUNT: Final = 8
_WINDOW_S: Final = 0.02
FEATURE_NAMES: Final = (
    "rms_v",
    "crest_factor",
    "band_3000_10000_rms_v",
    "band_10000_50000_rms_v",
    "band_50000_200000_rms_v",
    "event_count",
    "f10_occupancy_5mad",
)
INSUFFICIENT_WINDOWS: Final = "insufficient_windows"
FEATURE_UNAVAILABLE: Final = "feature_unavailable"
FEATURE_SCALE_ZERO: Final = "feature_scale_zero"
EMPTY_CLUSTER: Final = "empty_cluster"
STABILITY_BLOCK_TOO_SHORT: Final = "stability_block_too_short"
LABEL_LIMIT: Final = "label_limit"
FEATURE_UNITS: Final = (
    Unit.V,
    Unit.RATIO,
    Unit.V,
    Unit.V,
    Unit.V,
    Unit.COUNT,
    Unit.RATIO,
)
DECLARED_CODES: Final = (
    EMPTY_CLUSTER,
    FEATURE_SCALE_ZERO,
    FEATURE_UNAVAILABLE,
    INSUFFICIENT_WINDOWS,
    LABEL_LIMIT,
    STABILITY_BLOCK_TOO_SHORT,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class F15Settings:
    """Объявленные значения рецепта F15 для детерминированного движка."""

    window_s: float = _WINDOW_S
    overlap_fraction: float = 0.0
    features: tuple[str, ...] = FEATURE_NAMES
    standardization: str = "median_mad"
    distance: str = "euclidean"
    cluster_count: int = _CLUSTER_COUNT
    initialization: str = "pam_build"
    optimization: str = "pam_swap"
    maximum_swap_passes: int = _MAXIMUM_SWAP_PASSES
    tie_break: str = "lowest_window_index"
    label_order: str = "medoid_rms_then_index"
    stability_blocks: int = _STABILITY_BLOCK_COUNT
    stability_metric: str = "adjusted_rand_index"
    minimum_windows: int = 80
    maximum_labels: int = 4096
    subsampling: str = "even_floor_index"

    def __post_init__(self) -> None:
        """Проверить закрытый словарь алгоритма и положительные числовые гейты."""
        if (
            self.window_s != _WINDOW_S
            or self.overlap_fraction != 0.0
            or self.features != FEATURE_NAMES
            or self.standardization != "median_mad"
            or self.distance != "euclidean"
            or self.cluster_count != _CLUSTER_COUNT
            or self.initialization != "pam_build"
            or self.optimization != "pam_swap"
            or self.tie_break != "lowest_window_index"
            or self.label_order != "medoid_rms_then_index"
            or self.stability_metric != "adjusted_rand_index"
            or self.subsampling != "even_floor_index"
        ):
            raise ValueError("F15 settings do not match the locked algorithm vocabulary")
        if (
            not math.isfinite(self.window_s)
            or self.window_s <= 0.0
            or self.maximum_swap_passes != _MAXIMUM_SWAP_PASSES
            or self.stability_blocks != _STABILITY_BLOCK_COUNT
            or self.minimum_windows < self.cluster_count
            or self.maximum_labels < self.cluster_count
        ):
            raise ValueError("F15 numeric settings are outside their declared domains")

    @classmethod
    def locked(cls) -> F15Settings:
        """Вернуть зафиксированные настройки characterization-v1."""
        return cls()


@dataclass(frozen=True, slots=True, kw_only=True)
class F15Result:
    """Канонические метки F15, реальные медиоиды и состояние доступности."""

    status: Status
    reason_codes: tuple[str, ...]
    window_s: float
    feature_names: tuple[str, ...]
    feature_medians: Float64Array
    feature_mads: Float64Array
    standardized_features: Float64Array
    window_indices: Int64Array
    medoid_indices: Int64Array
    medoid_features: Float64Array
    medoid_rms_v: Float64Array
    labels: Int64Array
    dwell_labels: Int64Array
    dwell_durations_s: Float64Array
    transition_counts: Int64Array
    transition_probabilities: Float64Array
    stability_ari: Float64Array
    swap_passes: int
    complete_window_count: int
    qualified_window_count: int
    unretained_window_count: int

    def __post_init__(self) -> None:
        """Проверить коды, единицы, форму массивов и полный учёт окон."""
        _validate_result(self)


def _validate_result(result: F15Result) -> None:  # noqa: C901 - полный контракт F15
    """Проверить недоступные и построенные формы одним набором инвариантов."""
    if any(code not in DECLARED_CODES for code in result.reason_codes):
        _fail("reason code is outside the F15 vocabulary")
    if result.reason_codes != tuple(sorted(set(result.reason_codes))):
        _fail("reason codes must be sorted and unique")
    if result.status is Status.AVAILABLE and result.reason_codes:
        _fail("available F15 result must not have reasons")
    if result.status is not Status.AVAILABLE and not result.reason_codes:
        _fail("non-available F15 result needs reasons")
    if result.feature_names != FEATURE_NAMES:
        _fail("F15 feature declaration does not match the locked order")
    for name, unit in zip(result.feature_names, FEATURE_UNITS, strict=True):
        validate_unit_name(name, unit)
    if not math.isfinite(result.window_s) or result.window_s <= 0.0:
        _fail("F15 window duration must be finite and positive")
    counts = (
        result.swap_passes,
        result.complete_window_count,
        result.qualified_window_count,
        result.unretained_window_count,
    )
    if (
        result.swap_passes < 0
        or result.swap_passes > _MAXIMUM_SWAP_PASSES
        or any(count < 0 for count in counts)
        or result.qualified_window_count > result.complete_window_count
        or result.unretained_window_count
        != result.complete_window_count - result.qualified_window_count
    ):
        _fail("F15 window accounting is inconsistent")
    float_arrays = (
        result.feature_medians,
        result.feature_mads,
        result.standardized_features,
        result.medoid_features,
        result.medoid_rms_v,
        result.dwell_durations_s,
        result.transition_probabilities,
        result.stability_ari,
    )
    if any(not np.all(np.isfinite(values)) for values in float_arrays):
        _fail("F15 floating arrays must be finite")
    if result.status is Status.UNAVAILABLE:
        _validate_unavailable(result)
        return
    _validate_built(result)


def _validate_unavailable(result: F15Result) -> None:
    """Недоступность не публикует нулевые medoid, label или transition значения."""
    if (
        result.qualified_window_count != 0
        or result.feature_medians.size != 0
        or result.feature_mads.size != 0
        or result.standardized_features.shape != (0, _FEATURE_COUNT)
        or result.window_indices.size != 0
        or result.medoid_indices.size != 0
        or result.medoid_features.shape != (0, _FEATURE_COUNT)
        or result.labels.size != 0
        or result.dwell_labels.size != 0
        or result.transition_counts.shape != (0, 0)
        or result.transition_probabilities.shape != (0, 0)
        or result.stability_ari.size != 0
    ):
        _fail("unavailable F15 result must use explicit empty domains")


def _validate_built(result: F15Result) -> None:
    """Построенный результат хранит четыре канонические группы и полные переходы."""
    rows = result.qualified_window_count
    if (
        result.feature_medians.shape != (_FEATURE_COUNT,)
        or result.feature_mads.shape != (_FEATURE_COUNT,)
        or bool(np.any(result.feature_mads <= 0.0))
        or result.standardized_features.shape != (rows, _FEATURE_COUNT)
        or result.window_indices.shape != (rows,)
        or bool(np.any(np.diff(result.window_indices) <= 0))
        or result.medoid_indices.shape != (_CLUSTER_COUNT,)
        or result.medoid_features.shape != (_CLUSTER_COUNT, _FEATURE_COUNT)
        or result.medoid_rms_v.shape != (_CLUSTER_COUNT,)
        or result.labels.shape != (rows,)
        or bool(np.any((result.labels < 0) | (result.labels >= _CLUSTER_COUNT)))
        or not bool(np.all(np.isin(result.medoid_indices, result.window_indices)))
    ):
        _fail("built F15 arrays do not share their declared domains")
    order = np.lexsort((result.medoid_indices, result.medoid_rms_v))
    if not np.array_equal(result.medoid_indices, result.medoid_indices[order]):
        _fail("F15 medoids are not ordered by RMS then window index")
    if (
        result.dwell_labels.ndim != 1
        or result.dwell_labels.shape != result.dwell_durations_s.shape
        or bool(np.any((result.dwell_labels < 0) | (result.dwell_labels >= _CLUSTER_COUNT)))
        or bool(np.any(result.dwell_durations_s <= 0.0))
        or result.transition_counts.shape != (_CLUSTER_COUNT, _CLUSTER_COUNT)
        or result.transition_probabilities.shape != (_CLUSTER_COUNT, _CLUSTER_COUNT)
    ):
        _fail("F15 dwell or transition shape is invalid")
    totals = np.sum(result.transition_counts, axis=1)
    active = totals > 0
    if not np.allclose(
        np.sum(result.transition_probabilities[active], axis=1),
        1.0,
        rtol=0.0,
        atol=1e-12,
    ):
        _fail("F15 transition rows are not normalized")
    short = STABILITY_BLOCK_TOO_SHORT in result.reason_codes
    if result.stability_ari.shape != ((0,) if short else (_STABILITY_BLOCK_COUNT,)):
        _fail("F15 stability metric domain does not match its reason code")
    if result.stability_ari.size and bool(np.any(np.abs(result.stability_ari) > 1.0)):
        _fail("F15 adjusted Rand index must stay in [-1, 1]")


def _fail(detail: str) -> None:
    """Единая доменная ошибка публикуемой F15-записи."""
    raise CharacterizationError("status_invariant", detail)
