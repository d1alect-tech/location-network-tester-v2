"""HTTP-маршруты живого режима: SSE-кадры, POST-управление, статус владения.

Единственный владелец прибора — ``LiveCaptureGate`` из ``AppServices.instrument``
(регистрирует и освобождает его lifespan ``create_app``): маршруты не держат
состояния и не кэшируют статус, а читают сервис на каждый запрос. Контур кадра
крутит SSE-генератор — ``InstrumentService.poll`` обязанность владельца потока, —
и уводит опрос в рабочий поток (``asyncio.to_thread``, паттерн ``ui/jobs.py``),
чтобы блокирующий вызов драйвера (до 250 мс) не останавливал цикл событий и
``POST /api/live/stop`` проходил во время стрима. В поток не поднимается ни одно
исключение: отказ прибора завершает стрим (остаток очереди отдаётся), а неверный
nonce и отсутствие владельца отклоняются ДО отправки заголовков SSE. Nonce —
только на POST: браузерный ``EventSource`` заголовки не отправляет.

SA-контур (``instrument/sa``) кормится гейтом (одно кольцо на захват), а здесь
пересчитывается на каждый ОПУБЛИКОВАННЫЙ свип и уходит отдельным событием
``spectrum`` сразу за кадром того же свипа; события собирает ``ui/live_events``.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from lnt.errors import LntError
from lnt.instrument.live_gate import LiveCaptureGate
from lnt.ui.dependencies import (
    AppServices,
    get_services,
    http_conflict,
    map_domain_error,
    require_csrf,
)
from lnt.ui.live_events import Pacer, frame_event, heartbeat_event, spectrum_event
from lnt.ui.models_live import (
    LIVE_ALREADY_RUNNING_RU,
    LIVE_NOT_RUNNING_RU,
    LIVE_UNAVAILABLE_RU,
    MAX_FRAME_POINTS,
    LiveConfigModel,
    LiveStartRequest,
    LiveStatePayload,
    state_payload,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from lnt.instrument.frames import LiveFrame
    from lnt.instrument.sa import SaEngine
    from lnt.instrument.service import InstrumentService

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Паузы контура: опрос прибора и ожидание старта, на который подписчик не опоздал.
POLL_INTERVAL_S: Final = 0.005
IDLE_POLL_INTERVAL_S: Final = 0.05
# Display-темп кадров: 30 к/с достаточно для развёртки, кадр — до 8000 точек.
DEFAULT_MIN_INTERVAL_S: Final = 1.0 / 30.0

_Services = Annotated[AppServices, Depends(get_services)]


def _require_owner(services: _Services) -> LiveCaptureGate:
    """Отдаёт единственного владельца live или 503 — до заголовков ответа."""
    gate = services.instrument
    if gate is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=LIVE_UNAVAILABLE_RU,
        )
    return gate


_Owner = Annotated[LiveCaptureGate, Depends(_require_owner)]
_MaxPoints = Annotated[int, Query(ge=4, le=MAX_FRAME_POINTS)]
_MinIntervalS = Annotated[float, Query(ge=0.0, le=1.0)]


def _state_response(gate: LiveCaptureGate) -> JSONResponse:
    """Ответ управления и статуса: снимок сервиса, а не его копия в панели."""
    payload: LiveStatePayload = state_payload(gate.service, mode=gate.mode)
    return JSONResponse(payload.model_dump(mode="json"))


@router.post("/live/start", dependencies=[Depends(require_csrf)])
def live_start(body: LiveStartRequest, gate: _Owner) -> JSONResponse:
    """Берёт прибор: preflight-гейт, затем непрерывный захват; повторно — 409."""
    if gate.is_active:
        raise http_conflict(LIVE_ALREADY_RUNNING_RU)
    try:
        gate.start(body.to_start_config())
    except LntError as error:
        raise map_domain_error(error) from error
    return _state_response(gate)


@router.post("/live/stop", dependencies=[Depends(require_csrf)])
def live_stop(gate: _Owner) -> JSONResponse:
    """Освобождает прибор: финальный кадр, затем ``close_handle``; идемпотентно."""
    gate.stop()
    return _state_response(gate)


@router.post("/live/config", dependencies=[Depends(require_csrf)])
def live_config(body: LiveConfigModel, gate: _Owner) -> JSONResponse:
    """Меняет триггер и SA-контур на ходу: захват не перезапускается, буфер не мотается."""
    service = gate.service
    if service is None or not service.is_running:
        raise http_conflict(LIVE_NOT_RUNNING_RU)
    try:
        service.update_trigger(body.to_config())
        # «sa» в теле — только явное поле: scope-only посты SA-контур не трогают,
        # явный null выключает (см. LiveConfigModel).
        if "sa" in body.model_fields_set:
            gate.spectrum.configure(
                body.sa.to_sa_config() if body.sa is not None else None,
                sample_rate_hz=service.sample_rate_hz,
            )
    except LntError as error:
        raise map_domain_error(error) from error
    return _state_response(gate)


@router.get("/live/state")
def live_state(gate: _Owner) -> JSONResponse:
    """Статус владения: ``state`` и ``mode`` — два явных поля, без догадок."""
    return _state_response(gate)


@router.get(
    "/live/frames",
    dependencies=[Depends(_require_owner)],
    response_class=EventSourceResponse,
)
async def live_frames(
    gate: _Owner,
    max_points: _MaxPoints = MAX_FRAME_POINTS,
    min_interval_s: _MinIntervalS = DEFAULT_MIN_INTERVAL_S,
) -> AsyncIterator[ServerSentEvent]:
    """Кадры и трассы SA событиями ``frame``/``spectrum``/``heartbeat``.

    Подписка до старта разрешена: пока захвата нет, подписчик получает
    heartbeat и ждёт, а после ``POST /api/live/start`` тот же стрим отдаёт
    кадры. Переход idle→running при ОТКРЫТОЙ подписке сопровождается
    событием состояния (heartbeat с текущим статусом) ДО кадров: run-кластер
    полосы красит пару из onState и без события остаётся на idle до
    перестройки вкладки (QA round4, задача 21, находка F1).
    """
    announced_running = gate.service is not None and gate.service.is_running
    pacer = Pacer(gate=gate, min_interval_s=min_interval_s)
    yield heartbeat_event(gate)
    # Анонс коннекта мог уйти до старта: переход idle→running, увиденный
    # этим стримом, повторяется событием состояния тем же форматом
    # (heartbeat) ДО кадров — потребитель onState не остаётся на idle.
    while True:
        service = gate.service
        if service is None or not service.is_running:
            if (beat := pacer.heartbeat_due()) is not None:
                yield beat
            await asyncio.sleep(IDLE_POLL_INTERVAL_S)
            continue
        if not announced_running:
            announced_running = True
            yield heartbeat_event(gate)
        # Очередь ограничена: наполняет её только наш ``poll`` (плюс один
        # финальный кадр из ``stop``), а вычитывает тот же генератор — роста
        # без потребителя здесь нет.
        queue: deque[LiveFrame] = deque()
        detach: Callable[[], None] = service.subscribe(queue.append)
        try:
            async for event in _pump(
                service,
                queue,
                pacer,
                gate.spectrum,
                max_points=max_points,
            ):
                yield event
        finally:
            detach()
        return


async def _pump(
    service: InstrumentService,
    queue: deque[LiveFrame],
    pacer: Pacer,
    spectrum: SaEngine,
    *,
    max_points: int,
) -> AsyncIterator[ServerSentEvent]:
    """Контур владельца: ``poll`` в рабочем потоке, кадры и трассы SA до остановки."""
    calibration_used = service.calibration_used
    while service.is_running:
        try:
            # Опрос драйвера блокирует до 250 мс: уводим в рабочий поток, чтобы
            # POST /api/live/stop проходил во время стрима (паттерн ui/jobs.py).
            await asyncio.to_thread(service.poll)
        except LntError as error:
            # Стрим не роняем: остаток очереди уходит ниже. Лог — только если
            # прибор действительно отказал (гонку с обычным stop не шумим).
            if service.is_running:
                _LOGGER.warning("живой поток остановлен ошибкой опроса: %s", error)
            break
        emitted = False
        async for event in _paced_events(
            queue,
            pacer,
            spectrum,
            max_points=max_points,
            calibration_used=calibration_used,
        ):
            emitted = True
            yield event
        if not emitted:
            if (beat := pacer.heartbeat_due()) is not None:
                yield beat
            await asyncio.sleep(POLL_INTERVAL_S)
    # Остаток очереди — финальный кадр контракта ``stop``: темп его не задерживает.
    async for event in _final_events(
        queue,
        pacer,
        spectrum,
        max_points=max_points,
        calibration_used=calibration_used,
    ):
        yield event


async def _paced_events(
    queue: deque[LiveFrame],
    pacer: Pacer,
    spectrum: SaEngine,
    *,
    max_points: int,
    calibration_used: bool,
) -> AsyncIterator[ServerSentEvent]:
    """Кадры очереди в темпе панели; за каждым опубликованным — трасса SA."""
    while queue:
        frame = queue.popleft()
        event = pacer.paced_frame(
            frame,
            max_points=max_points,
            calibration_used=calibration_used,
        )
        if event is None:
            continue
        yield event
        if (trace := spectrum_event(spectrum, frame)) is not None:
            yield trace


async def _final_events(
    queue: deque[LiveFrame],
    pacer: Pacer,
    spectrum: SaEngine,
    *,
    max_points: int,
    calibration_used: bool,
) -> AsyncIterator[ServerSentEvent]:
    """Хвост остановки: финальные кадры без темпа, каждый со своей трассой SA."""
    while queue:
        frame = queue.popleft()
        yield frame_event(
            frame,
            max_points=max_points,
            calibration_used=calibration_used,
            skipped_frames=pacer.take_skipped(),
        )
        if (trace := spectrum_event(spectrum, frame)) is not None:
            yield trace
