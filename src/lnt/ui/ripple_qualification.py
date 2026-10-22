"""Переквалификация фона ripple при чтении: формат v1 остаётся замороженным.

GET не доверяет сохранённому ``comparison_status="available"``. Те же правила
квалификации, что применяет запись, повторяются по манифестам измерения и
фона и по свидетельствам внутри сайдкара. Ответ 200 может нести производный
статус ``unavailable``; файл ``ripple.json`` не переписывается.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.analysis_v2.ripple_baseline import (
    REASON_HOOKUP,
    REASON_INSTRUMENT_ONLY,
    baseline_identity_reasons,
)
from lnt.analysis_v2.ripple_options import BaselineAttachment
from lnt.types import SessionType

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.context.json_codec import JsonValue
    from lnt.types import SessionManifest

_AVAILABLE: Final = "available"
_UNAVAILABLE: Final = "unavailable"
_TERMINATED_KIND: Final = "scope_input_terminated_v1"


def requalified_payload(
    *,
    payload: dict[str, JsonValue],
    measurement: SessionManifest,
    baseline: SessionManifest,
    measurement_dir: Path,
    baseline_dir: Path,
) -> dict[str, JsonValue] | None:
    """Возвращает payload с производным статусом или None, если доверие подтверждено."""
    raw = payload["baseline"]
    if not isinstance(raw, dict) or raw.get("comparison_status") != _AVAILABLE:
        return None
    reasons = list(
        baseline_identity_reasons(
            measurement=measurement,
            baseline=baseline,
            attachment=_attachment(raw.get("attachment_basis")),
            measurement_dir=measurement_dir,
            baseline_dir=baseline_dir,
        )
    )
    reasons.extend(_artifact_evidence_reasons(raw, measurement))
    if not reasons:
        return None
    updated = dict(payload)
    block = dict(raw)
    block["comparison_status"] = _UNAVAILABLE
    block["reason_codes"] = list(dict.fromkeys(reasons))
    updated["baseline"] = block
    return updated


def _attachment(value: JsonValue | None) -> BaselineAttachment | None:
    """Объявленное условие подключения фона из уже проверенного блока."""
    if isinstance(value, str):
        return BaselineAttachment(value)
    return None


def _artifact_evidence_reasons(
    block: dict[str, JsonValue],
    measurement: SessionManifest,
) -> list[str]:
    """Свидетельства внутри сайдкара: приборный фон и несовпадение канала."""
    reasons: list[str] = []
    if block.get("session_type") == SessionType.SELF_NOISE.value:
        reasons.append(REASON_INSTRUMENT_ONLY)
    setup = block.get("ch1_setup")
    if isinstance(setup, dict) and setup.get("kind") == _TERMINATED_KIND:
        reasons.append(REASON_INSTRUMENT_ONLY)
    role = block.get("channel_role")
    if isinstance(role, str) and role != measurement.ch1.role.value:
        reasons.append(REASON_HOOKUP)
    return reasons
