from dataclasses import replace

import pytest

from lnt.acquisition_quality import AcquisitionQuality, QualityCode, QualityFinding
from lnt.comparability import (
    AdcSetup,
    CalibrationIdentity,
    ComparisonKind,
    ContextValue,
    NormalizationDecision,
    NormalizationKind,
    NormalizationRequest,
    SessionDescriptor,
    SetupKind,
    WelchGrid,
    assess_normalization,
    assess_pair,
    require_numeric_comparison,
)
from lnt.types import ChannelMode, SessionType

KINDS = tuple(ComparisonKind)


def _descriptor(kind: ComparisonKind) -> SessionDescriptor:
    base = SessionDescriptor(
        session_id=kind.value,
        comparison_kind=ComparisonKind.RC_2CH,
        session_type=SessionType.MEASUREMENT,
        channel_mode=ChannelMode.DUAL,
        setup_kind=SetupKind.FLOATING_DIFFERENTIAL_RC_SHUNT_V1,
        probe_multiplier=1.0,
        adc_setup=AdcSetup(range_code=5, range_v=5.0),
        sample_rate_hz=20_000_000.0,
        recipe_identity="welch-v2",
        grid=WelchGrid(window="hann", nperseg=4096, noverlap=2048),
        baseline_identity="baseline-a",
        calibration=CalibrationIdentity(identity="adc-a", applied=False),
        quality=AcquisitionQuality(
            quality_thresholds_version=1,
            channels=(),
            findings=(),
            maximum_callback_gap_s=0.0,
            short_block_count=0,
        ),
        context_fields=(ContextValue(field="site_id", value="lab-a", comparable=True),),
    )
    match kind:
        case ComparisonKind.LEGACY:
            return replace(
                base,
                comparison_kind=kind,
                setup_kind=SetupKind.LEGACY_MISSING,
            )
        case ComparisonKind.RC_1CH:
            return replace(
                base,
                comparison_kind=kind,
                channel_mode=ChannelMode.CH1_ONLY,
            )
        case ComparisonKind.RC_2CH:
            return base
        case ComparisonKind.SELF_NOISE:
            return replace(
                base,
                comparison_kind=kind,
                session_type=SessionType.SELF_NOISE,
                channel_mode=ChannelMode.CH1_ONLY,
                setup_kind=SetupKind.SCOPE_INPUT_TERMINATED_V1,
            )
        case ComparisonKind.LINE_QUALITY:
            return replace(
                base,
                comparison_kind=kind,
                session_type=SessionType.LINE_QUALITY,
                channel_mode=ChannelMode.CH1_ONLY,
                setup_kind=SetupKind.TRANSFORMER_LINE_PROBE_V1,
            )


@pytest.mark.parametrize(("left_kind", "right_kind"), [(a, b) for a in KINDS for b in KINDS])
def test_full_session_kind_matrix_blocks_every_mixed_pair(
    left_kind: ComparisonKind,
    right_kind: ComparisonKind,
) -> None:
    report = assess_pair(_descriptor(left_kind), _descriptor(right_kind))

    assert report.comparable is (left_kind is right_kind)
    assert (
        "comparison_kind" in {field for finding in report.blocks for field in finding.fields}
    ) is (left_kind is not right_kind)


@pytest.mark.parametrize(
    ("change", "code", "field"),
    [
        ({"probe_multiplier": 10.0}, "probe_multiplier_mismatch", "probe_multiplier"),
        (
            {"adc_setup": AdcSetup(range_code=1, range_v=5.0)},
            "adc_range_mismatch",
            "adc_setup.range_code",
        ),
        ({"sample_rate_hz": 10_000_000.0}, "sample_rate_mismatch", "sample_rate_hz"),
        ({"recipe_identity": "other"}, "recipe_identity_mismatch", "recipe_identity"),
        ({"baseline_identity": "other"}, "baseline_identity_mismatch", "baseline_identity"),
        (
            {"calibration": CalibrationIdentity(identity="other", applied=False)},
            "calibration_identity_mismatch",
            "calibration.identity",
        ),
        (
            {"context_fields": (ContextValue(field="site_id", value="lab-b", comparable=True),)},
            "context_field_mismatch",
            "context_fields.site_id",
        ),
    ],
)
def test_each_strict_dimension_reports_exact_field(
    change: dict[str, object], code: str, field: str
) -> None:
    left = _descriptor(ComparisonKind.RC_2CH)

    report = assess_pair(left, replace(left, session_id="right", **change))

    finding = next(item for item in report.blocks if item.code == code)
    assert finding.fields == (field,)


