from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from lnt.input_reference import correction_for_frequencies
from lnt.input_reference_v2 import (
    BaselinePsd,
    CorrectionRequest,
    GridMismatchError,
    IdentityMismatchError,
    MeasurementPsd,
    RcUncertaintyProfile,
    UnavailableCorrection,
    correct_input_reference,
)
from lnt.spectrum import find_qualified_peaks
from lnt.types import (
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
)
from lnt.uncertainty import NormalDistribution


def _model() -> FloatingDifferentialRcShunt:
    return FloatingDifferentialRcShunt(
        resistance_ohm=100.0,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis=ComponentValuesBasis.NOMINAL,
        reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    )


def _planes(
    measurement_values: tuple[float, ...] = (4e-12, 1.5e-12, 9e-12, 16e-12),
) -> tuple[MeasurementPsd, BaselinePsd]:
    frequencies = np.asarray((10_000.0, 20_000.0, 30_000.0, 40_000.0))
    measurement = MeasurementPsd.create(
        frequencies_hz=frequencies,
        psd_v2_per_hz=np.asarray(measurement_values),
        resolution_hz=10_000.0,
    )
    baseline = BaselinePsd.create(
        frequencies_hz=frequencies,
        psd_v2_per_hz=np.asarray((1e-12, 1e-12, 2e-12, 3e-12)),
        resolution_hz=10_000.0,
    )
    return measurement, baseline


def test_v2_matches_v1_math_qualification_and_disconnected_peak_rules() -> None:
    # Given
    measurement, baseline = _planes()
    model = _model()
    qualified = measurement.psd_v2_per_hz >= 2.0 * baseline.psd_v2_per_hz
    expected = np.full_like(measurement.psd_v2_per_hz, np.nan)
    gains = correction_for_frequencies(model, measurement.frequencies_hz)
    excess = measurement.psd_v2_per_hz - baseline.psd_v2_per_hz
    expected[qualified] = excess[qualified] / gains[qualified] ** 2

    # When
    result = correct_input_reference(
        CorrectionRequest(measurement=measurement, baseline=baseline, model=model)
    )

    # Then
    assert not isinstance(result, UnavailableCorrection)
    np.testing.assert_array_equal(result.qualified, qualified)
    np.testing.assert_allclose(result.corrected_psd_v2_per_hz, expected, equal_nan=True)
    assert result.corrected_peaks == find_qualified_peaks(
        measurement.frequencies_hz, expected, qualified
    )


def test_linearized_rc_uncertainty_matches_analytic_resistance_fixture() -> None:
    # Given
    measurement, baseline = _planes((4e-12, 4e-12, 4e-12, 4e-12))
    model = _model()
    profile = RcUncertaintyProfile(
        resistance=NormalDistribution(standard_uncertainty=1.0),
        c1=NormalDistribution(standard_uncertainty=0.0),
        c2=NormalDistribution(standard_uncertainty=0.0),
        independent_components=True,
    )

    # When
    result = correct_input_reference(
        CorrectionRequest(
            measurement=measurement, baseline=baseline, model=model, uncertainty=profile
        )
    )

    # Then
    assert not isinstance(result, UnavailableCorrection)
    frequency = measurement.frequencies_hz[0]
    excess = measurement.psd_v2_per_hz[0] - baseline.psd_v2_per_hz[0]
    x = 2.0 * np.pi * frequency * model.resistance_ohm * 5e-9
    expected_sigma = abs(-2.0 * excess / (x**2 * model.resistance_ohm))
    assert result.corrected_standard_uncertainty_v2_per_hz is not None
    assert result.corrected_standard_uncertainty_v2_per_hz[0] == pytest.approx(expected_sigma)
    assert result.uncertainty_reason_code is None


def test_tampered_baseline_hash_is_rejected_without_output() -> None:
    # Given
    measurement, baseline = _planes()
    tampered = replace(baseline, identity_sha256="0" * 64)

    # When / Then
    with pytest.raises(IdentityMismatchError) as captured:
        correct_input_reference(
            CorrectionRequest(measurement=measurement, baseline=tampered, model=_model())
        )
    assert captured.value.reason_code == "baseline_identity_hash_mismatch"


def test_sub_2x_bin_is_nan_and_serializes_as_json_null() -> None:
    # Given
    measurement, baseline = _planes()

    # When
    result = correct_input_reference(
        CorrectionRequest(measurement=measurement, baseline=baseline, model=_model())
    )

    # Then
    assert not isinstance(result, UnavailableCorrection)
    assert np.isnan(result.corrected_psd_v2_per_hz[1])
    corrected_payload = result.to_artifact_mapping()["corrected_psd_v2_per_hz"]
    assert isinstance(corrected_payload, list)
    assert corrected_payload[1] is None


def test_mismatched_frequency_grid_is_typed_rejection() -> None:
    # Given
    measurement, baseline = _planes()
    mismatched = BaselinePsd.create(
        frequencies_hz=baseline.frequencies_hz + 1.0,
        psd_v2_per_hz=baseline.psd_v2_per_hz,
        resolution_hz=baseline.resolution_hz,
    )

    # When / Then
    with pytest.raises(GridMismatchError) as captured:
        correct_input_reference(
            CorrectionRequest(measurement=measurement, baseline=mismatched, model=_model())
        )
    assert captured.value.reason_code == "baseline_frequency_grid_mismatch"


@pytest.mark.parametrize(
    ("schema_version", "reason_code"),
    [(1, "manifest_schema_v1"), (2, "measurement_ch1_setup_missing")],
)
def test_legacy_or_missing_setup_is_reason_coded_unavailable(
    schema_version: int,
    reason_code: str,
) -> None:
    # Given
    measurement, baseline = _planes()

    # When
    result = correct_input_reference(
        CorrectionRequest(
            measurement=measurement,
            baseline=baseline,
            model=None,
            manifest_schema_version=schema_version,
        )
    )

    # Then
    assert isinstance(result, UnavailableCorrection)
    assert result.reason_code == reason_code
    assert result.raw_scope_plane_valid is True


def test_missing_uncertainty_components_withhold_numeric_uncertainty() -> None:
    # Given
    measurement, baseline = _planes()

    # When
    result = correct_input_reference(
        CorrectionRequest(measurement=measurement, baseline=baseline, model=_model())
    )

    # Then
    assert not isinstance(result, UnavailableCorrection)
    assert result.corrected_standard_uncertainty_v2_per_hz is None
    assert result.uncertainty_reason_code == "missing_type_b_component"
