"""F13: опубликованная запись, объявленные коды и границы притязаний."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.characterization.errors import CharacterizationError
from lnt.characterization.records import Status, Unit, validate_unit_name

if TYPE_CHECKING:
    from collections.abc import Sequence

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]

METHOD: Final = "phase_residual_hilbert_envelope_coactivity"
BAND_COUNT: Final = 3
BAND_EDGE_COUNT: Final = 2
BANDS_HZ: Final = ((3_000.0, 10_000.0), (10_000.0, 50_000.0), (50_000.0, 200_000.0))

PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
BAND_ABOVE_NYQUIST: Final = "band_above_nyquist"
FILTER_SUPPORT_TOO_SHORT: Final = "filter_support_too_short"
FILTER_CONTEXT_UNSTABLE: Final = "filter_context_unstable"
NONFINITE_INPUT: Final = "nonfinite_input"
MIXED_UNAVAILABLE_SUPPORT: Final = "mixed_unavailable_support"
SCALE_ZERO: Final = "scale_zero"
INSUFFICIENT_ACTIVITY: Final = "insufficient_activity"
LAG_SUPPORT_TOO_SHORT: Final = "lag_support_too_short"
LEAKAGE_AMBIGUOUS: Final = "leakage_ambiguous"

DECLARED_CODES: Final = (
    PHASE_REFERENCE_UNAVAILABLE,
    BAND_ABOVE_NYQUIST,
    FILTER_SUPPORT_TOO_SHORT,
    FILTER_CONTEXT_UNSTABLE,
    NONFINITE_INPUT,
    MIXED_UNAVAILABLE_SUPPORT,
    SCALE_ZERO,
    INSUFFICIENT_ACTIVITY,
    LAG_SUPPORT_TOO_SHORT,
    LEAKAGE_AMBIGUOUS,
)

ACTIVITY_FRACTION_NAME: Final = "f13_activity_fraction"
PAIR_QUANTITY_NAMES: Final = (
    "f13_zero_lag_correlation",
    "f13_coincidence_probability",
    "f13_lift",
    "f13_maximum_lag_s",
    "f13_maximum_lag_correlation",
)
PAIR_QUANTITY_UNITS: Final = (
    Unit.RATIO,
    Unit.RATIO,
    Unit.RATIO,
    Unit.S,
    Unit.RATIO,
)

CLAIM_BOUNDARY: Final = (
    "coactivity and lag describe association within one measured channel; "
    "they do not establish coupling, direction, source, or causality"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class F13Declarations:
    """Полный объявленный вход F13 без скрытых настроек."""

    bands_hz: Sequence[Sequence[float]]
    filter: str
    filter_order: int
    filter_phase: str
    filter_edge_guard_fraction: float
    phase_bins: int
    activity_threshold_mad: float
    lag_low_s: float
    lag_high_s: float
    maximum_lag_points: int
    lag_tie_break: str
    minimum_active_samples: int

    def __post_init__(self) -> None:
        """Проверить геометрию, locked vocabulary и числовые домены рецепта."""
        if (
            self.filter != "butterworth_sos"
            or self.filter_phase != "zero"
            or self.lag_tie_break != "minimum_absolute_then_negative"
        ):
            raise ValueError("F13 declarations do not match the locked vocabulary")
        if (
            self.filter_order <= 0
            or self.phase_bins <= 0
            or self.maximum_lag_points <= 0
            or self.minimum_active_samples <= 0
        ):
            raise ValueError("F13 integer declarations must be positive")
        if (
            not math.isfinite(self.activity_threshold_mad)
            or self.activity_threshold_mad <= 0.0
            or not 0.0 < self.filter_edge_guard_fraction <= 1.0
            or not math.isfinite(self.lag_low_s)
            or not math.isfinite(self.lag_high_s)
            or self.lag_low_s >= 0.0
            or self.lag_high_s <= self.lag_low_s
        ):
            raise ValueError("F13 numeric declarations are outside their domains")
        if len(self.bands_hz) != BAND_COUNT or any(
            len(pair) != BAND_EDGE_COUNT for pair in self.bands_hz
        ):
            raise ValueError("F13 requires three two-edge frequency bands")
        pairs = tuple((float(pair[0]), float(pair[1])) for pair in self.bands_hz)
        if any(
            not math.isfinite(low) or not math.isfinite(high) or low < 0.0 or high <= low
            for low, high in pairs
        ) or any(left[1] > right[0] for left, right in pairwise(pairs)):
            raise ValueError("F13 bands must be finite, ordered, and nonoverlapping")


@dataclass(frozen=True, slots=True, kw_only=True)
class F13Result:
    """Симметричная матрица пар F13 и честный общий.support."""

    status: Status
    reason_codes: tuple[str, ...]
    band_names: tuple[str, ...]
    bands_hz: tuple[tuple[float, float], ...]
    lag_s: Float64Array
    activity_fraction: Float64Array
    active_sample_count: Int64Array
    sample_count: int
    qualified_sample_count: int
    zero_lag_correlation: Float64Array
    coincidence_probability: Float64Array
    lift: Float64Array
    maximum_lag_s: Float64Array
    maximum_lag_correlation: Float64Array

    def __post_init__(self) -> None:
        """Проверить коды, оси и пустые домены недоступного результата."""
        if any(code not in DECLARED_CODES for code in self.reason_codes):
            _fail("reason code is outside the F13 vocabulary")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            _fail("reason codes must be sorted and unique")
        if self.status is Status.AVAILABLE and self.reason_codes:
            _fail("available F13 result must not have reasons")
        if self.status is not Status.AVAILABLE and not self.reason_codes:
            _fail("non-available F13 result needs reasons")
        if (
            len(self.band_names) != BAND_COUNT
            or len(set(self.band_names)) != BAND_COUNT
            or any(not name for name in self.band_names)
        ):
            _fail("F13 needs three unique band names")
        if (
            len(self.bands_hz) != BAND_COUNT
            or any(
                not math.isfinite(low) or not math.isfinite(high) or low < 0.0 or high <= low
                for low, high in self.bands_hz
            )
            or any(left[1] > right[0] for left, right in pairwise(self.bands_hz))
        ):
            _fail("F13 bands must be finite, ordered, and nonoverlapping")
        if self.sample_count < 0 or not 0 <= self.qualified_sample_count <= self.sample_count:
            _fail("F13 sample accounting is inconsistent")
        if self.status is Status.UNAVAILABLE:
            _validate_unavailable(self)
            return
        _validate_built(self)


def _validate_unavailable(result: F13Result) -> None:
    """Недоступный F13 сохраняет оси, но не публикует выдуманные измерения."""
    numeric = (
        result.lag_s,
        result.activity_fraction,
        result.zero_lag_correlation,
        result.coincidence_probability,
        result.lift,
        result.maximum_lag_s,
        result.maximum_lag_correlation,
    )
    if (
        result.qualified_sample_count != 0
        or result.active_sample_count.size != 0
        or any(values.size != 0 for values in numeric)
    ):
        _fail("unavailable F13 result must use explicit empty domains")


def _validate_built(result: F13Result) -> None:
    """Проверить общий.support, вероятности и симметрию трёх неупорядоченных пар."""
    validate_unit_name(ACTIVITY_FRACTION_NAME, Unit.RATIO)
    for name, unit in zip(PAIR_QUANTITY_NAMES, PAIR_QUANTITY_UNITS, strict=True):
        validate_unit_name(name, unit)
    if (
        result.qualified_sample_count <= 0
        or result.lag_s.ndim != 1
        or result.lag_s.size == 0
        or not np.all(np.isfinite(result.lag_s))
        or bool(np.any(np.diff(result.lag_s) <= 0.0))
        or not bool(np.any(result.lag_s == 0.0))
    ):
        _fail("built F13 lag axis is invalid")
    matrices = (
        result.zero_lag_correlation,
        result.coincidence_probability,
        result.lift,
        result.maximum_lag_s,
        result.maximum_lag_correlation,
    )
    if (
        result.activity_fraction.shape != (3,)
        or result.active_sample_count.shape != (3,)
        or any(values.shape != (3, 3) for values in matrices)
        or any(not np.all(np.isfinite(values)) for values in matrices)
    ):
        _fail("built F13 arrays do not share their declared domains")
    if (
        not np.all(np.isfinite(result.activity_fraction))
        or np.any(result.activity_fraction < 0.0)
        or np.any(result.activity_fraction > 1.0)
        or np.any(result.active_sample_count < 0)
        or np.any(result.active_sample_count > result.qualified_sample_count)
        or not np.allclose(
            result.activity_fraction,
            result.active_sample_count / result.qualified_sample_count,
            rtol=0.0,
            atol=1e-12,
        )
    ):
        _fail("F13 activity accounting is inconsistent")
    _validate_pair_values(result)


def _validate_pair_values(result: F13Result) -> None:
    """Диагональ и симметрия выражают три уникальные неупорядоченные пары."""
    matrices = (
        result.zero_lag_correlation,
        result.coincidence_probability,
        result.lift,
        result.maximum_lag_s,
        result.maximum_lag_correlation,
    )
    if any(not np.allclose(values, values.T, rtol=0.0, atol=1e-12) for values in matrices):
        _fail("F13 pair matrices must be symmetric")
    if (
        np.any(np.abs(result.zero_lag_correlation) > 1.0)
        or np.any(np.abs(result.maximum_lag_correlation) > 1.0)
        or np.any(result.coincidence_probability < 0.0)
        or np.any(result.coincidence_probability > 1.0)
        or np.any(result.lift < 0.0)
        or not np.allclose(np.diag(result.zero_lag_correlation), 1.0, rtol=0.0, atol=1e-12)
        or not np.allclose(np.diag(result.coincidence_probability), result.activity_fraction)
        or not np.allclose(np.diag(result.lift), 1.0, rtol=0.0, atol=1e-12)
        or not np.allclose(np.diag(result.maximum_lag_s), 0.0, rtol=0.0, atol=1e-12)
        or not np.allclose(np.diag(result.maximum_lag_correlation), 1.0)
        or not np.all(np.isin(result.maximum_lag_s, result.lag_s))
    ):
        _fail("F13 pair values violate their declared domains")


def _fail(detail: str) -> None:
    """Единая доменная ошибка опубликованной F13-записи."""
    raise CharacterizationError("status_invariant", detail)
