"""Синхронное выполнение задач панели с типизированным результатом."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, assert_never

from lnt.compare import comparison_to_payload
from lnt.errors import AnalysisError, DeviceNotFoundError, InputError
from lnt.scope_io import CancellationToken, CancelledResult
from lnt.series import run_series, series_dirs
from lnt.ui.models import (
    AnalyzeRequest,
    BackupRequest,
    CaptureRequest,
    CompareRequest,
    DeviceCheckRequest,
    JobRequest,
    JobStage,
    SelftestRequest,
    SimulateRequest,
    SupportBundleRequest,
)
from lnt.ui.sessions import allocate_output_base, resolve_session_dir

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from lnt.types import SeriesPosition
    from lnt.ui.analysis_v2_wire import BranchFailureRecord
    from lnt.ui.operations import JobBackend

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerContext:
    """Зависимости одного синхронного запуска задачи."""

    backend: JobBackend
    root: Path
    is_cancelled: Callable[[], bool]
    report: Callable[[WorkerUpdate], None]


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerUpdate:
    """Изменение этапа или запись очередной сессии."""

    stage: JobStage
    series_index: int | None = None
    series_total: int | None = None
    written_session: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerSucceeded:
    """Успешный результат задачи панели."""

    result: Mapping[str, object]


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerCancelled:
    """Задача остановлена на границе элементов серии."""


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerFailed:
    """Безопасное представление ошибки задачи для панели."""

    error_code: str
    error_message: str


type WorkerResult = WorkerSucceeded | WorkerCancelled | WorkerFailed


class _Cancelled(Exception):  # noqa: N818 - внутренний сигнал, не публичная ошибка
    """Внутренний сигнал отмены между элементами серии."""


def execute_job(context: WorkerContext, request: JobRequest) -> WorkerResult:
    """Выполняет запрос и переводит исключения в типизированный результат.

    Отмена действует только на границах серии. Если флаг выставлен во время
    последней сессии, полностью дописанная и проанализированная серия успешна.
    """
    try:
        return _dispatch(context, request)
    except (InputError, AnalysisError) as exc:
        return WorkerFailed(error_code="input_error", error_message=str(exc))
    except DeviceNotFoundError as exc:
        return WorkerFailed(error_code="device_not_found", error_message=str(exc))
    except _Cancelled:
        return WorkerCancelled()
    except Exception:
        _LOGGER.exception("Необработанная ошибка выполнения задачи панели")
        return WorkerFailed(error_code="internal_error", error_message="внутренняя ошибка")


def _dispatch(  # noqa: PLR0911 - по одному return на kind задачи панели
    context: WorkerContext, request: JobRequest
) -> WorkerSucceeded:
    match request:
        case SimulateRequest() | CaptureRequest():
            return _execute_series(context, request)
        case AnalyzeRequest(session_name=session_name):
            session_dir = resolve_session_dir(context.root, session_name)
            context.report(WorkerUpdate(stage=JobStage.ANALYZING))
            analyzed = context.backend.analyze_and_write(session_dir)
            return WorkerSucceeded(
                result={
                    "sessions": [session_name],
                    "branch_failures": analyzed.branch_failures,
                },
            )
        case CompareRequest(session_a=session_a, session_b=session_b):
            dir_a = resolve_session_dir(context.root, session_a)
            dir_b = resolve_session_dir(context.root, session_b)
            context.report(WorkerUpdate(stage=JobStage.COMPARING))
            comparison = context.backend.compare(dir_a, dir_b)
            return WorkerSucceeded(result=comparison_to_payload(comparison))
        case SelftestRequest():
            context.report(WorkerUpdate(stage=JobStage.SELFTEST))
            result = context.backend.selftest()
            return WorkerSucceeded(
                result={
                    "ok": result.ok,
                    "message": result.message,
                    "frequency_hz": result.frequency_hz,
                    "cycles_analyzed": result.cycles_analyzed,
                },
            )
        case BackupRequest():
            context.report(WorkerUpdate(stage=JobStage.BACKUP))
            archived = context.backend.backup(context.root)
            return WorkerSucceeded(
                result={
                    "archive": archived.path.name,
                    "entry_count": archived.entry_count,
                },
            )
        case SupportBundleRequest():
            context.report(WorkerUpdate(stage=JobStage.SUPPORT_BUNDLE))
            bundle = context.backend.support_bundle()
            return WorkerSucceeded(
                result={
                    "bundle": bundle.path.name,
                    "members": list(bundle.member_names),
                },
            )
        case DeviceCheckRequest():
            context.report(WorkerUpdate(stage=JobStage.CHECKING_DEVICE))
            status = context.backend.device_check()
            return WorkerSucceeded(
                result={
                    "driver_installed": status.driver_installed,
                    "device_opened": status.device_opened,
                    "firmware_present": status.firmware_present,
                    "error_message": status.error_message,
                    "hints": list(status.hints),
                },
            )
    assert_never(request)


def _execute_series(
    context: WorkerContext,
    request: SimulateRequest | CaptureRequest,
) -> WorkerSucceeded:
    """Запускает серию симуляции или захвата с анализом каждого результата."""
    kind, profile, stage = _series_settings(request)
    base = allocate_output_base(
        context.root,
        requested=request.output_name,
        kind=kind,
        profile=profile,
        repeat=request.repeat,
    )
    dirs = series_dirs(base, request.repeat)
    branch_failures: list[BranchFailureRecord] = []

    def start_session(position: SeriesPosition) -> Path:
        if context.is_cancelled():
            raise _Cancelled
        context.report(
            WorkerUpdate(
                stage=stage,
                series_index=position.index,
                series_total=position.total,
            ),
        )
        series = position if request.repeat > 1 else None
        match request:
            case SimulateRequest():
                path = context.backend.simulate_one(
                    request,
                    dirs[position.index - 1],
                    series,
                )
                context.report(
                    WorkerUpdate(
                        stage=stage,
                        series_index=position.index,
                        series_total=position.total,
                        written_session=path.name,
                    ),
                )
                context.report(
                    WorkerUpdate(
                        stage=JobStage.ANALYZING,
                        series_index=position.index,
                        series_total=position.total,
                    ),
                )
                analyzed = context.backend.analyze_and_write(path)
                branch_failures.extend(analyzed.branch_failures)
                return path
            case CaptureRequest():
                path = context.backend.capture_one(
                    request,
                    dirs[position.index - 1],
                    series,
                    CancellationToken(context.is_cancelled),
                )
                if isinstance(path, CancelledResult):
                    raise _Cancelled
                context.report(
                    WorkerUpdate(
                        stage=stage,
                        series_index=position.index,
                        series_total=position.total,
                        written_session=path.name,
                    ),
                )
                context.report(
                    WorkerUpdate(
                        stage=JobStage.ANALYZING,
                        series_index=position.index,
                        series_total=position.total,
                    ),
                )
                analyzed = context.backend.analyze_and_write(path)
                branch_failures.extend(analyzed.branch_failures)
                return path
        assert_never(request)

    written = run_series(
        repeat=request.repeat,
        interval_s=request.interval_s,
        start_session=start_session,
    )
    return WorkerSucceeded(
        result={
            "sessions": [path.name for path in written],
            "branch_failures": tuple(branch_failures),
        },
    )


def _series_settings(
    request: SimulateRequest | CaptureRequest,
) -> tuple[str, str | None, JobStage]:
    match request:
        case SimulateRequest(profile=profile):
            return "simulate", profile, JobStage.SIMULATING
        case CaptureRequest():
            return "capture", None, JobStage.CAPTURING
    assert_never(request)
