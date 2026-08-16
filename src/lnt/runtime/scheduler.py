"""Детерминированные очереди аппаратных и CPU-операций."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar, final, override

if TYPE_CHECKING:
    from collections.abc import Callable

ResultT = TypeVar("ResultT")


class OperationClass(StrEnum):
    """Класс ресурса, определяющий очередь операции."""

    HARDWARE = "hardware"
    CPU = "cpu"


@dataclass(frozen=True, slots=True)
class AnalysisQueueFullError(Exception):
    """Ограниченная очередь анализа исчерпана."""

    limit: int
    code: str = "analysis_queue_full"

    @override
    def __str__(self) -> str:
        return f"очередь анализа заполнена: максимум ожидающих задач {self.limit}"


@dataclass(frozen=True, slots=True)
class SeriesResult:
    """Число завершённых членов и подтверждение отмены."""

    completed: int
    cancelled: bool


@dataclass(slots=True)
class _CpuSlot:
    """Освобождает резерв очереди ровно один раз после запуска работы."""

    on_start: Callable[[], None]
    on_finish: Callable[[], None]
    queued: bool

    def start(self) -> None:
        if self.queued:
            self.on_start()
            self.queued = False

    def finish(self) -> None:
        self.on_finish()


@final
class OperationScheduler:
    """Владеет FIFO executor-очередями с разными лимитами ресурсов."""

    def __init__(self, *, cpu_workers: int = 2, cpu_queue_limit: int = 2) -> None:
        """Создаёт однопоточную hardware и ограниченную CPU FIFO-очереди."""
        if cpu_workers < 1 or cpu_queue_limit < 0:
            raise ValueError("лимиты планировщика должны быть неотрицательными")
        self._hardware = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lnt-job-hardware")
        self._cpu = ThreadPoolExecutor(
            max_workers=cpu_workers, thread_name_prefix="lnt-job-analysis"
        )
        self._cpu_workers = cpu_workers
        self._cpu_queue_limit = cpu_queue_limit
        self._cpu_running = 0
        self._cpu_queued = 0
        self._lock = threading.Lock()

    def submit(
        self,
        operation_class: OperationClass,
        operation: Callable[[], ResultT],
    ) -> Future[ResultT]:
        """Ставит операцию в FIFO своего класса или типизированно отклоняет CPU overflow."""
        match operation_class:
            case OperationClass.HARDWARE:
                return self._hardware.submit(operation)
            case OperationClass.CPU:
                return self._submit_cpu(operation)

    def ensure_capacity(self, operation_class: OperationClass) -> None:
        """Отклоняет CPU-операцию до создания её долговечной записи."""
        match operation_class:
            case OperationClass.HARDWARE:
                return
            case OperationClass.CPU:
                with self._lock:
                    if (
                        self._cpu_running >= self._cpu_workers
                        and self._cpu_queued >= self._cpu_queue_limit
                    ):
                        raise AnalysisQueueFullError(self._cpu_queue_limit)

    def _submit_cpu(self, operation: Callable[[], ResultT]) -> Future[ResultT]:
        with self._lock:
            queued = self._cpu_running >= self._cpu_workers
            if queued and self._cpu_queued >= self._cpu_queue_limit:
                raise AnalysisQueueFullError(self._cpu_queue_limit)
            if queued:
                self._cpu_queued += 1
            else:
                self._cpu_running += 1
        slot = _CpuSlot(self._start_queued_cpu, self._finish_cpu, queued)

        def run() -> ResultT:
            slot.start()
            try:
                return operation()
            finally:
                slot.finish()

        try:
            return self._cpu.submit(run)
        except RuntimeError:
            if queued:
                with self._lock:
                    self._cpu_queued -= 1
            else:
                slot.finish()
            raise

    def _start_queued_cpu(self) -> None:
        with self._lock:
            self._cpu_queued -= 1
            self._cpu_running += 1

    def _finish_cpu(self) -> None:
        with self._lock:
            self._cpu_running -= 1

    def close(self) -> None:
        """Дожидается обеих очередей и запрещает новые работы."""
        self._hardware.shutdown(wait=True, cancel_futures=False)
        self._cpu.shutdown(wait=True, cancel_futures=False)


def run_member_series(
    *,
    total: int,
    is_cancelled: Callable[[], bool],
    run_member: Callable[[int, int], None],
) -> SeriesResult:
    """Проверяет отмену только перед следующим членом серии."""
    completed = 0
    for index in range(1, total + 1):
        if is_cancelled():
            return SeriesResult(completed=completed, cancelled=True)
        run_member(index, total)
        completed += 1
    return SeriesResult(completed=completed, cancelled=False)
