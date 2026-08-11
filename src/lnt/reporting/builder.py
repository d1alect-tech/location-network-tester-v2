"""Чистая композиция typed scientific results в report schema 1."""

from lnt.reporting.models import (
    EstimandResult,
    IntervalModel,
    Limitation,
    PlaneReport,
    QcDecision,
    QcState,
    ReportInputs,
    ReportSchema1,
    ResultMetadataModel,
)
from lnt.statistics.models import DescriptiveEffect, InferentialEffect


def _estimand(result: InferentialEffect | DescriptiveEffect) -> EstimandResult:
    metadata = ResultMetadataModel(
        sampling_unit=result.metadata.sampling_unit,
        hierarchy=result.metadata.hierarchy,
        n=result.metadata.n,
        missing_count=result.metadata.missing_count,
        exclusions=tuple(
            QcDecision(
                member_id=item.member_id,
                state=QcState.EXCLUDED,
                reason=item.reason,
            )
            for item in result.metadata.exclusions
        ),
        estimator_name=result.metadata.estimator_name,
        interval_method=result.metadata.interval_method,
    )
    match result:
        case InferentialEffect(interval=interval):
            return EstimandResult(
                result_kind="inferential",
                mean_effect=result.mean_effect,
                median_effect=result.median_effect,
                robust_effect=result.robust_effect,
                interval=IntervalModel(
                    low=interval.low,
                    high=interval.high,
                    confidence_level=interval.confidence_level,
                ),
                stored_differences=result.stored_differences,
                metadata=metadata,
            )
        case DescriptiveEffect():
            return EstimandResult(
                result_kind="descriptive",
                mean_effect=result.mean_effect,
                median_effect=result.median_effect,
                robust_effect=result.robust_effect,
                interval=None,
                stored_differences=result.stored_differences,
                metadata=metadata,
            )


def build_report(inputs: ReportInputs) -> ReportSchema1:
    """Собирает report без файловой системы и скрытых вычислений."""
    limitations = [
        Limitation(code="protocol_qualification", detail=detail, source="protocol")
        for detail in inputs.protocol_qualifications
    ]
    limitations.extend(
        Limitation(
            code="artifact_missing",
            detail=f"Артефакт недоступен: {artifact}",
            source="automatic",
        )
        for artifact in inputs.missing_artifacts
    )
    limitations.extend(
        Limitation(
            code=plane.reason_code or "plane_unavailable",
            detail=f"Плоскость {plane.kind.value} недоступна: {plane.reason_code}",
            source="automatic",
        )
        for plane in inputs.planes
        if not plane.available
    )
    planes = tuple(
        PlaneReport(
            kind=plane.kind,
            available=plane.available,
            reason_code=plane.reason_code,
            session_id=plane.session_id,
            member_id=plane.member_id,
            unit=plane.unit,
            estimator=plane.estimator,
            n=plane.n,
            values=tuple(_estimand(value) for value in plane.values),
        )
        for plane in inputs.planes
    )
    return ReportSchema1(
        provenance=inputs.provenance,
        setup_context=inputs.setup,
        qc_exclusions=inputs.qc,
        recipes_used=inputs.recipes,
        primary_estimands=tuple(_estimand(item) for item in inputs.primary_estimands),
        secondary_estimands=tuple(_estimand(item) for item in inputs.secondary_estimands),
        planes=planes,
        drift_confounds=inputs.drift_confounds,
        events_summary=inputs.events,
        limitations=tuple(limitations),
        linked_hypotheses=inputs.hypotheses,
    )
