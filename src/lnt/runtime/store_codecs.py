"""Чистые кодеки снимков задач (лист store.py, issue #8)."""

from __future__ import annotations

import json

from lnt.ui.job_state import JobSnapshot
from lnt.ui.models import JobKind, JobStage, JobStatus

__all__ = ["_dump_progress", "_dump_snapshot", "_load_snapshot"]


def _dump_progress(snapshot: JobSnapshot) -> str:
    return json.dumps(
        {
            "stage": snapshot.stage.value,
            "series_index": snapshot.series_index,
            "series_total": snapshot.series_total,
            "written_sessions": list(snapshot.written_sessions),
        },
        ensure_ascii=False,
    )


def _dump_snapshot(snapshot: JobSnapshot) -> str:
    return json.dumps(snapshot.to_payload(), ensure_ascii=False)


def _load_snapshot(raw: str) -> JobSnapshot:
    data = json.loads(raw)
    return JobSnapshot(
        schema_version=int(data["schema_version"]),
        version=int(data["version"]),
        job_id=str(data["job_id"]),
        kind=JobKind(str(data["kind"])),
        status=JobStatus(str(data["status"])),
        stage=JobStage(str(data["stage"])),
        series_index=data["series_index"],
        series_total=data["series_total"],
        written_sessions=tuple(str(item) for item in data["written_sessions"]),
        result=data["result"],
        error_code=data["error_code"],
        error_message=data["error_message"],
    )
