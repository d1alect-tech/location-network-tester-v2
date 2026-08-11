from __future__ import annotations

import json
import math

import pytest
from scipy.stats import t

from lnt.uncertainty import (
    BudgetRequest,
    CovarianceTerm,
    Measurand,
    MonteCarloSettings,
    NormalDistribution,
    PropagationMethod,
    RatioRequest,
    RectangularDistribution,
    SensitivityCoefficient,
    SingleRecordDescription,
    TriangularDistribution,
    TypeBComponent,
    evaluate_budget,
    evaluate_paired_type_a,
    evaluate_ratio,
    evaluate_type_a,
)


@pytest.mark.parametrize(
    ("measurand", "unit"),
    [
        (Measurand.BAND_RMS, "V"),
        (Measurand.BAND_POWER, "V²"),
        (Measurand.SECONDARY_RMS, "V"),
        (Measurand.PRIMARY_RMS_CALIBRATED, "V"),
        (Measurand.THD, "1"),
        (Measurand.HARMONIC_RATIO, "1"),
    ],
)
def test_named_measurands_match_analytic_linear_budget(
    measurand: Measurand,
    unit: str,
) -> None:
    components = (
        TypeBComponent(
            name="calibration",
            distribution=NormalDistribution(standard_uncertainty=3.0),
            sensitivity=SensitivityCoefficient(name="calibration_gain", value=2.0),
        ),
        TypeBComponent(
            name="resolution",
            distribution=RectangularDistribution(half_width=math.sqrt(3.0) * 8.0),
            sensitivity=SensitivityCoefficient(name="resolution_gain", value=0.5),
        ),
        TypeBComponent(
            name="profile_limit",
            distribution=TriangularDistribution(half_width=math.sqrt(6.0) * 2.0),
            sensitivity=SensitivityCoefficient(name="profile_gain", value=1.0),
        ),
    )

    result = evaluate_budget(
        BudgetRequest(
            measurand=measurand,
            estimate=10.0,
            unit=unit,
            components=components,
            required_components=frozenset({"calibration", "resolution", "profile_limit"}),
            independent_components=True,
        )
    )

    assert result.standard_uncertainty == pytest.approx(math.sqrt(36.0 + 16.0 + 4.0))
    assert result.expanded_uncertainty == pytest.approx(2.0 * math.sqrt(56.0))
    assert result.coverage_method == "normal_k_factor"
    assert result.coverage_factor == 2.0
    assert {item.sensitivity_name for item in result.components} == {
        "calibration_gain",
        "resolution_gain",
        "profile_gain",
    }
    json.dumps(result.to_mapping(), allow_nan=False)


def test_type_a_mean_uses_student_t_interval() -> None:
    estimates = (9.0, 10.0, 11.0, 12.0)

    result = evaluate_type_a(estimates, unit="V", independent=True)

    expected_standard = 1.2909944487358056 / math.sqrt(4.0)
    expected_factor = float(t.ppf(0.975, df=3))
    assert result.standard_uncertainty == pytest.approx(expected_standard)
    assert result.coverage_factor == pytest.approx(expected_factor)
    assert result.interval_low == pytest.approx(10.5 - expected_factor * expected_standard)
    assert result.interval_high == pytest.approx(10.5 + expected_factor * expected_standard)
    assert result.degrees_of_freedom == 3
    assert result.method == "type_a_capture_mean_student_t"


def test_paired_type_a_operates_on_stored_block_differences() -> None:
    result = evaluate_paired_type_a((1.0, 2.0, 3.0), unit="V", independent=True)

    assert result.estimate == pytest.approx(2.0)
    assert result.standard_uncertainty == pytest.approx(1.0 / math.sqrt(3.0))
    assert result.source == "stored_block_differences"


def test_supplied_covariance_matches_analytic_propagation() -> None:
    components = (
        TypeBComponent(
            name="x",
            distribution=NormalDistribution(standard_uncertainty=2.0),
            sensitivity=SensitivityCoefficient(name="dx", value=3.0),
            correlation_group="shared",
        ),
        TypeBComponent(
            name="y",
            distribution=NormalDistribution(standard_uncertainty=4.0),
            sensitivity=SensitivityCoefficient(name="dy", value=-1.0),
            correlation_group="shared",
        ),
    )

    result = evaluate_budget(
        BudgetRequest(
            measurand=Measurand.BAND_POWER,
            estimate=20.0,
            unit="V²",
            components=components,
            required_components=frozenset({"x", "y"}),
            covariance=(CovarianceTerm(left="x", right="y", covariance=3.0),),
        )
    )

    assert result.standard_uncertainty == pytest.approx(math.sqrt(36.0 + 16.0 - 18.0))
    assert result.covariance_included is True


@pytest.mark.parametrize("output", [Measurand.HARMONIC_RATIO, Measurand.THD])
def test_seeded_monte_carlo_ratio_is_deterministic_and_linearizable(output: Measurand) -> None:
    request = RatioRequest(
        measurand=output,
        numerator=2.0,
        denominator=10.0,
        numerator_standard_uncertainty=0.01,
        denominator_standard_uncertainty=0.02,
        output_unit="1",
        method=PropagationMethod.MONTE_CARLO,
        independent_inputs=True,
        monte_carlo=MonteCarloSettings(seed=44117, draw_count=200_000),
    )

    first = evaluate_ratio(request)
    second = evaluate_ratio(request)
    analytic = 0.2 * math.sqrt((0.01 / 2.0) ** 2 + (0.02 / 10.0) ** 2)

    assert first == second
    assert first.standard_uncertainty == pytest.approx(analytic, rel=0.02)
    assert first.monte_carlo_seed == 44117
    assert first.monte_carlo_draw_count == 200_000
    assert first.method == "monte_carlo_ratio_normal_inputs"


