"""Durable progress snapshots for analysis job API runs."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 - runtime store path type


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisJob:
    """Durable analysis progress snapshot."""

    job_id: str
    status: str
    stage: str
    completed: int
    total: int
    artifact_key: str | None = None
    error: str | None = None

    def payload(self) -> dict[str, str | int | None]:
        """Return a JSON-compatible API payload."""
        return {
            "job_id": self.job_id,
            "kind": "analyze",
            "status": self.status,
            "stage": self.stage,
            "completed": self.completed,
            "total": self.total,
            "artifact_key": self.artifact_key,
            "error": self.error,
        }


class AnalysisJobStore:
    """Persists every progress transition with atomic replace."""

    def __init__(self, root: Path) -> None:
        """Bind the store to one directory."""
        self._root: Path = root

    def create(self) -> AnalysisJob:
        """Create and persist a running analysis job."""
        job = AnalysisJob(
            job_id=uuid.uuid4().hex,
            status="running",
            stage="queued",
            completed=0,
            total=0,
        )
        self.write(job)
        return job

    def get(self, job_id: str) -> AnalysisJob:
        """Load the latest persisted snapshot."""
        payload = json.loads((self._root / f"{job_id}.json").read_text(encoding="utf-8"))
        return AnalysisJob(
            job_id=str(payload["job_id"]),
            status=str(payload["status"]),
            stage=str(payload["stage"]),
            completed=int(payload["completed"]),
            total=int(payload["total"]),
            artifact_key=None if payload["artifact_key"] is None else str(payload["artifact_key"]),
            error=None if payload["error"] is None else str(payload["error"]),
        )

    def write(self, job: AnalysisJob) -> None:
        """Atomically persist one progress transition."""
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{job.job_id}.json"
        temporary = path.with_name(f".{path.name}.partial-{uuid.uuid4().hex}")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(job.payload(), stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)  # noqa: PTH105 - explicit atomic seam
        finally:
            temporary.unlink(missing_ok=True)
