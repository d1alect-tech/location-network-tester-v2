"""Единственная активная фоновая задача панели с версионированными снимками."""

# ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: первые ~4 КБ файла утрачены при сбое диска;
# голова реконструирована по тестам и маршрутам, хвост оригинальный.

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final, assert_never

from lnt.runtime.scheduler import OperationClass, OperationScheduler
from lnt.runtime.store import JobStore
from lnt.ui.job_state import JobSnapshot, advance, new_job
from lnt.ui.job_worker import (
    WorkerCancelled,
    WorkerContext,
    WorkerFailed,
    WorkerSucceeded,
    WorkerUpdate,
    execute_job,
)
from lnt.ui.models import JobKind, JobRequest, JobStage, JobStatus
from lnt.ui.operations import JobBackend

_LOGGER = logging.getLogger(__name__)

_FIRST_STAGES: Final[dict[JobKind, JobStage]] = {
    JobKind.SIMULATE: JobStage.SIMULATING,
    JobKind.CAPTURE: JobStage.CAPTURING,
    JobKind.ANALYZE: JobStage.ANALYZING,
    JobKind.COMPARE: JobStage.COMPARING,
    JobKind.SELFTEST: JobStage.SELFTEST,
    JobKind.DEVICE_CHECK: JobStage.CHECKING_DEVICE,
    JobKind.BACKUP: JobStage.BACKUP,
    JobKind.SUPPORT_BUNDLE: JobStage.SUPPORT_BUNDLE,
}
_HARDWARE_KINDS: Final = frozenset({JobKind.CAPTURE, JobKind.DEVICE_CHECK})


class JobBusyError(Exception):
    """Панель уже выполняет незавершённую задачу."""


class UnknownJobError(Exception):
    """Запрошенная задача не зарегистрирована."""


class JobNotCancellableError(Exception):
    """Задача уже достигла терминального статуса."""


