"""Типы результатов анализа v1 и имена артефактов (C4: выделено из analysis).

Тонкий слой данных без математики: потребители продолжают импортировать
эти имена из ``lnt.analysis`` (фасад реэкспортирует их без изменений).
"""

from dataclasses import dataclass, field

from lnt.input_reference import Ch1InputReference, InputReferenceStatus
from lnt.line_quality import LineQualityMetrics
from lnt.needles import NeedleMetrics
from lnt.spectrum import BandSpectrum
from lnt.types import SessionSource, SessionType

METRICS_FILENAME = "metrics.json"
SPECTRUM_FILENAME = "spectrum.csv"
SPECTRUM_INPUT_REFERRED_FILENAME = "spectrum_input_referred.csv"
ANALYSIS_SCHEMA_VERSION = 2


def legacy_input_reference() -> Ch1InputReference:
    """Создаёт provenance для вручную собранных legacy AnalysisResult в consumers/tests."""
    return Ch1InputReference(
        status=InputReferenceStatus.UNAVAILABLE,
        reason_code="manifest_schema_v1",
        model_kind=None,
        input_referred_excess_psd_v2_per_hz=None,
        qualified=None,
        baseline_session_id=None,
        model=None,
        qualification_rule_id=None,
        qualified_bin_count=0,
        total_bin_count=0,
        corrected_peaks=(),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisResult:
    """Полный результат анализа одной сессии."""

    session_id: str
    profile: str | None
    source: SessionSource
    session_type: SessionType
    sample_rate_hz: float
    duration_s: float
    needle: NeedleMetrics
    spectrum: BandSpectrum
    ch1_input_reference: Ch1InputReference = field(default_factory=legacy_input_reference)


@dataclass(frozen=True, slots=True, kw_only=True)
class LineQualityAnalysis:
    """Результат анализа line-quality сессии (качество сети 50 Гц)."""

    session_id: str
    profile: str | None
    source: SessionSource
    session_type: SessionType
    sample_rate_hz: float
    duration_s: float
    line_quality: LineQualityMetrics


# Совместимость: прежнее приватное имя из ``lnt.analysis``.
_legacy_input_reference = legacy_input_reference
