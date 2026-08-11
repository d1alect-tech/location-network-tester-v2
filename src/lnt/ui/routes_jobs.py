"""HTTP-маршруты жизненного цикла фоновых задач панели."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from lnt.runtime.scheduler import AnalysisQueueFullError
from lnt.ui.dependencies import (
    AppServices,
    get_services,
    map_domain_error,
    require_csrf,
)
from lnt.ui.jobs import JobBusyError, JobNotCancellableError, UnknownJobError
from lnt.ui.models import JobRequest

router = APIRouter(prefix="/api")
_Services = Annotated[AppServices, Depends(get_services)]


def _require_known_job(job_id: str, services: _Services) -> None:
    """Проверяет существование задачи до отправки заголовков SSE."""
    try:
        services.jobs.get(job_id)
    except UnknownJobError as error:
        raise map_domain_error(error) from error


@router.post(
    "/jobs",
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_job(request: JobRequest, services: _Services) -> JSONResponse:
    """Запускает единственную фоновую задачу и возвращает первый снимок."""
    try:
        snapshot = await services.jobs.start(request)
    except (JobBusyError, AnalysisQueueFullError) as error:
        raise map_domain_error(error) from error
    return JSONResponse(snapshot.to_payload(), status_code=status.HTTP_202_ACCEPTED)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, services: _Services) -> JSONResponse:
    """Возвращает текущий снимок задачи."""
    try:
        snapshot = services.jobs.get(job_id)
    except UnknownJobError as error:
        raise map_domain_error(error) from error
    return JSONResponse(snapshot.to_payload())


@router.post(
    "/jobs/{job_id}/cancel",
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_job(job_id: str, services: _Services) -> JSONResponse:
    """Запрашивает отмену незавершённой задачи."""
    try:
        snapshot = services.jobs.cancel(job_id)
    except (UnknownJobError, JobNotCancellableError) as error:
        raise map_domain_error(error) from error
    return JSONResponse(snapshot.to_payload(), status_code=status.HTTP_202_ACCEPTED)


@router.get(
    "/jobs/{job_id}/events",
    dependencies=[Depends(_require_known_job)],
    response_class=EventSourceResponse,
)
async def stream_job_events(
    job_id: str,
    services: _Services,
) -> AsyncIterator[ServerSentEvent]:
    """Передаёт версионированные снимки задачи до терминального состояния."""
    async for snapshot in services.jobs.snapshots(job_id):
        yield ServerSentEvent(
            event="snapshot",
            id=str(snapshot.version),
            retry=1000,
            data=snapshot.to_payload(),
        )
