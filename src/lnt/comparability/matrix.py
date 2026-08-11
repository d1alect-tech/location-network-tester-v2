"""Причинно-кодированная матрица сопоставимости сессий."""

from typing import Final

from lnt.acquisition_quality import QualityCode

from .models import (
    ComparabilityFinding,
    ComparabilityReport,
    ComparisonKind,
    FindingLevel,
    SessionDescriptor,
)

TYPE_MATRIX: Final = {
    left: {right: left is right for right in ComparisonKind} for left in ComparisonKind
}
_BLOCKING_QUALITY: Final = frozenset(
    {
        QualityCode.CLIPPING,
        QualityCode.CALLBACK_GAP,
        QualityCode.SHORT_BLOCK,
        QualityCode.INCOMPLETE_CAPTURE,
    }
)


def _finding(
    dimension: str,
    code: str,
    fields: tuple[str, ...],
    *,
    matched: bool,
    mismatch_level: FindingLevel = FindingLevel.BLOCK,
) -> ComparabilityFinding:
    return ComparabilityFinding(
        dimension=dimension,
        level=FindingLevel.OK if matched else mismatch_level,
        code=f"{dimension}_ok" if matched else code,
        fields=fields,
    )


def _context_findings(
    left: SessionDescriptor, right: SessionDescriptor
) -> tuple[ComparabilityFinding, ...]:
    left_values = {item.field: item.value for item in left.context_fields if item.comparable}
    right_values = {item.field: item.value for item in right.context_fields if item.comparable}
    fields = tuple(
        f"context_fields.{name}" for name in sorted(set(left_values) | set(right_values))
    )
    return (
        _finding("context", "context_field_mismatch", fields, matched=left_values == right_values),
    )


def _quality_findings(
    left: SessionDescriptor, right: SessionDescriptor
) -> tuple[ComparabilityFinding, ...]:
    codes = {finding.code for item in (left, right) for finding in item.quality.findings}
    blocked = bool(codes & _BLOCKING_QUALITY)
    warning = QualityCode.UNDER_RANGE in codes
    if blocked:
        level = FindingLevel.BLOCK
        code = "acquisition_quality_unqualified"
    elif warning:
        level = FindingLevel.WARNING
        code = "acquisition_quality_under_range"
    else:
        level = FindingLevel.OK
        code = "quality_ok"
    return (
        ComparabilityFinding(
            dimension="quality",
            level=level,
            code=code,
            fields=("quality.findings",),
        ),
    )


def _changed_fields(*checks: tuple[bool, str]) -> tuple[str, ...]:
    return tuple(field for matched, field in checks if not matched)


def assess_pair(left: SessionDescriptor, right: SessionDescriptor) -> ComparabilityReport:
    """Оценивает каждое научное измерение и сохраняет все причины."""
    checks: tuple[ComparabilityFinding, ...] = (
        _finding(
            "comparison_kind",
            "comparison_kind_mismatch",
            ("comparison_kind",),
            matched=TYPE_MATRIX[left.comparison_kind][right.comparison_kind],
        ),
        _finding(
            "session_type",
            "session_type_mismatch",
            ("session_type",),
            matched=left.session_type is right.session_type,
        ),
        _finding(
            "channel_mode",
            "channel_mode_mismatch",
            ("channel_mode",),
            matched=left.channel_mode is right.channel_mode,
        ),
        _finding(
            "setup",
            "setup_kind_mismatch",
            ("setup_kind",),
            matched=left.setup_kind is right.setup_kind,
        ),
        _finding(
            "probe",
            "probe_multiplier_mismatch",
            ("probe_multiplier",),
            matched=left.probe_multiplier == right.probe_multiplier,
        ),
        _finding(
            "adc_range",
            "adc_range_mismatch",
            _changed_fields(
                (left.adc_setup.range_code == right.adc_setup.range_code, "adc_setup.range_code"),
                (left.adc_setup.range_v == right.adc_setup.range_v, "adc_setup.range_v"),
            ),
            matched=left.adc_setup == right.adc_setup,
        ),
        _finding(
            "sample_rate",
            "sample_rate_mismatch",
            ("sample_rate_hz",),
            matched=left.sample_rate_hz == right.sample_rate_hz,
        ),
        _finding(
            "recipe",
            "recipe_identity_mismatch",
            ("recipe_identity",),
            matched=left.recipe_identity == right.recipe_identity,
        ),
        _finding(
            "grid",
            "welch_grid_mismatch",
            ("grid.window", "grid.nperseg", "grid.noverlap"),
            matched=left.grid == right.grid,
        ),
        _finding(
            "baseline",
            "baseline_identity_mismatch",
            ("baseline_identity",),
            matched=left.baseline_identity == right.baseline_identity,
        ),
        _finding(
            "calibration",
            "calibration_identity_mismatch",
            _changed_fields(
                (left.calibration.identity == right.calibration.identity, "calibration.identity"),
                (left.calibration.applied == right.calibration.applied, "calibration.applied"),
            ),
            matched=left.calibration == right.calibration,
        ),
    )
    return ComparabilityReport(
        findings=checks + _quality_findings(left, right) + _context_findings(left, right)
    )
