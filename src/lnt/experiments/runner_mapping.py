"""Маппинг preflight-находок между runtime- и persistable-формами."""

from __future__ import annotations

from lnt.capture_preflight import FindingSeverity, PreflightFinding
from lnt.experiments.runner_models import FindingRecord


def _finding(source: PreflightFinding) -> FindingRecord:
    return FindingRecord(
        severity=source.severity.value,
        code=source.code,
        message_ru=source.message_ru,
        recovery_action_ru=source.recovery_action_ru,
    )


def _preflight(source: FindingRecord) -> PreflightFinding:
    return PreflightFinding(
        severity=FindingSeverity(source.severity),
        code=source.code,
        message_ru=source.message_ru,
        recovery_action_ru=source.recovery_action_ru,
    )


__all__ = [
    "_finding",
    "_preflight",
]
