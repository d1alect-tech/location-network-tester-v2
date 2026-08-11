"""QC-рекомендации без автоматического изменения inclusion state."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from lnt.acquisition_quality import AcquisitionQuality, QualityCode
from lnt.capture_preflight import FindingSeverity, PreflightFinding


class InclusionState(StrEnum):
    """Явное состояние члена сравнения или эксперимента."""

    PROPOSED = "proposed"
    INCLUDED = "included"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True, kw_only=True)
class QcRecommendation:
    """Рекомендация оператору, не являющаяся командой изменения."""

    member_id: str
    recommended_state: InclusionState
    reason_code: str
    fields: tuple[str, ...]


_EXCLUSION_CODES: Final = frozenset(
    {
        QualityCode.CLIPPING,
        QualityCode.CALLBACK_GAP,
        QualityCode.SHORT_BLOCK,
        QualityCode.INCOMPLETE_CAPTURE,
    }
)


def recommend_exclusion(
    *,
    member_id: str,
    quality: AcquisitionQuality,
    preflight_findings: tuple[PreflightFinding, ...],
) -> tuple[QcRecommendation, ...]:
    """Только рекомендует exclusion по blocking QC/preflight findings."""
    quality_recommendations = tuple(
        QcRecommendation(
            member_id=member_id,
            recommended_state=InclusionState.EXCLUDED,
            reason_code=f"qc_{finding.code.value}",
            fields=("quality.findings",),
        )
        for finding in quality.findings
        if finding.code in _EXCLUSION_CODES
    )
    preflight_recommendations = tuple(
        QcRecommendation(
            member_id=member_id,
            recommended_state=InclusionState.EXCLUDED,
            reason_code=f"preflight_{finding.code}",
            fields=("preflight_findings",),
        )
        for finding in preflight_findings
        if finding.severity is FindingSeverity.BLOCK
    )
    return quality_recommendations + preflight_recommendations
