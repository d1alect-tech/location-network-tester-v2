"""Like-for-like line-quality comparison contracts."""

import numpy as np
import pytest

from lnt.line_quality_compare import (
    LineQualityIncompatibilityError,
    compare_line_quality,
)
from lnt.line_quality_v2 import (
    LineQualityV2,
    TransformerCalibrationProfile,
    WindowScheme,
    compute_line_quality_v2,
)
from lnt.uncertainty import NormalDistribution, SensitivityCoefficient, TypeBComponent

RATE_HZ = 20_000.0


def _result(*, h3: float, profile: TransformerCalibrationProfile | None = None) -> LineQualityV2:
    time = np.arange(round(2.0 * RATE_HZ), dtype=np.float64) / RATE_HZ
    wave = 10.0 * (np.sin(2.0 * np.pi * 50.0 * time) + h3 * np.sin(2.0 * np.pi * 150.0 * time))
    return compute_line_quality_v2(wave.astype(np.float32), sample_rate_hz=RATE_HZ, profile=profile)


def _profile(identity: str) -> TransformerCalibrationProfile:
    return TransformerCalibrationProfile(
        identity=identity,
        ratio=20.0,
        ratio_uncertainty=TypeBComponent(
            name="transformer_ratio",
            distribution=NormalDistribution(standard_uncertainty=0.1),
            sensitivity=SensitivityCoefficient(name="secondary_rms", value=1.0),
        ),
    )


def test_comparison_contains_scalar_and_complete_harmonic_deltas() -> None:
    # Given
    result_a = _result(h3=0.03)
    result_b = _result(h3=0.05)

    # When
    comparison = compare_line_quality(result_a, result_b)

    # Then
    assert comparison.frequency.delta == pytest.approx(0.0, abs=0.02)
    assert comparison.secondary_rms.delta is not None
    assert comparison.thd.delta > 0.0
    assert comparison.crest.delta is not None
    assert comparison.envelope_cv.delta is not None
    assert [item.order for item in comparison.harmonics] == list(range(2, 41))
    assert comparison.harmonics[1].delta_ratio == pytest.approx(0.02, rel=0.1)
    assert all(
        item.status in {"available", "absent_a", "absent_b", "absent_both"}
        for item in comparison.harmonics
    )


def test_incompatible_transformer_profiles_are_typed_rejection() -> None:
    # Given
    result_a = _result(h3=0.03, profile=_profile("transformer-a@1"))
    result_b = _result(h3=0.03, profile=_profile("transformer-b@1"))

    # When/Then
    with pytest.raises(LineQualityIncompatibilityError) as caught:
        compare_line_quality(result_a, result_b)
    assert caught.value.reason_code == "transformer_profile_mismatch"
    assert "профил" in str(caught.value)


def test_incompatible_sample_rate_and_window_scheme_are_rejected() -> None:
    # Given
    result_a = _result(h3=0.03)
    time = np.arange(40_000, dtype=np.float64) / 10_000.0
    result_b = compute_line_quality_v2(
        (10.0 * np.sin(2.0 * np.pi * 50.0 * time)).astype(np.float32),
        sample_rate_hz=10_000.0,
        window_scheme=WindowScheme(duration_s=2.0),
    )

    # When/Then
    with pytest.raises(LineQualityIncompatibilityError) as caught:
        compare_line_quality(result_a, result_b)
    assert caught.value.reason_code == "recipe_mismatch"


def test_cross_type_comparison_is_typed_rejection() -> None:
    # Given
    result = _result(h3=0.03)

    # When/Then
    with pytest.raises(LineQualityIncompatibilityError) as caught:
        compare_line_quality(result, "hf-analysis")
    assert caught.value.reason_code == "session_type_mismatch"
