"""Канонический JSON renderer report schema 1."""

import json

from lnt.reporting.models import ReportSchema1


def canonical_json(report: ReportSchema1) -> bytes:
    """Возвращает sorted UTF-8 JSON с единственной конечной новой строкой."""
    payload = report.model_dump(mode="json")
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (text + "\n").encode()