class JobManager:
    """Управляет единственной активной задачей и рассылкой её снимков."""

    def __init__(
        self,
        *,
        backend: JobBackend,
        root: Path,
        store: JobStore,
        scheduler: OperationScheduler | None = None,
    ) -> None:
        """Создаёт менеджер с сериализацией железа и ограниченным CPU-пулом."""
        self._backend: JobBackend = backend
        self._root: Path = root
        self._store: JobStore = store
        self._scheduler: OperationScheduler = scheduler or OperationScheduler()
        self._registry: dict[str, JobSnapshot] = {}
        self._changes: dict[str, asyncio.Event] = {}
        self._cancellations: dict[str, threading.Event] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def start(self, request: JobRequest) -> JobSnapshot:
        """Регистрирует задачу и запускает её в рабочем потоке."""
        async with self._lock:
            snapshot = new_job(JobKind(request.kind))
            operation_class = _operation_class(snapshot.kind)
            self._scheduler.ensure_capacity(operation_class)
            job_id = snapshot.job_id
            self._store.create(snapshot, input_reference=request.model_dump(mode="json"))
            self._registry[job_id] = snapshot
            self._changes[job_id] = asyncio.Event()
            cancellation = threading.Event()
            self._cancellations[job_id] = cancellation
            loop = asyncio.get_running_loop()
            first_stage = _FIRST_STAGES[snapshot.kind]

            def report(update: WorkerUpdate) -> None:
                loop.call_soon_threadsafe(self._apply_update, job_id, update)

            def run() -> None:
                loop.call_soon_threadsafe(self._mark_running, job_id, first_stage)
                outcome = execute_job(
                    WorkerContext(
                        backend=self._backend,
                        root=self._root,
                        is_cancelled=cancellation.is_set,
                        report=report,
                    ),
                    request,
                )
                loop.call_soon_threadsafe(self._apply_outcome, job_id, outcome)

            self._scheduler.submit(operation_class, run)
            return snapshot

    def get(self, job_id: str) -> JobSnapshot:
        """Возвращает текущий снимок или сообщает о неизвестной задаче."""
        snapshot = self._registry.get(job_id)
        if snapshot is None:
            try:
                snapshot = self._store.get(job_id)
            except KeyError as error:
                raise UnknownJobError from error
            self._registry[job_id] = snapshot
            self._changes[job_id] = asyncio.Event()
        return snapshot

    def cancel(self, job_id: str) -> JobSnapshot:
        """Запрашивает отмену незавершённой задачи на ближайшей границе серии."""
        snapshot = self.get(job_id)
        if snapshot.is_terminal():
            raise JobNotCancellableError
        self._cancellations[job_id].set()
        cancelling = advance(snapshot, status=JobStatus.CANCELLING)
        self._publish(job_id, cancelling)
        return cancelling

    def list(self, *, page_size: int, offset: int = 0) -> tuple[JobSnapshot, ...]:
        """Возвращает страницу durable задач, включая прошлые запуски."""
        return self._store.list_snapshots(page_size=page_size, offset=offset)

    def history(
        self,
        job_id: str,
        *,
        page_size: int,
        after_version: int = 0,
    ) -> tuple[JobSnapshot, ...]:
        """Возвращает durable прогресс после указанной версии."""
        snapshots = self._store.event_snapshots(
            job_id,
            page_size=page_size,
            after_version=after_version,
        )
        if not snapshots and after_version == 0:
            self.get(job_id)
        return snapshots

    async def snapshots(self, job_id: str) -> AsyncIterator[JobSnapshot]:
        """Публикует только новые версии снимков вплоть до терминальной.

        Все читатели используют одно событие, но каждый хранит свою версию.
        Событие очищается до синхронной повторной проверки реестра, поэтому
        объединённые сигналы и очистка другим читателем не теряют изменения.
        """
        change = self._changes.get(job_id)
        if change is None:
            self.get(job_id)
            change = self._changes[job_id]
        last_version = 0
        while True:
            change.clear()
            snapshot = self.get(job_id)
            if snapshot.version > last_version:
                last_version = snapshot.version
                yield snapshot
                if snapshot.is_terminal():
                    return
                continue
            await change.wait()

    async def aclose(self) -> None:
        """Запрашивает отмену активной задачи и без блокировки осушает executor."""
        for snapshot in tuple(self._registry.values()):
            if not snapshot.is_terminal():
                self.cancel(snapshot.job_id)
        await asyncio.to_thread(self._scheduler.close)

    def _publish(self, job_id: str, snapshot: JobSnapshot) -> None:
        self._store.record(snapshot)
        self._registry[job_id] = snapshot
        self._changes[job_id].set()

    def _mark_running(self, job_id: str, stage: JobStage) -> None:
        snapshot = self._registry[job_id]
        status = snapshot.status
        match status:
            case JobStatus.QUEUED:
                self._publish(
                    job_id,
                    advance(snapshot, status=JobStatus.RUNNING, stage=stage),
                )
                return
            case JobStatus.RUNNING | JobStatus.CANCELLING:
                return
            case (
                JobStatus.SUCCEEDED | JobStatus.CANCELLED | JobStatus.FAILED | JobStatus.INTERRUPTED
            ):
                _LOGGER.debug(
                    "Запуск завершённой задачи отброшен",
                    extra={"job_id": job_id},
                )
                return
        assert_never(status)

    def _apply_update(self, job_id: str, update: WorkerUpdate) -> None:
        snapshot = self._registry[job_id]
        if snapshot.is_terminal():
            _LOGGER.debug(
                "Обновление завершённой задачи отброшено",
                extra={"job_id": job_id},
            )
            return
        status = JobStatus.RUNNING if snapshot.status is JobStatus.QUEUED else None
        self._publish(
            job_id,
            advance(
                snapshot,
                status=status,
                stage=update.stage,
                series_index=update.series_index,
                series_total=update.series_total,
                add_session=update.written_session,
            ),
        )

    def _apply_outcome(
        self,
        job_id: str,
        outcome: WorkerSucceeded | WorkerCancelled | WorkerFailed,
    ) -> None:
        snapshot = self._registry[job_id]
        if snapshot.is_terminal():
            _LOGGER.debug(
                "Повторный результат завершённой задачи отброшен",
                extra={"job_id": job_id},
            )
            return
        match outcome:
            case WorkerSucceeded(result=result):
                self._finish(
                    job_id,
                    advance(
                        snapshot,
                        status=JobStatus.SUCCEEDED,
                        stage=JobStage.DONE,
                        result=result,
                    ),
                )
                return
            case WorkerCancelled():
                self._finish(
                    job_id,
                    advance(snapshot, status=JobStatus.CANCELLED, stage=JobStage.DONE),
                )
                return
            case WorkerFailed(error_code=error_code, error_message=error_message):
                self._finish(
                    job_id,
                    advance(
                        snapshot,
                        status=JobStatus.FAILED,
                        stage=JobStage.DONE,
                        error_code=error_code,
                        error_message=error_message,
                    ),
                )
                return
        assert_never(outcome)

    def _finish(self, job_id: str, terminal: JobSnapshot) -> None:
        self._publish(job_id, terminal)


def _operation_class(kind: JobKind) -> OperationClass:
    return OperationClass.HARDWARE if kind in _HARDWARE_KINDS else OperationClass.CPU
