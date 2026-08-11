"""Линейное и детерминированное Monte Carlo распространение ratios/dB."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import assert_never

import numpy as np

from lnt.uncertainty.models import (
    Measurand,
    MonteCarloSettings,
    PropagationMethod,
    UncertaintyResult,
)

DEFAULT_COVERAGE_FACTOR = 2.0


@dataclass(frozen=True, slots=True, kw_only=True)
class RatioRequest:
    """Входы отношения в линейной области и выбранный метод."""

    measurand: Measurand
    numerator: float
    denominator: float
    numerator_standard_uncertainty: float
    denominator_standard_uncertainty: float
    output_unit: str
    method: PropagationMethod
    independent_inputs: bool
    monte_carlo: MonteCarloSettings | None = None
    covariance: float | None = None
    logarithmic: bool = False


def evaluate_ratio(request: RatioRequest) -> UncertaintyResult:
    """Распространяет uncertainty отношения, начиная только с linear inputs."""
    if not request.independent_inputs and request.covariance is None:
        return _withheld(
            request,
            code="independence_not_declared",
            message="Независимость входов отношения не объявлена и ковариация не задана",
        )
    match request.method:
        case PropagationMethod.LINEAR:
            return _linear(request)
        case PropagationMethod.MONTE_CARLO:
            if request.monte_carlo is None:
                return _withheld(
                    request,
                    code="missing_monte_carlo_settings",
                    message="Для Monte Carlo требуются seed и draw_count",
                )
            return _monte_carlo(request, request.monte_carlo)
        case PropagationMethod.UNSUPPORTED_NONLINEAR:
            return _withheld(
                request,
                code="unsupported_nonlinear_method",
                message="Нелинейный метод не поддержан без сохранённого Monte Carlo",
            )
    assert_never(request.method)


def _linear(request: RatioRequest) -> UncertaintyResult:
    ratio = request.numerator / request.denominator
    variance = (request.numerator_standard_uncertainty / request.denominator) ** 2 + (
        request.numerator * request.denominator_standard_uncertainty / request.denominator**2
    ) ** 2
    if request.covariance is not None:
        variance -= 2.0 * request.numerator * request.covariance / request.denominator**3
    if request.logarithmic:
        estimate = 20.0 * math.log10(ratio)
        standard = 20.0 / math.log(10.0) * math.sqrt(variance) / ratio
    else:
        estimate = ratio
        standard = math.sqrt(variance)
    return _available(
        request,
        estimate=estimate,
        standard=standard,
        method="linear_domain_ratio_propagation",
        covariance_included=request.covariance is not None,
    )


def _monte_carlo(request: RatioRequest, settings: MonteCarloSettings) -> UncertaintyResult:
    rng = np.random.default_rng(settings.seed)
    if request.covariance is None:
        numerator = rng.normal(
            request.numerator, request.numerator_standard_uncertainty, settings.draw_count
        )
        denominator = rng.normal(
            request.denominator, request.denominator_standard_uncertainty, settings.draw_count
        )
    else:
        draws = rng.multivariate_normal(
            mean=(request.numerator, request.denominator),
            cov=(
                (request.numerator_standard_uncertainty**2, request.covariance),
                (request.covariance, request.denominator_standard_uncertainty**2),
            ),
            size=settings.draw_count,
        )
        numerator = draws[:, 0]
        denominator = draws[:, 1]
    ratios = numerator / denominator
    values = 20.0 * np.log10(ratios) if request.logarithmic else ratios
    estimate = float(np.mean(values))
    standard = float(np.std(values, ddof=1))
    result = _available(
        request,
        estimate=estimate,
        standard=standard,
        method="monte_carlo_ratio_normal_inputs",
        covariance_included=request.covariance is not None,
    )
    return UncertaintyResult(
        measurand=result.measurand,
        estimate=result.estimate,
        unit=result.unit,
        status=result.status,
        method=result.method,
        standard_uncertainty=result.standard_uncertainty,
        expanded_uncertainty=result.expanded_uncertainty,
        coverage_method=result.coverage_method,
        coverage_factor=result.coverage_factor,
        covariance_included=result.covariance_included,
        monte_carlo_seed=settings.seed,
        monte_carlo_draw_count=settings.draw_count,
    )


def _available(
    request: RatioRequest,
    *,
    estimate: float,
    standard: float,
    method: str,
    covariance_included: bool,
) -> UncertaintyResult:
    return UncertaintyResult(
        measurand=request.measurand,
        estimate=estimate,
        unit=request.output_unit,
        status="available",
        method=method,
        standard_uncertainty=standard,
        expanded_uncertainty=DEFAULT_COVERAGE_FACTOR * standard,
        coverage_method="normal_k_factor",
        coverage_factor=DEFAULT_COVERAGE_FACTOR,
        covariance_included=covariance_included,
    )


def _withheld(request: RatioRequest, *, code: str, message: str) -> UncertaintyResult:
    estimate = request.numerator / request.denominator
    return UncertaintyResult(
        measurand=request.measurand,
        estimate=estimate,
        unit=request.output_unit,
        status="withheld",
        method=request.method.value,
        reason_code=code,
        reason_message=message,
    )
