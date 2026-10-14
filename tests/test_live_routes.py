"""Live-маршруты панели: SSE-кадры, POST-управление с nonce, статус владения.

Стенд без железа, потоков и ``sleep``: прибор — ``FakeHantekScope``, время —
``ManualClock`` (кадры ставятся одним присваиванием, как в ``test_live_gate``),
а SSE читается блокирующим ``TestClient.stream``: тест ждёт событие из потока, а
не таймер. Дедлайн ``DEADLINE_S`` превращает зависание стрима в падение, а не в
вечно зелёный прогон. Панель минимальна — ``install_services`` плюс
``routes_live.router`` без ``LocalSecurityMiddleware``, поэтому 403 проверяет
сама dependency маршрута (``require_csrf`` → ``secrets.compare_digest``), а
единственный владелец live приходит в ``AppServices.instrument``: очередь 6
регистрирует его в ``create_app`` тем же полем.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.testclient import TestClient

from lnt.capture_preflight import BaselineCompatibility, CaptureEnvironment
from lnt.device_diagnostics import DeviceState
from lnt.instrument import (
    FakeHantekScope,
    InstrumentState,
    LiveCaptureGate,
    LiveMode,
    LiveStartConfig,
    ManualClock,
    TriggerConfig,
    TriggerMode,
    TriggerSlope,
    TriggerSource,
)
from lnt.instrument.frames import DEFAULT_FRAME_SAMPLES
from lnt.instrument.live_gate import LIVE_BUSY_MESSAGE_RU
from lnt.runtime.store import JobStore
from lnt.scope_io import BLOCK_SAMPLES_PER_CHANNEL
from lnt.ui import routes_live
from lnt.ui.dependencies import AppServices, install_services
from lnt.ui.jobs import JobManager
from lnt.ui.models_live import (
    LIVE_ALREADY_RUNNING_RU,
    LIVE_NOT_RUNNING_RU,
    LIVE_UNAVAILABLE_RU,
    MAX_FRAME_POINTS,
    LiveFramePayload,
    LiveStatePayload,
    LiveTriggerModel,
)
from lnt.ui.operations import LntBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path

    from fastapi.sse import ServerSentEvent
    from httpx2 import Response

    from lnt.scope_io import ScopeProtocol

# Тот же детерминированный стенд, что в test_live_gate: 1 МГц (код 1), профиль
# «bad», порог 4.9 В выше сети (±3 В) и в окне триггера — недостижим.
RATE_HZ: Final = 1_000_000.0
CADENCE_S: Final = BLOCK_SAMPLES_PER_CHANNEL / RATE_HZ
PROFILE: Final = "bad"
SEED: Final = 2026
NEVER_CROSS_V: Final = 4.9
HUGE_FREE_BYTES: Final = 10**12
# Вольты после масштаба АЦП ограничены диапазоном +-5 В (raw uint8 был бы 0..255).
VOLTS_BOUND: Final = 5.2
DEADLINE_S: Final = 30.0
EVENT_LIMIT: Final = 60
# Ограниченные ожидания фонового остановки и завершения его потока.
FRAME_WAIT_S: Final = 20.0
JOIN_TIMEOUT_S: Final = 20.0
FRAMES_QUERY: Final = "?min_interval_s=0"
START_BODY: Final[dict[str, object]] = {
    "sample_rate_hz": RATE_HZ,
    "ch1_range_v": 5.0,
    "ch1_probe_multiplier": 1.0,
    "trigger": {
        "level_v": NEVER_CROSS_V,
        "slope": "rising",
        "source": "ch2",
        "mode": "auto",
        "auto_timeout_s": CADENCE_S,
    },
}
TRIGGER_BODY: Final[dict[str, object]] = {
    "level_v": 0.25,
    "slope": "falling",
    "source": "ch2",
    "mode": "normal",
    "auto_timeout_s": 0.5,
}


@dataclass(slots=True)
class _Factory:
    """Инжектируемая фабрика прибора: отдаёт один фейк и считает вызовы."""

    scope: FakeHantekScope
    calls: int = 0

    def __call__(self) -> ScopeProtocol:
        self.calls += 1
        return self.scope


@dataclass(slots=True)
class _Environment:
    """Инжектируемая проба среды; блокирующий статус устройства ломает старт."""

    device_state: DeviceState = DeviceState.READY
    calls: int = 0

    def probe(self) -> CaptureEnvironment:
        self.calls += 1
        return CaptureEnvironment(
            device_state=self.device_state,
            free_bytes=HUGE_FREE_BYTES,
            root_writable=True,
            baseline_compatibility=BaselineCompatibility.NOT_REQUESTED,
        )


@dataclass(slots=True)
class SseEvent:
    """Разобранное событие SSE: имя, JSON-данные, id и retry."""

    name: str
    data: dict[str, object]
    event_id: str | None = None
    retry: int | None = None


@dataclass(slots=True)
class Rig:
    """Панель живого режима: фейк-прибор, инжектируемые часы, nonce запуска."""

    app: FastAPI
    gate: LiveCaptureGate
    scope: FakeHantekScope
    clock: ManualClock
    factory: _Factory
    nonce: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-LNT-Mutation-Nonce": self.nonce}

    def advance(self, blocks: int) -> None:
        """Ставит часы на ``blocks`` кадров прибора (без sleep)."""
        self.clock.now_s = blocks * self.scope.expected_block_interval_s

    def start(self, client: TestClient) -> Response:
        return client.post("/api/live/start", headers=self.headers, json=START_BODY)

    def stop(self, client: TestClient) -> Response:
        return client.post("/api/live/stop", headers=self.headers, json={})


def start_config() -> LiveStartConfig:
    """Доменный эквивалент ``START_BODY`` для старта мимо HTTP."""
    return LiveStartConfig(
        trigger=TriggerConfig(
            level_v=NEVER_CROSS_V,
            slope=TriggerSlope.RISING,
            source=TriggerSource.CH2,
            mode=TriggerMode.AUTO,
            auto_timeout_s=CADENCE_S,
        ),
        sample_rate_hz=RATE_HZ,
        ch1_range_v=5.0,
        ch1_probe_multiplier=1.0,
    )


def gate_with(
    tmp_path: Path,
    *,
    device_state: DeviceState = DeviceState.READY,
    mode: LiveMode = LiveMode.SIM,
) -> tuple[LiveCaptureGate, FakeHantekScope, ManualClock, _Factory]:
    clock = ManualClock()
    scope = FakeHantekScope(
        profile=PROFILE,
        seed=SEED,
        sample_rate_hz=RATE_HZ,
        clock=clock,
        buffer_blocks=8,
    )
    factory = _Factory(scope=scope)
    gate = LiveCaptureGate(
        scope_factory=factory,
        environment_probe=_Environment(device_state=device_state).probe,
        session_root=tmp_path / "sessions",
        clock=clock,
        discard_lead_samples=0,
        mode=mode,
    )
    return gate, scope, clock, factory


def panel(gate: LiveCaptureGate | None, tmp_path: Path) -> FastAPI:
    """Минимальная панель: сервисы приложения и маршруты живого режима."""
    root = tmp_path / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    runtime_db = tmp_path / "runtime.sqlite3"
    app = FastAPI()
    install_services(
        app,
        AppServices(
            root=root,
            catalog_db=tmp_path / "catalog.sqlite3",
            runtime_db=runtime_db,
            jobs=JobManager(backend=LntBackend(), root=root, store=JobStore(runtime_db)),
            instrument=gate,
        ),
    )
    app.include_router(routes_live.router)
    return app


def sse_events(response: Response, limit: int) -> Iterator[SseEvent]:
    """Разбирает поток SSE до ``limit`` событий; конец тела завершает итератор."""
    name: str | None = None
    data: str | None = None
    event_id: str | None = None
    retry: int | None = None
    deadline = time.monotonic() + DEADLINE_S
    emitted = 0
    for line in response.iter_lines():
        assert time.monotonic() < deadline, "SSE-поток не дал событий до дедлайна"
        if line.startswith(":"):
            continue  # keep-alive комментарий транспорта
        if not line:
            if name is not None and data is not None:
                emitted += 1
                payload: dict[str, object] = json.loads(data)
                yield SseEvent(name=name, data=payload, event_id=event_id, retry=retry)
                if emitted >= limit:
                    return
            name, data, event_id, retry = None, None, None, None
            continue
        field, _, value = line.partition(": ")
        if field == "event":
            name = value
        elif field == "data":
            data = value
        elif field == "id":
            event_id = value
        elif field == "retry":
            retry = int(value)


def steps(values: tuple[float, ...]) -> list[float]:
    return [b - a for a, b in pairwise(values)]


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    gate, scope, clock, factory = gate_with(tmp_path)
    app = panel(gate, tmp_path)
    yield Rig(
        app=app,
        gate=gate,
        scope=scope,
        clock=clock,
        factory=factory,
        nonce=app.state.lnt_security.mutation_nonce,
    )
    gate.stop()


# ---------------------------------------------------------------------------
# nonce-гейт мутаций
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/live/start", "/api/live/stop", "/api/live/config"])
def test_post_without_launch_nonce_is_forbidden(rig: Rig, path: str) -> None:
    with TestClient(rig.app) as client:
        missing = client.post(path, json=START_BODY)
        wrong_headers = {"X-LNT-Mutation-Nonce": "not-the-nonce"}
        wrong = client.post(path, headers=wrong_headers, json=START_BODY)

    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "mutation_nonce_invalid"
    assert wrong.status_code == 403
    assert wrong.json()["detail"]["code"] == "mutation_nonce_invalid"
    # Отказ до всякого действия: прибор не тронут, владение не взято.
    assert rig.factory.calls == 0
    assert rig.gate.is_active is False


def test_nonce_gate_precedes_owner_lookup(tmp_path: Path) -> None:
    app = panel(None, tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/live/start", json=START_BODY)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# статус владения: state и mode — два явных поля
# ---------------------------------------------------------------------------


def test_state_wire_schema_carries_state_and_mode_explicitly(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        idle = client.get("/api/live/state")

    assert idle.status_code == 200
    assert idle.json() == {
        "state": "idle",
        "mode": "sim",
        "busy_reason": None,
        "trigger": None,
    }
    payload = LiveStatePayload.model_validate(idle.json())
    assert payload.state is InstrumentState.IDLE
    assert payload.mode is LiveMode.SIM


def test_real_mode_is_reported_without_hardware_claims(tmp_path: Path) -> None:
    gate, _scope, _clock, _factory = gate_with(tmp_path, mode=LiveMode.REAL)
    app = panel(gate, tmp_path)
    with TestClient(app) as client:
        state = client.get("/api/live/state")

    assert state.json()["mode"] == "real"
    assert state.json()["state"] == "idle"


def test_state_reflects_ownership_of_the_single_service(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        started = rig.start(client)
        active_while_running = rig.gate.is_active
        open_while_running = rig.scope.is_open
        running = client.get("/api/live/state")
        stopped = rig.stop(client)
        active_after_stop = rig.gate.is_active
        open_after_stop = rig.scope.is_open
        after = client.get("/api/live/state")

    assert started.status_code == 200
    assert started.json()["state"] == "running"
    assert running.status_code == 200
    assert running.json()["state"] == "running"
    assert running.json()["mode"] == "sim"
    assert running.json()["busy_reason"] == LIVE_BUSY_MESSAGE_RU
    assert running.json()["trigger"]["level_v"] == NEVER_CROSS_V
    assert active_while_running is True
    assert open_while_running is True

    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"
    assert after.json() == {
        "state": "stopped",
        "mode": "sim",
        "busy_reason": None,
        "trigger": START_BODY["trigger"],
    }
    assert active_after_stop is False
    assert open_after_stop is False


def test_second_start_while_running_is_conflict(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        second = rig.start(client)
        rig.stop(client)
        third = rig.start(client)

    assert second.status_code == 409
    assert second.json()["detail"] == LIVE_ALREADY_RUNNING_RU
    # Второй ручки во время отказа нет: старт после stop — уже новая.
    assert rig.factory.calls == 2
    assert rig.scope.calls.count("open_handle") == 2
    assert third.status_code == 200


def test_stop_is_idempotent_and_never_conflicts(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        first = rig.stop(client)
        rig.start(client)
        second = rig.stop(client)
        third = rig.stop(client)

    assert (first.status_code, second.status_code, third.status_code) == (200, 200, 200)
    assert first.json()["state"] == "idle"
    assert second.json()["state"] == "stopped"
    assert third.json()["state"] == "stopped"
    assert rig.scope.calls.count("close_handle") == 1


def test_invalid_start_config_is_unprocessable(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        response = client.post(
            "/api/live/start",
            headers=rig.headers,
            json={**START_BODY, "ch1_range_v": 2.5},
        )

    assert response.status_code == 422
    assert rig.gate.is_active is False
    assert rig.factory.calls == 0


def test_preflight_blocker_reaches_the_client_as_422_with_reason(tmp_path: Path) -> None:
    gate, _scope, _clock, factory = gate_with(tmp_path, device_state=DeviceState.HANDLE_BUSY)
    app = panel(gate, tmp_path)
    nonce = app.state.lnt_security.mutation_nonce
    with TestClient(app) as client:
        response = client.post(
            "/api/live/start",
            headers={"X-LNT-Mutation-Nonce": nonce},
            json=START_BODY,
        )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert response.json()["detail"]
    assert gate.is_active is False
    assert factory.calls == 0


def test_start_request_rejects_unknown_fields(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        response = client.post(
            "/api/live/start",
            headers=rig.headers,
            json={**START_BODY, "websocket": True},
        )

    assert response.status_code == 422
    assert rig.gate.is_active is False


# ---------------------------------------------------------------------------
# SSE: кадры, heartbeat, завершение по stop
# ---------------------------------------------------------------------------


def stop_after_first_frame(rig: Rig) -> None:
    """Фон: ждёт первый кадр подпиской на сервис и освобождает прибор.

    ``TestClient`` отдаёт тело ответа только целиком (``portal.call`` возвращается
    после ``more_body=False``), поэтому бесконечный стрим в тесте не прочитать:
    захват останавливает отдельный поток. Ожидание — по событию кадра
    (``Event.wait`` с ограниченным таймаутом), а не по таймеру.
    """
    service = rig.gate.service
    assert service is not None
    first_frame = threading.Event()
    detach = service.subscribe(lambda _frame: first_frame.set())
    try:
        assert first_frame.wait(FRAME_WAIT_S), "кадр живого потока не пришёл до дедлайна"
    finally:
        detach()
    rig.gate.stop()


def read_stream(rig: Rig, client: TestClient, path: str) -> list[SseEvent]:
    """Читает SSE-ответ до конца тела: фон останавливает захват по первому кадру."""
    stopper = threading.Thread(target=stop_after_first_frame, args=(rig,), daemon=True)
    stopper.start()
    try:
        with client.stream("GET", path) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = list(sse_events(response, limit=EVENT_LIMIT))
    finally:
        stopper.join(JOIN_TIMEOUT_S)
    assert not stopper.is_alive(), "поток остановки не завершился"
    return events


def live_stream(gate: LiveCaptureGate) -> AsyncIterator[ServerSentEvent]:
    """SSE-генератор маршрута напрямую: семантика событий без транспорта."""
    return routes_live.live_frames(
        gate=gate,
        max_points=MAX_FRAME_POINTS,
        min_interval_s=0.0,
    )


def collect_events(gate: LiveCaptureGate, count: int) -> list[ServerSentEvent]:
    """Снимает первые ``count`` событий генератора.

    Обрыв на ``count`` оставляет генератор подвешенным, а ``asyncio.run``
    финализирует его через ``shutdown_asyncgens``: подписка снимается в
    ``finally`` маршрута, потоков и ``sleep`` тест не заводит.
    """

    async def scenario() -> list[ServerSentEvent]:
        events: list[ServerSentEvent] = []
        async for event in live_stream(gate):
            events.append(event)
            if len(events) >= count:
                break
        return events

    return asyncio.run(scenario())


def test_frames_stream_delivers_whole_calibrated_frames(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")

    # heartbeat присутствует: первое событие — статус владения, а не тишина.
    assert events[0].name == "heartbeat"
    assert events[0].retry == 1000
    assert events[0].data["state"] == "running"
    assert events[0].data["mode"] == "sim"

    frames = [event for event in events if event.name == "frame"]
    assert len(frames) >= 2
    first = LiveFramePayload.model_validate(frames[0].data)
    second = LiveFramePayload.model_validate(frames[1].data)

    assert frames[0].retry == 1000
    assert frames[0].event_id == str(first.frame_index)
    assert (first.frame_index, second.frame_index) == (0, 1)
    assert first.sample_rate_hz == RATE_HZ
    assert first.frame_samples == DEFAULT_FRAME_SAMPLES
    assert first.triggered is False
    assert first.dropped_samples == 0
    assert first.skipped_frames == 0
    # Провенанс вольт: per-device таблицы в стенде нет — флаг честно False.
    assert first.calibration_used is False
    assert first.emitted_at_s == pytest.approx(2 * CADENCE_S)


def test_frame_channels_are_volts_decimated_to_display_budget(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")

    frames = [event for event in events if event.name == "frame"]
    frame = LiveFramePayload.model_validate(frames[0].data)
    for channel in (frame.ch1, frame.ch2):
        assert channel.point_count <= MAX_FRAME_POINTS
        assert len(channel.time_s) == channel.point_count
        assert len(channel.voltage_v) == channel.point_count
        # Время — секунды от начала окна кадра: t0 = 0, монотонно.
        assert channel.time_s[0] == 0.0
        assert all(step > 0.0 for step in steps(channel.time_s))
        # Вольты, а не raw uint8: масштаб АЦП применён до прореживания.
        assert max(abs(value) for value in channel.voltage_v) < VOLTS_BOUND
    assert frame.decimated is True
    assert frame.frame_samples > MAX_FRAME_POINTS


def test_max_points_budget_is_bounded_by_the_waveform_limit(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}&max_points=64")
        rejected = [client.get(f"/api/live/frames?max_points={n}") for n in (4001, 3, 0)]

    frames = [event for event in events if event.name == "frame"]
    frame = LiveFramePayload.model_validate(frames[0].data)
    assert frame.ch1.point_count <= 64
    assert frame.ch2.point_count <= 64
    assert frame.decimated is True
    assert [response.status_code for response in rejected] == [422, 422, 422]


def test_heartbeat_is_the_first_event_while_idle_but_subscribed(rig: Rig) -> None:
    events = collect_events(rig.gate, count=1)

    assert events[0].event == "heartbeat"
    assert events[0].retry == 1000
    payload: LiveStatePayload = events[0].data
    assert payload.model_dump(mode="json") == {
        "state": "idle",
        "mode": "sim",
        "busy_reason": None,
        "trigger": None,
    }


def test_stream_attaches_to_capture_started_after_subscribe(rig: Rig) -> None:
    attached = False

    async def scenario() -> list[ServerSentEvent]:
        nonlocal attached
        events: list[ServerSentEvent] = []
        async for event in live_stream(rig.gate):
            events.append(event)
            if not attached:
                # Подписка до старта: стрим ждёт захват heartbeat-ом и подхватывает его.
                assert event.event == "heartbeat"
                rig.gate.start(start_config())
                rig.advance(2)
                attached = True
            if len(events) >= 3:
                break
        return events

    events = asyncio.run(scenario())

    assert attached
    assert [event.event for event in events] == ["heartbeat", "frame", "frame"]
    first: LiveFramePayload = events[1].data
    assert first.frame_index == 0
    assert first.sample_rate_hz == RATE_HZ


def test_stop_terminates_the_stream_with_the_final_frame(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")

    # Тело прочитано до конца (``read_stream`` вернулся), а не до лимита событий:
    # остановка завершает стрим, и остаток очереди уходит финальным кадром.
    assert len(events) < EVENT_LIMIT
    assert events[-1].name == "frame"
    final = LiveFramePayload.model_validate(events[-1].data)
    assert final.frame_index > 0
    assert rig.gate.is_active is False
    assert rig.scope.calls[-1] == "close_handle"


# ---------------------------------------------------------------------------
# POST /api/live/config — триггер на ходу
# ---------------------------------------------------------------------------


def test_config_updates_trigger_without_restarting_capture(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        response = client.post("/api/live/config", headers=rig.headers, json=TRIGGER_BODY)
        state = client.get("/api/live/state")

    assert response.status_code == 200
    assert response.json()["trigger"] == TRIGGER_BODY
    assert state.json()["trigger"] == TRIGGER_BODY
    service = rig.gate.service
    assert service is not None
    assert service.trigger.level_v == 0.25
    assert service.trigger.slope is TriggerSlope.FALLING
    assert service.trigger.mode is TriggerMode.NORMAL
    # Захват не перезапускался: ручка и старт — по одному разу.
    assert rig.scope.calls.count("open_handle") == 1
    assert rig.scope.calls.count("start_capture") == 1
    assert rig.gate.is_active is True


def test_config_requires_running_capture(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        idle = client.post("/api/live/config", headers=rig.headers, json=TRIGGER_BODY)
        rig.start(client)
        rig.stop(client)
        stopped = client.post("/api/live/config", headers=rig.headers, json=TRIGGER_BODY)
        invalid = client.post(
            "/api/live/config",
            headers=rig.headers,
            json={**TRIGGER_BODY, "auto_timeout_s": -1.0},
        )

    assert idle.status_code == 409
    assert idle.json()["detail"] == LIVE_NOT_RUNNING_RU
    assert stopped.status_code == 409
    assert invalid.status_code == 422


@pytest.mark.parametrize("level_v", [5.001, -5.001])
def test_out_of_range_trigger_level_is_rejected_with_limits(rig: Rig, level_v: float) -> None:
    start_body = {**START_BODY, "trigger": {**START_BODY["trigger"], "level_v": level_v}}
    with TestClient(rig.app) as client:
        started = client.post("/api/live/start", headers=rig.headers, json=start_body)
        rejected_untouched = (rig.gate.is_active, rig.factory.calls)
        assert rig.start(client).status_code == 200
        configured = client.post(
            "/api/live/config",
            headers=rig.headers,
            json={**TRIGGER_BODY, "level_v": level_v},
        )

    assert started.status_code == 422
    detail = started.json()["detail"]
    # Стиль routes_live: one-line тело с пределами, как у прочих 422 домена.
    assert isinstance(detail, str)
    assert f"уровень {level_v} В" in detail
    assert "−5…+5 В" in detail
    # Отказ до прибора: владение не взято, фабрика не звана.
    assert rejected_untouched == (False, 0)
    # Допустимые значения не задеты: валидный уровень стартует как прежде.
    assert rig.gate.is_active is True
    # Конфиг на ходу: захват жив, чужой уровень не применён.
    assert configured.status_code == 422
    assert configured.json()["detail"] == detail
    service = rig.gate.service
    assert service is not None
    assert service.trigger.level_v == NEVER_CROSS_V
    assert rig.scope.calls.count("open_handle") == 1


@pytest.mark.parametrize("level_v", [-5.0, -4.999, 0.0, 4.999, 5.0])
def test_boundary_trigger_levels_are_accepted_on_config(rig: Rig, level_v: float) -> None:
    body = {**TRIGGER_BODY, "level_v": level_v}
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        response = client.post("/api/live/config", headers=rig.headers, json=body)

    assert response.status_code == 200
    assert response.json()["trigger"] == body


@pytest.mark.parametrize("level_v", [float("inf"), float("nan")])
def test_live_trigger_model_rejects_non_finite_levels(level_v: float) -> None:
    # Инфинити/NaN не выражаются стандартным JSON с клиента: границу
    # конечности запросной модели проверяем на самой модели.
    with pytest.raises(ValidationError):
        LiveTriggerModel.model_validate({"level_v": level_v})


def test_null_trigger_level_is_unprocessable(rig: Rig) -> None:
    body = {**START_BODY, "trigger": {**START_BODY["trigger"], "level_v": None}}
    with TestClient(rig.app) as client:
        response = client.post("/api/live/start", headers=rig.headers, json=body)

    assert response.status_code == 422
    assert rig.gate.is_active is False
    assert rig.factory.calls == 0


def test_absent_trigger_level_keeps_the_zero_default(rig: Rig) -> None:
    # Отсутствующее поле — дефолт 0.0 («не менять»), не отказ: валидное
    # поведение wire-контракта диапазон не трогает.
    body = {**START_BODY, "trigger": {"mode": "auto", "auto_timeout_s": CADENCE_S}}
    with TestClient(rig.app) as client:
        started = client.post("/api/live/start", headers=rig.headers, json=body)

    assert started.status_code == 200
    assert started.json()["trigger"] == {
        "level_v": 0.0,
        "slope": "rising",
        "source": "ch1",
        "mode": "auto",
        "auto_timeout_s": CADENCE_S,
    }


# ---------------------------------------------------------------------------
# граница очереди 6: владелец live не зарегистрирован
# ---------------------------------------------------------------------------


def test_live_routes_are_unavailable_without_registered_owner(tmp_path: Path) -> None:
    app = panel(None, tmp_path)
    nonce = app.state.lnt_security.mutation_nonce
    with TestClient(app) as client:
        state = client.get("/api/live/state")
        frames = client.get("/api/live/frames")
        start = client.post(
            "/api/live/start",
            headers={"X-LNT-Mutation-Nonce": nonce},
            json=START_BODY,
        )

    assert state.status_code == 503
    assert state.json()["detail"] == LIVE_UNAVAILABLE_RU
    # SSE: отказ ДО отправки заголовков потока, иначе клиент висел бы в ожидании.
    assert frames.status_code == 503
    assert start.status_code == 503