def test_seeded_monte_carlo_db_agrees_with_linear_propagation() -> None:
    request = RatioRequest(
        measurand=Measurand.HARMONIC_RATIO,
        numerator=2.0,
        denominator=10.0,
        numerator_standard_uncertainty=0.002,
        denominator_standard_uncertainty=0.005,
        output_unit="dB",
        method=PropagationMethod.MONTE_CARLO,
        independent_inputs=True,
        monte_carlo=MonteCarloSettings(seed=17, draw_count=250_000),
        logarithmic=True,
    )

    result = evaluate_ratio(request)
    analytic = 20.0 / math.log(10.0) * math.sqrt((0.002 / 2.0) ** 2 + (0.005 / 10.0) ** 2)

    assert result.standard_uncertainty == pytest.approx(analytic, rel=0.02)
    assert result.estimate == pytest.approx(20.0 * math.log10(0.2), rel=0.01)


@pytest.mark.parametrize(
    ("budget_request", "reason_code"),
    [
        (
            BudgetRequest(
                measurand=Measurand.BAND_RMS,
                estimate=1.0,
                unit="V",
                components=(),
                required_components=frozenset({"scope_calibration"}),
            ),
            "missing_type_b_component",
        ),
        (
            BudgetRequest(
                measurand=Measurand.BAND_RMS,
                estimate=1.0,
                unit="V",
                components=(
                    TypeBComponent(
                        name="x",
                        distribution=NormalDistribution(standard_uncertainty=1.0),
                        sensitivity=SensitivityCoefficient(name="dx", value=1.0),
                        correlation_group="shared",
                    ),
                    TypeBComponent(
                        name="y",
                        distribution=NormalDistribution(standard_uncertainty=1.0),
                        sensitivity=SensitivityCoefficient(name="dy", value=1.0),
                        correlation_group="shared",
                    ),
                ),
                required_components=frozenset({"x", "y"}),
            ),
            "missing_declared_covariance",
        ),
    ],
)
def test_missing_inputs_withhold_numeric_combined_result(
    budget_request: BudgetRequest,
    reason_code: str,
) -> None:
    mapping = evaluate_budget(budget_request).to_mapping()

    assert mapping["status"] == "withheld"
    assert mapping["reason_code"] == reason_code
    assert "standard_uncertainty" not in mapping
    assert "expanded_uncertainty" not in mapping


def test_unsupported_nonlinear_method_withholds_combined_result() -> None:
    result = evaluate_ratio(
        RatioRequest(
            measurand=Measurand.THD,
            numerator=1.0,
            denominator=2.0,
            numerator_standard_uncertainty=0.1,
            denominator_standard_uncertainty=0.1,
            output_unit="1",
            method=PropagationMethod.UNSUPPORTED_NONLINEAR,
            independent_inputs=True,
        )
    )

    assert result.reason_code == "unsupported_nonlinear_method"
    assert "standard_uncertainty" not in result.to_mapping()


@pytest.mark.parametrize("estimates", [(1.0,), (1.0, 2.0)])
def test_fewer_than_three_captures_refuses_type_a(estimates: tuple[float, ...]) -> None:
    result = evaluate_type_a(estimates, unit="V", independent=True)

    assert result.reason_code == "insufficient_independent_captures"
    assert "standard_uncertainty" not in result.to_mapping()


def test_independence_must_be_declared() -> None:
    result = evaluate_type_a((1.0, 2.0, 3.0), unit="V", independent=False)

    assert result.reason_code == "independence_not_declared"
    assert "standard_uncertainty" not in result.to_mapping()


def test_type_b_independence_must_be_declared() -> None:
    components = (
        TypeBComponent(
            name="x",
            distribution=NormalDistribution(standard_uncertainty=1.0),
            sensitivity=SensitivityCoefficient(name="dx", value=1.0),
        ),
        TypeBComponent(
            name="y",
            distribution=NormalDistribution(standard_uncertainty=1.0),
            sensitivity=SensitivityCoefficient(name="dy", value=1.0),
        ),
    )

    result = evaluate_budget(
        BudgetRequest(
            measurand=Measurand.BAND_RMS,
            estimate=1.0,
            unit="V",
            components=components,
            required_components=frozenset({"x", "y"}),
        )
    )

    assert result.reason_code == "independence_not_declared"
    assert "standard_uncertainty" not in result.to_mapping()


def test_ratio_input_independence_must_be_declared() -> None:
    result = evaluate_ratio(
        RatioRequest(
            measurand=Measurand.HARMONIC_RATIO,
            numerator=1.0,
            denominator=2.0,
            numerator_standard_uncertainty=0.1,
            denominator_standard_uncertainty=0.1,
            output_unit="1",
            method=PropagationMethod.LINEAR,
            independent_inputs=False,
        )
    )

    assert result.reason_code == "independence_not_declared"
    assert "standard_uncertainty" not in result.to_mapping()


def test_single_record_outputs_are_explicitly_not_measurement_uncertainty() -> None:
    result = SingleRecordDescription(
        resolution_hz=50.0,
        bin_width_hz=50.0,
        spectral_variability=0.08,
        spectral_variability_unit="relative_sd",
    )
    mapping = result.to_mapping()

    assert mapping["classification"] == "not_measurement_uncertainty"
    assert mapping["reason_code"] == "single_record_variability_only"
    assert mapping["spectral_variability_label"] == "within_record_spectral_variability"
    assert mapping["spectral_variability_label"] == "within_record_spectral_variability"
    assert mapping["method"] == "welch_resolution_and_within_record_variability"
