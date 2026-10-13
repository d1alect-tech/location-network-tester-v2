"""HTTP-маршруты живого режима: SSE-кадры, POST-управление, статус владения.

Единственный владелец прибора — ``LiveCaptureGate`` из ``AppServices.instrument``
(регистрирует и освобождает его lifespan ``create_app``): маршруты не держат
состояния и не кэшируют статус, а читают сервис на каждый запрос. Контур кадра крутит
SSE-генератор — ``InstrumentService.poll`` обязанность владельца потока, — и
уводит опрос в рабочий поток (``asyncio.to_thread``, паттерн ``ui/jobs.py``),
чтобы блокирующий вызов драйвера (до 250 мс) не останавливал цикл событий и
``POST /api/live/stop`` проходил во время стрима. В поток не поднимается ни одно
исключение: отказ прибора завершает стрим (остаток очереди отдаётся), а неверный
nonce и отсутствие владельца отклоняются ДО отправки заголовков SSE. Nonce —
только на POST: браузерный ``EventSource`` заголовки не отправляет.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
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
from lnt.ui.models_live import (
    LIVE_ALREADY_RUNNING_RU,
    LIVE_NOT_RUNNING_RU,
    LIVE_UNAVAILABLE_RU,
    MAX_FRAME_POINTS,
    LiveStartRequest,
    LiveStatePayload,
    LiveTriggerModel,
    frame_payload,
    state_payload,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from lnt.instrument.frames import LiveFrame
    from lnt.instrument.service import InstrumentService

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Паузы контура: опрос прибора, ожидание старта, на который подписчик не опоздал,
# и heartbeat без кадров (подписчик отличает «нет данных» от «поток умер»).
POLL_INTERVAL_S: Final = 0.005
IDLE_POLL_INTERVAL_S: Final = 0.05
HEARTBEAT_INTERVAL_S: Final = 15.0
# Display-темп кадров: 30 к/с достаточно для развёртки, кадр — до 8000 точек.
DEFAULT_MIN_INTERVAL_S: Final = 1.0 / 30.0
RETRY_MS: Final = 1000

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


@dataclass(slots=True)
class _Pacer:
    """Display-темп потока: кадры не чаще ``min_interval_s``, heartbeat — свой.

    Часы — монотонные часы панели, не часы прибора: темп защищает браузер от
    лавины кадров (блок прибора даёт несколько окон сразу), а пропуски уезжают
    в ``skipped_frames`` ближайшего кадра.
    """

    gate: LiveCaptureGate
    min_interval_s: float
    last_event_s: float = field(default_factory=time.monotonic)
    skipped: int = 0

    def frame_event(
        self,
        frame: LiveFrame,
        *,
        max_points: int,
        calibration_used: bool,
    ) -> ServerSentEvent | None:
        """Кадр в темпе панели; вне темпа — ``None`` и счётчик пропуска."""
        now_s = time.monotonic()
        if now_s - self.last_event_s < self.min_interval_s:
            self.skipped += 1
            return None
        return self._taken(
            _frame_event(
                frame,
                max_points=max_points,
                calibration_used=calibration_used,
                skipped_frames=self.take_skipped(),
            ),
            now_s,
        )

    def heartbeat_due(self) -> ServerSentEvent | None:
        """Heartbeat, если событий не было дольше ``HEARTBEAT_INTERVAL_S``."""
        now_s = time.monotonic()
        if now_s - self.last_event_s < HEARTBEAT_INTERVAL_S:
            return None
        return self._taken(_heartbeat_event(self.gate), now_s)

    def take_skipped(self) -> int:
        """Счётчик display-пропусков с обнулением: пропуски не замалчиваются."""
        skipped, self.skipped = self.skipped, 0
        return skipped

    def _taken(self, event: ServerSentEvent, now_s: float) -> ServerSentEvent:
        self.last_event_s = now_s
        self.skipped = 0
        return event


def _frame_event(
    frame: LiveFrame,
    *,
    max_points: int,
    calibration_used: bool,
    skipped_frames: int,
) -> ServerSentEvent:
    """Событие ``frame``: кадр целиком, id — индекс кадра, retry — как у задач."""
    return ServerSentEvent(
        event="frame",
        id=str(frame.frame_index),
        retry=RETRY_MS,
        data=frame_payload(
            frame,
            max_points=max_points,
            calibration_used=calibration_used,
            skipped_frames=skipped_frames,
        ),
    )


def _heartbeat_event(gate: LiveCaptureGate) -> ServerSentEvent:
    """Событие ``heartbeat``: текущий статус владения, а не пустой кадр."""
    return ServerSentEvent(
        event="heartbeat",
        retry=RETRY_MS,
        data=state_payload(gate.service, mode=gate.mode),
    )


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
def live_config(body: LiveTriggerModel, gate: _Owner) -> JSONResponse:
    """Меняет триггер на ходу: захват не перезапускается, буфер не мотается."""
    service = gate.service
    if service is None or not service.is_running:
        raise http_conflict(LIVE_NOT_RUNNING_RU)
    try:
        service.update_trigger(body.to_config())
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
    """Кадры потока событиями ``frame``/``heartbeat``; остановка завершает стрим.

    Подписка до старта разрешена: пока захвата нет, подписчик получает
    heartbeat и ждёт, а после ``POST /api/live/start`` тот же стрим отдаёт кадры.
    """
    pacer = _Pacer(gate=gate, min_interval_s=min_interval_s)
    yield _heartbeat_event(gate)
    while True:
        service = gate.service
        if service is None or not service.is_running:
            if (beat := pacer.heartbeat_due()) is not None:
                yield beat
            await asyncio.sleep(IDLE_POLL_INTERVAL_S)
            continue
        # Очередь ограничена: наполняет её только наш ``poll`` (плюс один
        # финальный кадр из ``stop``), а вычитывает тот же генератор — роста
        # без потребителя здесь нет.
        queue: deque[LiveFrame] = deque()
        detach: Callable[[], None] = service.subscribe(queue.append)
        try:
            async for event in _pump(service, queue, pacer, max_points=max_points):
                yield event
        finally:
            detach()
        return


async def _pump(
    service: InstrumentService,
    queue: deque[LiveFrame],
    pacer: _Pacer,
    *,
    max_points: int,
) -> AsyncIterator[ServerSentEvent]:
    """Контур владельца: ``poll`` в рабочем потоке, кадры и heartbeat до остановки."""
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
        while queue:
            event = pacer.frame_event(
                queue.popleft(),
                max_points=max_points,
                calibration_used=calibration_used,
            )
            if event is not None:
                emitted = True
                yield event
        if not emitted:
            if (beat := pacer.heartbeat_due()) is not None:
                yield beat
            await asyncio.sleep(POLL_INTERVAL_S)
    # Остаток очереди — финальный кадр контракта ``stop``: темп его не задерживает.
    while queue:
        yield _frame_event(
            queue.popleft(),
            max_points=max_points,
            calibration_used=calibration_used,
            skipped_frames=pacer.take_skipped(),
        )
