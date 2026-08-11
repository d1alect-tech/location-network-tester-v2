"""Versioned transformer line-quality monitoring and like-for-like comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypedDict

import numpy as np
from numpy.typing import NDArray

from lnt.line_quality import (
    LineQualityMetrics,
    compute_line_quality,
    line_quality_to_payload,
)
from lnt.uncertainty import (
    BudgetRequest,
    Measurand,
    SensitivityCoefficient,
    TypeBComponent,
    evaluate_budget,
)

LINE_QUALITY_VERSION: Final = 2
LINE_QUALITY_DISCLAIMER_RU: Final = (
    "Только мониторинг: не сертифицированное измерение качества электроэнергии или фликера по IEC."
)
Float32Array = NDArray[np.float32]


@dataclass(frozen=True, slots=True, kw_only=True)
class WindowScheme:
    """Explicit non-overlapping window recipe."""

    duration_s: float = 1.0


DEFAULT_WINDOW_SCHEME: Final = WindowScheme(duration_s=1.0)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformerCalibrationProfile:
    """Calibrated transformer ratio and its explicit Type-B component."""

    identity: str
    ratio: float
    ratio_uncertainty: TypeBComponent


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricInterval:
    """Observed minimum, maximum, and span across sub-windows."""

    minimum: float
    maximum: float
    span: float


@dataclass(frozen=True, slots=True, kw_only=True)
class LineQualityWindow:
    """One explicit time window and its retained v1 metrics."""

    start_s: float
    end_s: float
    metrics: LineQualityMetrics


@dataclass(frozen=True, slots=True, kw_only=True)
class PrimaryRmsEstimate:
    """Calibrated primary estimate or a reason-coded withholding."""

    status: Literal["available", "withheld"]
    value_v: float | None = None
    standard_uncertainty_v: float | None = None
    expanded_uncertainty_v: float | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LineQualityV2:
    """Versioned monitoring result with whole-record and drift metrics."""

    line_quality_version: int
    sample_rate_hz: float
    window_scheme: WindowScheme
    transformer_profile_identity: str | None
    metrics: LineQualityMetrics
    windows: tuple[LineQualityWindow, ...]
    frequency_interval: MetricInterval
    secondary_rms_interval: MetricInterval
    thd_interval: MetricInterval
    primary_rms: PrimaryRmsEstimate
    disclaimer_ru: str = LINE_QUALITY_DISCLAIMER_RU


class PrimaryRmsPayload(TypedDict, total=False):
    """Serialized calibrated primary estimate."""

    status: str
    value_v: float
    standard_uncertainty_v: float
    expanded_uncertainty_v: float
    reason_code: str


def compute_line_quality_v2(
    ch1: Float32Array,
    *,
    sample_rate_hz: float,
    window_scheme: WindowScheme = DEFAULT_WINDOW_SCHEME,
    profile: TransformerCalibrationProfile | None = None,
) -> LineQualityV2:
    """Retain v1 metrics and add explicit-window monitoring drift."""
    metrics = compute_line_quality(ch1, sample_rate_hz=sample_rate_hz)
    window_samples = round(window_scheme.duration_s * sample_rate_hz)
    windows = tuple(
        LineQualityWindow(
            start_s=start / sample_rate_hz,
            end_s=(start + window_samples) / sample_rate_hz,
            metrics=compute_line_quality(
                ch1[start : start + window_samples], sample_rate_hz=sample_rate_hz
            ),
        )
        for start in range(0, ch1.size - window_samples + 1, window_samples)
    )
    if not windows:
        windows = (
            LineQualityWindow(start_s=0.0, end_s=ch1.size / sample_rate_hz, metrics=metrics),
        )
    return LineQualityV2(
        line_quality_version=LINE_QUALITY_VERSION,
        sample_rate_hz=sample_rate_hz,
        window_scheme=window_scheme,
        transformer_profile_identity=None if profile is None else profile.identity,
        metrics=metrics,
        windows=windows,
        frequency_interval=_interval(tuple(item.metrics.fundamental_hz for item in windows)),
        secondary_rms_interval=_interval(tuple(item.metrics.fundamental_rms_v for item in windows)),
        thd_interval=_interval(tuple(item.metrics.thd_ratio for item in windows)),
        primary_rms=_primary_rms(metrics.fundamental_rms_v, profile),
    )


def _interval(values: tuple[float, ...]) -> MetricInterval:
    minimum = min(values)
    maximum = max(values)
    return MetricInterval(minimum=minimum, maximum=maximum, span=maximum - minimum)


def _primary_rms(
    secondary_rms_v: float, profile: TransformerCalibrationProfile | None
) -> PrimaryRmsEstimate:
    if profile is None:
        return PrimaryRmsEstimate(status="withheld", reason_code="transformer_profile_required")
    component = TypeBComponent(
        name=profile.ratio_uncertainty.name,
        distribution=profile.ratio_uncertainty.distribution,
        sensitivity=SensitivityCoefficient(name="secondary_rms_v", value=secondary_rms_v),
        correlation_group=profile.ratio_uncertainty.correlation_group,
    )
    budget = evaluate_budget(
        BudgetRequest(
            measurand=Measurand.PRIMARY_RMS_CALIBRATED,
            estimate=secondary_rms_v * profile.ratio,
            unit="V",
            components=(component,),
            required_components=frozenset({component.name}),
            independent_components=True,
        )
    )
    return PrimaryRmsEstimate(
        status="available",
        value_v=budget.estimate,
        standard_uncertainty_v=budget.standard_uncertainty,
        expanded_uncertainty_v=budget.expanded_uncertainty,
    )


def line_quality_v2_to_payload(result: LineQualityV2) -> dict[str, object]:
    """Serialize the monitoring result without fabricating withheld numbers."""
    primary: PrimaryRmsPayload = {"status": result.primary_rms.status}
    if result.primary_rms.value_v is not None:
        primary["value_v"] = result.primary_rms.value_v
    if result.primary_rms.standard_uncertainty_v is not None:
        primary["standard_uncertainty_v"] = result.primary_rms.standard_uncertainty_v
    if result.primary_rms.expanded_uncertainty_v is not None:
        primary["expanded_uncertainty_v"] = result.primary_rms.expanded_uncertainty_v
    if result.primary_rms.reason_code is not None:
        primary["reason_code"] = result.primary_rms.reason_code
    return {
        "line_quality_version": result.line_quality_version,
        "sample_rate_hz": result.sample_rate_hz,
        "window_duration_s": result.window_scheme.duration_s,
        "transformer_profile_identity": result.transformer_profile_identity,
        "metrics": line_quality_to_payload(result.metrics),
        "windows": [
            {
                "start_s": item.start_s,
                "end_s": item.end_s,
                "metrics": line_quality_to_payload(item.metrics),
            }
            for item in result.windows
        ],
        "frequency_interval": _interval_payload(result.frequency_interval),
        "secondary_rms_interval": _interval_payload(result.secondary_rms_interval),
        "thd_interval": _interval_payload(result.thd_interval),
        "primary_rms": primary,
        "disclaimer_ru": result.disclaimer_ru,
    }


def _interval_payload(value: MetricInterval) -> dict[str, float]:
    return {"minimum": value.minimum, "maximum": value.maximum, "span": value.span}
