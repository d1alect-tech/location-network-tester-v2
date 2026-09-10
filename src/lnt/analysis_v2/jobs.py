"""Durable progress snapshots for analysis job API runs."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 - runtime store path type

from lnt.safe_paths import is_linked_path

_JOB_ID_LENGTH = 32


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
        self._validate_root()
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
        self._validate_id(job_id)
        self._validate_root()
        path = self._root / f"{job_id}.json"
        if is_linked_path(path):
            raise OSError("файл задачи анализа не должен быть ссылкой")
        payload = json.loads(path.read_text(encoding="utf-8"))
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
        self._validate_id(job.job_id)
        self._validate_root()
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{job.job_id}.json"
        if is_linked_path(path):
            raise OSError("файл задачи анализа не должен быть ссылкой")
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

    def _validate_root(self) -> None:
        if is_linked_path(self._root) or is_linked_path(self._root.parent):
            raise OSError("каталог задач анализа не должен быть ссылкой")

    @staticmethod
    def _validate_id(job_id: str) -> None:
        if len(job_id) != _JOB_ID_LENGTH or any(char not in "0123456789abcdef" for char in job_id):
            raise ValueError("job_id должен быть lowercase UUID hex")
