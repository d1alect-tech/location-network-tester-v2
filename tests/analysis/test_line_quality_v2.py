"""Versioned line-quality monitoring analysis."""

import numpy as np
import pytest
from numpy.typing import NDArray

from lnt.line_quality import compute_line_quality
from lnt.line_quality_v2 import (
    LINE_QUALITY_DISCLAIMER_RU,
    TransformerCalibrationProfile,
    WindowScheme,
    compute_line_quality_v2,
    line_quality_v2_to_payload,
)
from lnt.uncertainty import NormalDistribution, SensitivityCoefficient, TypeBComponent

RATE_HZ = 20_000.0


def _wave(
    *, duration_s: float = 4.0, start_hz: float = 50.0, end_hz: float = 50.0
) -> NDArray[np.float32]:
    samples = round(duration_s * RATE_HZ)
    time = np.arange(samples, dtype=np.float64) / RATE_HZ
    slope = (end_hz - start_hz) / duration_s
    phase = 2.0 * np.pi * (start_hz * time + 0.5 * slope * time**2)
    return (12.0 * (np.sin(phase) + 0.04 * np.sin(3.0 * phase))).astype(np.float32)


def test_v2_retains_legacy_metrics_and_monitoring_label() -> None:
    # Given
    signal = _wave()
    legacy = compute_line_quality(signal, sample_rate_hz=RATE_HZ)

    # When
    result = compute_line_quality_v2(signal, sample_rate_hz=RATE_HZ)
    payload = line_quality_v2_to_payload(result)

    # Then
    assert result.line_quality_version == 2
    assert result.metrics.fundamental_hz == pytest.approx(legacy.fundamental_hz)
    assert result.metrics.fundamental_rms_v == pytest.approx(legacy.fundamental_rms_v)
    assert result.metrics.thd_ratio == pytest.approx(legacy.thd_ratio)
    assert result.metrics.crest_factor == pytest.approx(legacy.crest_factor)
    assert result.metrics.envelope_cv == pytest.approx(legacy.envelope_cv)
    assert payload["disclaimer_ru"] == LINE_QUALITY_DISCLAIMER_RU


def test_frequency_ramp_is_visible_in_explicit_window_intervals() -> None:
    # Given
    signal = _wave(start_hz=49.5, end_hz=50.5)

    # When
    result = compute_line_quality_v2(
        signal,
        sample_rate_hz=RATE_HZ,
        window_scheme=WindowScheme(duration_s=1.0),
    )

    # Then
    assert len(result.windows) == 4
    assert result.frequency_interval.minimum < 49.8
    assert result.frequency_interval.maximum > 50.2
    assert result.frequency_interval.span > 0.7
    assert result.secondary_rms_interval.minimum > 8.0
    assert result.thd_interval.minimum > 0.02


def test_calibrated_ratio_produces_primary_rms_with_type_b_uncertainty() -> None:
    # Given
    profile = TransformerCalibrationProfile(
        identity="lab-transformer@3",
        ratio=20.0,
        ratio_uncertainty=TypeBComponent(
            name="transformer_ratio",
            distribution=NormalDistribution(standard_uncertainty=0.2),
            sensitivity=SensitivityCoefficient(name="secondary_rms", value=1.0),
        ),
    )

    # When
    result = compute_line_quality_v2(_wave(), sample_rate_hz=RATE_HZ, profile=profile)

    # Then
    assert result.primary_rms.status == "available"
    assert result.primary_rms.value_v == pytest.approx(result.metrics.fundamental_rms_v * 20.0)
    assert result.primary_rms.standard_uncertainty_v == pytest.approx(
        result.metrics.fundamental_rms_v * 0.2
    )
    assert result.primary_rms.expanded_uncertainty_v == pytest.approx(
        2.0 * result.metrics.fundamental_rms_v * 0.2
    )


def test_primary_rms_is_withheld_without_calibrated_profile() -> None:
    # When
    result = compute_line_quality_v2(_wave(), sample_rate_hz=RATE_HZ)
    payload = line_quality_v2_to_payload(result)

    # Then
    assert result.primary_rms.status == "withheld"
    assert result.primary_rms.value_v is None
    assert result.primary_rms.reason_code == "transformer_profile_required"
    primary = payload["primary_rms"]
    assert isinstance(primary, dict)
    assert "value_v" not in primary
    assert "standard_uncertainty_v" not in primary