def test_clipped_capture_blocks_numeric_comparison() -> None:
    left = _descriptor(ComparisonKind.RC_2CH)
    clipped = replace(
        left.quality,
        findings=(
            QualityFinding(
                code=QualityCode.CLIPPING,
                channel="ch1",
                message_ru="Клиппинг.",
                recovery_action_ru="Повторите захват вручную.",
            ),
        ),
    )
    report = assess_pair(left, replace(left, session_id="clipped", quality=clipped))

    assert report.comparable is False
    assert next(
        item for item in report.blocks if item.code == "acquisition_quality_unqualified"
    ).fields == ("quality.findings",)
    with pytest.raises(ValueError, match="сравнение заблокировано"):
        require_numeric_comparison(report)


def test_psd_grid_decimation_is_permitted_and_arbitrary_resample_is_not() -> None:
    source = WelchGrid(window="hann", nperseg=4096, noverlap=2048)
    target = WelchGrid(window="hann", nperseg=2048, noverlap=1024)

    permitted = assess_normalization(
        NormalizationRequest(
            kind=NormalizationKind.PSD_GRID_DECIMATION,
            source_grid=source,
            target_grid=target,
            sample_rate_hz=20_000_000.0,
        )
    )
    arbitrary = assess_normalization(
        NormalizationRequest(
            kind=NormalizationKind.ARBITRARY_RESAMPLE,
            source_grid=source,
            target_grid=target,
            sample_rate_hz=20_000_000.0,
        )
    )

    assert permitted.permitted is True
    assert permitted.rule_id == "psd_welch_nperseg_decimation_v1"
    assert arbitrary.permitted is False
    assert arbitrary.reason_code == "normalization_not_whitelisted"


def _decimation_request(
    factor: int | None, source_hz: float | None, target_hz: float | None
) -> NormalizationRequest:
    grid = WelchGrid(window="hann", nperseg=4096, noverlap=2048)
    return NormalizationRequest(
        kind=NormalizationKind.BICOHERENCE_DECIMATION,
        source_grid=grid,
        target_grid=grid,
        sample_rate_hz=20_000_000.0,
        analysis_factor=factor,
        source_analysis_rate_hz=source_hz,
        target_analysis_rate_hz=target_hz,
    )


def test_exact_integer_analysis_decimation_is_the_second_permitted_normalization() -> None:
    """Целочисленное приведение к частоте анализа разрешено и названо своим rule_id."""
    permitted = assess_normalization(_decimation_request(8, 8_000_000.0, 1_000_000.0))

    assert permitted.permitted is True
    assert permitted.rule_id == "bicoherence_analysis_rate_decimation_v1"
    assert permitted.reason_code == "permitted"


def test_non_integer_analysis_ratio_is_refused_instead_of_resampled() -> None:
    """1.5 МГц -> 1 МГц это отношение 1.5: объявить его целым фактором нельзя."""
    fractional = assess_normalization(_decimation_request(1, 1_500_000.0, 1_000_000.0))
    rounded = assess_normalization(_decimation_request(2, 1_500_000.0, 1_000_000.0))
    undeclared = assess_normalization(_decimation_request(None, None, None))
    zero = assess_normalization(_decimation_request(0, 1_000_000.0, 1_000_000.0))

    for refused in (fractional, rounded, undeclared, zero):
        assert refused.permitted is False
        assert refused.rule_id is None
        assert refused.reason_code == "normalization_not_whitelisted"


def test_every_normalization_kind_returns_a_decision() -> None:
    """Член enum без case-arm молча вернул бы None: у match нет wildcard."""
    grid = WelchGrid(window="hann", nperseg=4096, noverlap=2048)

    for kind in NormalizationKind:
        decision = assess_normalization(
            NormalizationRequest(
                kind=kind,
                source_grid=grid,
                target_grid=grid,
                sample_rate_hz=8_000_000.0,
                analysis_factor=8,
                source_analysis_rate_hz=8_000_000.0,
                target_analysis_rate_hz=1_000_000.0,
            )
        )
        assert isinstance(decision, NormalizationDecision)
