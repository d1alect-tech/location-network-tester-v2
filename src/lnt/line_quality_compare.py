"""Like-for-like comparison of versioned line-quality monitoring results."""

from dataclasses import dataclass
from typing import Literal, override

from lnt.analysis import AnalysisResult, LineQualityAnalysis
from lnt.line_quality import MAX_HARMONIC_ORDER, LineHarmonic
from lnt.line_quality_v2 import LINE_QUALITY_DISCLAIMER_RU, LineQualityV2


@dataclass(frozen=True, slots=True, kw_only=True)
class LineQualityIncompatibilityError(Exception):
    """Typed Russian rejection for non-like-for-like inputs."""

    reason_code: str
    message_ru: str

    @override
    def __str__(self) -> str:
        return self.message_ru


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricDelta:
    """Scalar B-A delta with both source values."""

    value_a: float
    value_b: float
    delta: float


@dataclass(frozen=True, slots=True, kw_only=True)
class HarmonicDelta:
    """One H2-H40 delta or explicit Nyquist absence."""

    order: int
    status: Literal["available", "absent_a", "absent_b", "absent_both"]
    ratio_a: float | None
    ratio_b: float | None
    delta_ratio: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class LineQualityComparison:
    """Complete monitoring comparison result."""

    frequency: MetricDelta
    secondary_rms: MetricDelta
    thd: MetricDelta
    crest: MetricDelta
    envelope_cv: MetricDelta
    harmonics: tuple[HarmonicDelta, ...]
    disclaimer_ru: str = LINE_QUALITY_DISCLAIMER_RU


type ComparisonInput = LineQualityV2 | AnalysisResult | LineQualityAnalysis | str


def compare_line_quality(a: ComparisonInput, b: ComparisonInput) -> LineQualityComparison:
    """Compare only compatible v2 line-quality recipes and profiles."""
    if not isinstance(a, LineQualityV2) or not isinstance(b, LineQualityV2):
        raise LineQualityIncompatibilityError(
            reason_code="session_type_mismatch",
            message_ru="Сравнение возможно только между line-quality сессиями.",
        )
    recipe_a = (a.line_quality_version, a.sample_rate_hz, a.window_scheme)
    recipe_b = (b.line_quality_version, b.sample_rate_hz, b.window_scheme)
    if recipe_a != recipe_b:
        raise LineQualityIncompatibilityError(
            reason_code="recipe_mismatch",
            message_ru=(
                "Несовместимые рецепты line-quality: частота дискретизации или окна различаются."
            ),
        )
    if a.transformer_profile_identity != b.transformer_profile_identity:
        raise LineQualityIncompatibilityError(
            reason_code="transformer_profile_mismatch",
            message_ru="Несовместимые профили трансформатора.",
        )
    return LineQualityComparison(
        frequency=_delta(a.metrics.fundamental_hz, b.metrics.fundamental_hz),
        secondary_rms=_delta(a.metrics.fundamental_rms_v, b.metrics.fundamental_rms_v),
        thd=_delta(a.metrics.thd_ratio, b.metrics.thd_ratio),
        crest=_delta(a.metrics.crest_factor, b.metrics.crest_factor),
        envelope_cv=_delta(a.metrics.envelope_cv, b.metrics.envelope_cv),
        harmonics=_harmonic_deltas(a.metrics.harmonics, b.metrics.harmonics),
    )


def _delta(value_a: float, value_b: float) -> MetricDelta:
    return MetricDelta(value_a=value_a, value_b=value_b, delta=value_b - value_a)


def _harmonic_deltas(
    harmonics_a: tuple[LineHarmonic, ...], harmonics_b: tuple[LineHarmonic, ...]
) -> tuple[HarmonicDelta, ...]:
    by_a = {item.order: item.ratio for item in harmonics_a}
    by_b = {item.order: item.ratio for item in harmonics_b}
    return tuple(
        _harmonic_delta(order, by_a.get(order), by_b.get(order))
        for order in range(2, MAX_HARMONIC_ORDER + 1)
    )


def _harmonic_delta(order: int, ratio_a: float | None, ratio_b: float | None) -> HarmonicDelta:
    if ratio_a is None and ratio_b is None:
        status = "absent_both"
    elif ratio_a is None:
        status = "absent_a"
    elif ratio_b is None:
        status = "absent_b"
    else:
        status = "available"
    return HarmonicDelta(
        order=order,
        status=status,
        ratio_a=ratio_a,
        ratio_b=ratio_b,
        delta_ratio=None if ratio_a is None or ratio_b is None else ratio_b - ratio_a,
    )
