"""Repeatability Type-A только по независимым capture-level оценкам."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.stats import t

if TYPE_CHECKING:
    from lnt.context.json_codec import JsonValue

MIN_CAPTURES = 3
CONFIDENCE_LEVEL = 0.95


@dataclass(frozen=True, slots=True, kw_only=True)
class RepeatabilityResult:
    """Type-A оценка среднего либо reason-coded отказ."""

    estimate: float
    unit: str
    sample_count: int
    status: str
    method: str
    source: str
    reason_code: str | None = None
    reason_message: str | None = None
    standard_uncertainty: float | None = None
    coverage_factor: float | None = None
    coverage_method: str | None = None
    degrees_of_freedom: int | None = None
    interval_low: float | None = None
    interval_high: float | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        """Сериализует отказ без численной неопределённости."""
        result: dict[str, JsonValue] = {
            "estimate": self.estimate,
            "unit": self.unit,
            "sample_count": self.sample_count,
            "status": self.status,
            "method": self.method,
            "source": self.source,
        }
        optional = {
            "reason_code": self.reason_code,
            "reason_message": self.reason_message,
            "standard_uncertainty": self.standard_uncertainty,
            "coverage_factor": self.coverage_factor,
            "coverage_method": self.coverage_method,
            "degrees_of_freedom": self.degrees_of_freedom,
            "interval_low": self.interval_low,
            "interval_high": self.interval_high,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class _Refusal:
    estimate: float
    unit: str
    count: int
    source: str
    code: str
    message: str


def evaluate_type_a(
    estimates: tuple[float, ...],
    *,
    unit: str,
    independent: bool,
) -> RepeatabilityResult:
    """Считает s/sqrt(n) и 95% Student-t CI для независимых captures."""
    count = len(estimates)
    estimate = float(np.mean(estimates)) if estimates else math.nan
    if not independent:
        return _refusal(
            _Refusal(
                estimate=estimate,
                unit=unit,
                count=count,
                source="capture_level_estimates",
                code="independence_not_declared",
                message="Независимость capture-level оценок не объявлена",
            )
        )
    if count < MIN_CAPTURES:
        return _refusal(
            _Refusal(
                estimate=estimate,
                unit=unit,
                count=count,
                source="capture_level_estimates",
                code="insufficient_independent_captures",
                message="Для Type-A требуются минимум три независимые записи",
            )
        )
    sample_sd = float(np.std(np.asarray(estimates, dtype=np.float64), ddof=1))
    standard = sample_sd / math.sqrt(count)
    degrees = count - 1
    factor = float(t.ppf((1.0 + CONFIDENCE_LEVEL) / 2.0, df=degrees))
    return RepeatabilityResult(
        estimate=estimate,
        unit=unit,
        sample_count=count,
        status="available",
        method="type_a_capture_mean_student_t",
        source="capture_level_estimates",
        standard_uncertainty=standard,
        coverage_factor=factor,
        coverage_method="student_t_two_sided_95",
        degrees_of_freedom=degrees,
        interval_low=estimate - factor * standard,
        interval_high=estimate + factor * standard,
    )


def evaluate_paired_type_a(
    stored_block_differences: tuple[float, ...],
    *,
    unit: str,
    independent: bool,
) -> RepeatabilityResult:
    """Считает paired effect исключительно из сохранённых block differences."""
    result = evaluate_type_a(stored_block_differences, unit=unit, independent=independent)
    return RepeatabilityResult(
        estimate=result.estimate,
        unit=result.unit,
        sample_count=result.sample_count,
        status=result.status,
        method=result.method,
        source="stored_block_differences",
        reason_code=result.reason_code,
        reason_message=result.reason_message,
        standard_uncertainty=result.standard_uncertainty,
        coverage_factor=result.coverage_factor,
        coverage_method=result.coverage_method,
        degrees_of_freedom=result.degrees_of_freedom,
        interval_low=result.interval_low,
        interval_high=result.interval_high,
    )


def _refusal(refusal: _Refusal) -> RepeatabilityResult:
    return RepeatabilityResult(
        estimate=refusal.estimate,
        unit=refusal.unit,
        sample_count=refusal.count,
        status="withheld",
        method="type_a_capture_mean_student_t",
        source=refusal.source,
        reason_code=refusal.code,
        reason_message=refusal.message,
    )
