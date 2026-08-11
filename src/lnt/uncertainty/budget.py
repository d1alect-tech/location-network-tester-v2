"""Линейное распространение явных Type-B компонентов и ковариаций."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import assert_never

from lnt.uncertainty.models import (
    ComponentContribution,
    CovarianceTerm,
    Measurand,
    NormalDistribution,
    RectangularDistribution,
    TriangularDistribution,
    TypeBComponent,
    TypeBDistribution,
    UncertaintyResult,
)

DEFAULT_COVERAGE_FACTOR = 2.0


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetRequest:
    """Полный запрос линейного бюджета одной поддержанной величины."""

    measurand: Measurand
    estimate: float
    unit: str
    components: tuple[TypeBComponent, ...]
    required_components: frozenset[str]
    independent_components: bool = False
    covariance: tuple[CovarianceTerm, ...] = ()


def standard_uncertainty(distribution: TypeBDistribution) -> tuple[str, float]:
    """Преобразует явное распределение профиля в standard uncertainty."""
    match distribution:
        case NormalDistribution(standard_uncertainty=value):
            return "normal", value
        case RectangularDistribution(half_width=value):
            return "rectangular", value / math.sqrt(3.0)
        case TriangularDistribution(half_width=value):
            return "triangular", value / math.sqrt(6.0)
    assert_never(distribution)


def evaluate_budget(request: BudgetRequest) -> UncertaintyResult:
    """Комбинирует компоненты; не предполагает отсутствующую независимость."""
    by_name = {component.name: component for component in request.components}
    missing = request.required_components - by_name.keys()
    if missing:
        return _withheld(
            request,
            code="missing_type_b_component",
            message=f"Отсутствуют обязательные Type-B компоненты: {', '.join(sorted(missing))}",
        )
    covariance_by_pair = {
        frozenset((term.left, term.right)): term.covariance for term in request.covariance
    }
    correlated_pairs = _declared_correlated_pairs(request.components)
    absent_covariance = correlated_pairs - covariance_by_pair.keys()
    if absent_covariance:
        return _withheld(
            request,
            code="missing_declared_covariance",
            message="Для объявленной корреляции не предоставлена ковариация",
        )
    if (
        len(request.components) > 1
        and not request.independent_components
        and not request.covariance
    ):
        return _withheld(
            request,
            code="independence_not_declared",
            message="Независимость Type-B компонентов не объявлена",
        )
    contributions = tuple(_contribution(component) for component in request.components)
    variance = sum(
        contribution.standard_uncertainty**2 * contribution.sensitivity_value**2
        for contribution in contributions
    )
    for term in request.covariance:
        left = by_name.get(term.left)
        right = by_name.get(term.right)
        if left is not None and right is not None:
            variance += 2.0 * left.sensitivity.value * right.sensitivity.value * term.covariance
    if variance < 0.0:
        return _withheld(
            request,
            code="invalid_covariance_matrix",
            message="Предоставленные ковариации дают отрицательную дисперсию",
        )
    combined = math.sqrt(variance)
    return UncertaintyResult(
        measurand=request.measurand,
        estimate=request.estimate,
        unit=request.unit,
        status="available",
        method="linear_sensitivity_coefficients",
        standard_uncertainty=combined,
        expanded_uncertainty=DEFAULT_COVERAGE_FACTOR * combined,
        coverage_method="normal_k_factor",
        coverage_factor=DEFAULT_COVERAGE_FACTOR,
        covariance_included=bool(request.covariance),
        components=contributions,
    )


def _contribution(component: TypeBComponent) -> ComponentContribution:
    distribution_name, uncertainty = standard_uncertainty(component.distribution)
    return ComponentContribution(
        name=component.name,
        distribution=distribution_name,
        standard_uncertainty=uncertainty,
        sensitivity_name=component.sensitivity.name,
        sensitivity_value=component.sensitivity.value,
    )


def _declared_correlated_pairs(
    components: tuple[TypeBComponent, ...],
) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    for index, left in enumerate(components):
        for right in components[index + 1 :]:
            if (
                left.correlation_group is not None
                and left.correlation_group == right.correlation_group
            ):
                pairs.add(frozenset((left.name, right.name)))
    return pairs


def _withheld(request: BudgetRequest, *, code: str, message: str) -> UncertaintyResult:
    return UncertaintyResult(
        measurand=request.measurand,
        estimate=request.estimate,
        unit=request.unit,
        status="withheld",
        method="linear_sensitivity_coefficients",
        reason_code=code,
        reason_message=message,
    )
