"""Жизненный цикл сервисов панели: ленивый владелец live и его dispose.

``create_app`` регистрирует ЕДИНСТВЕННОГО владельца живого режима в
``AppServices.instrument`` и передаёт тот же объект гейту job-захвата
(``JobManager(live_ownership=...)``): второго источника владения нет, поэтому
409 «устройство занято вкладкой» и статус ``/api/live/state`` читают одну
правду. Прибор на старте приложения НЕ открывается — ``InstrumentService``
создаёт только ``POST /api/live/start`` (``LiveCaptureGate.start``), а shutdown
lifespan освобождает ручку контрактом ``stop -> финальный кадр -> close_handle``,
в том числе во время активного SSE-стрима: генератор завершается сам, без
обрыва транспорта и без исключений в поток.

Стенд без железа и без ``sleep``: фейк-прибор, ``ManualClock`` и nonce — тот же
риг, что в ``tests/test_live_routes.py`` (импорт, а не копия: одна правда о
стенде). Dispose во время стрима проверяется прямым прогоном lifespan и
SSE-генератора в одном цикле событий; ожидание — по событию кадра
(``asyncio.Event`` + ограниченный ``wait_for``), а не по таймеру.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import pytest
from starlette.testclient import TestClient

from lnt.instrument.live_gate import LIVE_BUSY_MESSAGE_RU
from lnt.ui import routes_live
from lnt.ui.app import create_app
from lnt.ui.models_live import MAX_FRAME_POINTS, LiveFramePayload
from tests.test_live_routes import START_BODY, gate_with, start_config

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from fastapi import FastAPI
    from fastapi.sse import ServerSentEvent

    from lnt.instrument import FakeHantekScope, LiveCaptureGate, ManualClock
    from lnt.ui.dependencies import AppServices

# Ограниченные ожидания события кадра и завершения генератора после dispose.
FRAME_WAIT_S: Final = 20.0
STREAM_END_S: Final = 20.0
CAPTURE_BODY: Final[dict[str, object]] = {"kind": "capture"}
IDLE_STATE: Final[dict[str, object]] = {
    "state": "idle",
    "mode": "sim",
    "busy_reason": None,
    "trigger": None,
}
REAL_IDLE_STATE: Final[dict[str, object]] = {**IDLE_STATE, "mode": "real"}


@dataclass(slots=True)
class Rig:
    """Панель ``create_app`` с инжектированным фейк-владельцем live."""

    app: FastAPI
    gate: LiveCaptureGate
    scope: FakeHantekScope
    clock: ManualClock

    def advance(self, blocks: int) -> None:
        """Ставит часы на ``blocks`` блоков прибора (без sleep)."""
        self.clock.now_s = blocks * self.scope.expected_block_interval_s


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    gate, scope, clock, _factory = gate_with(tmp_path)
    app = create_app(
        root=tmp_path / "sessions",
        runtime_db=tmp_path / "runtime.sqlite3",
        instrument=gate,
    )
    yield Rig(app=app, gate=gate, scope=scope, clock=clock)
    gate.stop()


def nonce_headers(client: TestClient) -> dict[str, str]:
    """Заголовок launch-nonce текущего запуска панели."""
    config: dict[str, object] = client.get("/api/config").json()
    nonce = config["mutation_nonce"]
    assert isinstance(nonce, str)
    return {"X-LNT-Mutation-Nonce": nonce}


async def stream_across_shutdown(rig: Rig) -> list[ServerSentEvent]:
    """Прогон SSE-генератора через shutdown lifespan: dispose завершает поток."""
    events: list[ServerSentEvent] = []
    first_frame = asyncio.Event()

    async def drain() -> None:
        stream = routes_live.live_frames(
            gate=rig.gate,
            max_points=MAX_FRAME_POINTS,
            min_interval_s=0.0,
        )
        async for event in stream:
            events.append(event)
            if event.event == "frame":
                first_frame.set()

    lifespan = rig.app.router.lifespan_context(rig.app)
    async with lifespan:
        rig.gate.start(start_config())
        rig.advance(2)
        task = asyncio.create_task(drain())
        await asyncio.wait_for(first_frame.wait(), FRAME_WAIT_S)
    # Выход из lifespan выполнил dispose; генератор обязан завершиться сам.
    await asyncio.wait_for(task, STREAM_END_S)
    return events


# ---------------------------------------------------------------------------
# happy: lifespan регистрирует владельца, прибор ленивый
# ---------------------------------------------------------------------------


def test_lifespan_registers_owner_and_defers_device_until_start(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        services: AppServices = rig.app.state.lnt_services
        idle = client.get("/api/live/state")
        untouched_at_startup = list(rig.scope.calls)
        started = client.post("/api/live/start", headers=nonce_headers(client), json=START_BODY)
        running = client.get("/api/live/state")
        opened = rig.scope.calls.count("open_handle")
        active = rig.gate.is_active

    assert services.instrument is rig.gate
    assert idle.json() == IDLE_STATE
    # Старт приложения прибор не трогает: ручка открывается только по POST start.
    assert untouched_at_startup == []
    assert started.status_code == 200
    assert started.json()["state"] == "running"
    assert running.json()["state"] == "running"
    assert opened == 1
    assert active is True


def test_shutdown_without_start_never_touches_device(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        state = client.get("/api/live/state")

    assert state.status_code == 200
    assert rig.scope.calls == []
    assert rig.gate.service is None
    assert rig.gate.is_active is False


def test_default_owner_is_registered_and_live_routes_are_mounted(tmp_path: Path) -> None:
    app = create_app(root=tmp_path / "sessions", runtime_db=tmp_path / "runtime.sqlite3")
    with TestClient(app) as client:
        state = client.get("/api/live/state")
        without_nonce = client.post("/api/live/start", json=START_BODY)

    # Без инъекции владелец собирается production-гейтом: режим объявлен честно.
    assert state.status_code == 200
    assert state.json() == REAL_IDLE_STATE
    # Маршрут смонтирован (не 404), и nonce-гейт срабатывает раньше прибора.
    assert without_nonce.status_code == 403


# ---------------------------------------------------------------------------
# dispose: shutdown останавливает активный live и завершает стрим
# ---------------------------------------------------------------------------


def test_shutdown_disposes_active_capture(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        start = client.post("/api/live/start", headers=nonce_headers(client), json=START_BODY)
        assert start.status_code == 200
        assert rig.scope.is_open is True

    assert rig.gate.is_active is False
    assert rig.scope.is_open is False
    assert rig.scope.calls[-1] == "close_handle"
    service = rig.gate.service
    assert service is not None
    assert service.is_running is False


def test_dispose_during_active_stream_ends_it_cleanly(rig: Rig) -> None:
    events = asyncio.run(stream_across_shutdown(rig))

    frames = [event for event in events if event.event == "frame"]
    assert events[0].event == "heartbeat"
    # Поток завершён сам (генератор вернулся), остаток ушёл кадрами.
    assert len(frames) >= 2
    final = frames[-1].data
    assert isinstance(final, LiveFramePayload)
    assert final.frame_index > 0
    assert rig.gate.is_active is False
    assert rig.scope.is_open is False
    assert rig.scope.calls[-1] == "close_handle"


def test_registered_owner_is_the_job_capture_gate(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        headers = nonce_headers(client)
        assert client.post("/api/live/start", headers=headers, json=START_BODY).status_code == 200
        blocked = client.post("/api/jobs", headers=headers, json=CAPTURE_BODY)
        jobs: dict[str, object] = client.get("/api/jobs").json()

    assert blocked.status_code == 409
    assert blocked.json() == {"detail": LIVE_BUSY_MESSAGE_RU}
    # Отказ до durable-регистрации: задача захвата не создана и воркер не запущен.
    assert jobs == {"items": []}
