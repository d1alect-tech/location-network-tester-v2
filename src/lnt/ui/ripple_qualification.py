"""Переквалификация фона ripple при чтении: формат v1 остаётся замороженным.

GET не доверяет сохранённому ``comparison_status="available"``. Единственный
источник квалификации — хэш-пиннингованные манифесты измерения и фона: правила
применяет общий с записью помощник ``baseline_identity_reasons``. Текстовые
поля артефакта не участвуют. Ответ 200 может нести производный статус
``unavailable``; файл ``ripple.json`` не переписывается.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from lnt.analysis_v2.ripple_baseline import baseline_identity_reasons
from lnt.analysis_v2.ripple_options import BaselineAttachment

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.context.json_codec import JsonValue
    from lnt.types import SessionManifest

_AVAILABLE: Final = "available"
_UNAVAILABLE: Final = "unavailable"


def requalified_payload(
    *,
    payload: dict[str, JsonValue],
    measurement: SessionManifest,
    baseline: SessionManifest,
    measurement_dir: Path,
    baseline_dir: Path,
) -> dict[str, JsonValue] | None:
    """Возвращает payload с производным статусом по манифестам или None.

    None означает, что сохранённое «available» подтверждено.
    """
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
