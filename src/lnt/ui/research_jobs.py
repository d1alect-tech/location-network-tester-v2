"""Durable CPU jobs for bounded research calculations."""
# ruff: noqa: TC001

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import Lock
from typing import Final

from lnt.runtime.scheduler import OperationClass, OperationScheduler
from lnt.runtime.store import JobStore
from lnt.ui.job_state import JobSnapshot, advance, new_job
from lnt.ui.models import JobKind, JobStage, JobStatus

ResearchResult = Mapping[str, object]


class ResearchJobService:
    """Owns durable snapshots and a bounded CPU scheduler."""

    def __init__(self, store: JobStore) -> None:
        """Bind the service to one durable runtime store."""
        self._store: Final = store
        self._scheduler: Final = OperationScheduler(cpu_workers=2, cpu_queue_limit=2)
        self._lock: Final = Lock()

    def submit(
        self,
        input_reference: Mapping[str, object],
        calculate: Callable[[str], ResearchResult],
    ) -> JobSnapshot:
        """Persist queued work before submitting it to the CPU class."""
        self._scheduler.ensure_capacity(OperationClass.CPU)
        snapshot = new_job(JobKind.ANALYZE)
        self._store.create(snapshot, input_reference=input_reference)

        def run() -> None:
            with self._lock:
                current = self._store.get(snapshot.job_id)
                self._store.record(
                    advance(current, status=JobStatus.RUNNING, stage=JobStage.ANALYZING)
                )
            try:
                result = calculate(snapshot.job_id)
            except (ArithmeticError, ValueError) as error:
                with self._lock:
                    current = self._store.get(snapshot.job_id)
                    self._store.record(
                        advance(
                            current,
                            status=JobStatus.FAILED,
                            stage=JobStage.DONE,
                            error_code="statistics_calculation_failed",
                            error_message=f"статистический расчёт завершился ошибкой: {error}",
                        )
                    )
                return
            with self._lock:
                current = self._store.get(snapshot.job_id)
                self._store.record(
                    advance(current, status=JobStatus.SUCCEEDED, stage=JobStage.DONE, result=result)
                )

        self._scheduler.submit(OperationClass.CPU, run)
        return snapshot

    def get(self, job_id: str) -> JobSnapshot:
        """Load the latest durable research job snapshot."""
        return self._store.get(job_id)

    def close(self) -> None:
        """Drain CPU workers during application shutdown."""
        self._scheduler.close()
