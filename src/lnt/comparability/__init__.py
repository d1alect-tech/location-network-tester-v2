"""Публичный v2-контракт сопоставимости, QC и inclusion state."""

from .matrix import TYPE_MATRIX, assess_pair
from .models import (
    AdcSetup,
    CalibrationIdentity,
    ComparabilityBlockedError,
    ComparabilityFinding,
    ComparabilityReport,
    ComparisonKind,
    ContextValue,
    FindingLevel,
    SessionDescriptor,
    SetupKind,
    WelchGrid,
    require_numeric_comparison,
)
from .normalization import (
    NormalizationDecision,
    NormalizationKind,
    NormalizationRequest,
    assess_normalization,
)
from .qc import InclusionState, QcRecommendation, recommend_exclusion
from .state import MemberInclusion, MemberStateStore, StateConflictError, StateRevision

__all__ = [
    "TYPE_MATRIX",
    "AdcSetup",
    "CalibrationIdentity",
    "ComparabilityBlockedError",
    "ComparabilityFinding",
    "ComparabilityReport",
    "ComparisonKind",
    "ContextValue",
    "FindingLevel",
    "InclusionState",
    "MemberInclusion",
    "MemberStateStore",
    "NormalizationDecision",
    "NormalizationKind",
    "NormalizationRequest",
    "QcRecommendation",
    "SessionDescriptor",
    "SetupKind",
    "StateConflictError",
    "StateRevision",
    "WelchGrid",
    "assess_normalization",
    "assess_pair",
    "recommend_exclusion",
    "require_numeric_comparison",
]
