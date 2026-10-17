"""LiveCaptureGate: preflight-гейт live-старта и владение прибором для job-захвата.

Без железа: прибор — ``FakeHantekScope``, время — ``ManualClock`` (кадры
ставятся одним присваиванием, как в ``test_instrument_service``); reaper-тесты
ждут смены состояния с ограниченным окном (``_wait_until``), реальный поток
один — сам reaper. Контракт 409 проверяется через реальный маршрут
``POST /api/jobs`` и существующий ``map_domain_error`` (issue #26, резолюция
п.2/п.6): live-старт всегда идёт через ``run_capture_preflight``, блокеры
отклоняют старт ДО прикосновения к прибору, а job-захват при активной вкладке
получает 409 «устройство занято вкладкой». Семантика ``/api/device/state`` не
подменяется — гейт живёт отдельным статусом владения.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, override

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from lnt.capture_preflight import (
    BaselineCompatibility,
    CaptureEnvironment,
    FindingSeverity,
    PreflightFinding,
)
from lnt.device_diagnostics import DeviceState
from lnt.errors import DeviceNotFoundError, InputError
from lnt.instrument import (
    DeviceBusyError,
    FakeHantekScope,
    InstrumentState,
    LiveCaptureGate,
    LiveFrame,
    LivePreflightBlockedError,
    LiveStartConfig,
    ManualClock,
    TriggerConfig,
    TriggerMode,
    TriggerSlope,
    TriggerSource,
)
from lnt.instrument.live_gate import LIVE_BUSY_MESSAGE_RU
from lnt.runtime.scheduler import OperationScheduler
from lnt.runtime.store import JobStore
from lnt.scope_io import (
    BLOCK_SAMPLES_PER_CHANNEL,
    NEVER_CANCELLED,
    RANGE_CODE_5V,
    CancellationToken,
)
from lnt.ui import routes_jobs
from lnt.ui.dependencies import AppServices, install_services, map_domain_error
from lnt.ui.device import DeviceStatus
from lnt.ui.jobs import JobManager
from lnt.ui.operations import LntBackend

if TYPE_CHECKING:
    from collections.abc import Callable

    from lnt.scope_io import ScopeProtocol
    from lnt.types import SeriesPosition
    from lnt.ui.models import CaptureRequest
    from lnt.ui.security import SecurityContext

# Тот же детерминированный стенд, что в test_instrument_service: 1 МГц (код 1),
# профиль «bad», порог 4.9 В выше сети (±3 В) и в окне триггера — недостижим.
RATE_HZ = 1_000_000.0
RATE_CODE = 1
CADENCE_S = BLOCK_SAMPLES_PER_CHANNEL / RATE_HZ
PROFILE = "bad"
SEED = 2026
NEVER_CROSS_V = 4.9
TRIGGER_LEVEL_V = 0.0
HUGE_FREE_BYTES = 10**12


@dataclass(slots=True)
class _Factory:
    """Инжектируемая фабрика прибора: отдаёт один фейк и считает вызовы."""

    scope: FakeHantekScope
    calls: int = 0

    def __call__(self) -> ScopeProtocol:
        self.calls += 1
        return self.scope


@dataclass(slots=True)
class _FailingFactory:
    """Фабрика с отказом «устройство не найдено»: проверка типизированного проброса."""

    calls: int = 0

    def __call__(self) -> ScopeProtocol:
        self.calls += 1
        raise DeviceNotFoundError("имитация отсутствия прибора при старте live")


@dataclass(slots=True)
class _Environment:
    """Инжектируемая проба ``CaptureEnvironment``; скрытого I/O в гейте нет."""

    device_state: DeviceState = DeviceState.READY
    root_writable: bool = True
    free_bytes: int = HUGE_FREE_BYTES
    calls: int = 0

    def probe(self) -> CaptureEnvironment:
        self.calls += 1
        return CaptureEnvironment(
            device_state=self.device_state,
            free_bytes=self.free_bytes,
            root_writable=self.root_writable,
            baseline_compatibility=BaselineCompatibility.NOT_REQUESTED,
        )


@dataclass(slots=True)
class _Rig:
    gate: LiveCaptureGate
    scope: FakeHantekScope
    clock: ManualClock
    factory: _Factory
    environment: _Environment

    def advance(self, blocks: int) -> None:
        """Ставит часы на ``blocks`` кадров прибора (без sleep)."""
        self.clock.now_s = blocks * self.scope.expected_block_interval_s


def _rig(
    *,
    device_state: DeviceState = DeviceState.READY,
    root_writable: bool = True,
    free_bytes: int = HUGE_FREE_BYTES,
) -> _Rig:
    clock = ManualClock()
    scope = FakeHantekScope(
        profile=PROFILE,
        seed=SEED,
        sample_rate_hz=RATE_HZ,
        clock=clock,
        buffer_blocks=8,
    )
    factory = _Factory(scope=scope)
    environment = _Environment(
        device_state=device_state,
        root_writable=root_writable,
        free_bytes=free_bytes,
    )
    gate = LiveCaptureGate(
        scope_factory=factory,
        environment_probe=environment.probe,
        # Preflight чистый: корень участвует только в запросе, I/O к нему нет.
        session_root=Path("sessions"),
        clock=clock,
        discard_lead_samples=0,
    )
    return _Rig(
        gate=gate,
        scope=scope,
        clock=clock,
        factory=factory,
        environment=environment,
    )


def _config(
    *,
    mode: TriggerMode = TriggerMode.AUTO,
    level_v: float = NEVER_CROSS_V,
    source: TriggerSource = TriggerSource.CH2,
    ch1_range_v: float = 5.0,
    ch1_probe_multiplier: float = 1.0,
) -> LiveStartConfig:
    return LiveStartConfig(
        trigger=TriggerConfig(
            level_v=level_v,
            slope=TriggerSlope.RISING,
            source=source,
            mode=mode,
            auto_timeout_s=CADENCE_S,
        ),
        sample_rate_hz=RATE_HZ,
        ch1_range_v=ch1_range_v,
        ch1_probe_multiplier=ch1_probe_multiplier,
    )


@dataclass(frozen=True, slots=True)
class _NoHardwareBackend(LntBackend):
    """Backend без устройства: захват типизированно отказывает, диагностика честная."""

    @override
    def capture_one(
        self,
        request: CaptureRequest,
        out_dir: Path,
        series: SeriesPosition | None,
        cancellation_token: CancellationToken = NEVER_CANCELLED,
    ) -> Path:
        del request, out_dir, series, cancellation_token
        raise DeviceNotFoundError("заглушка: реального захвата в этом тесте нет")

    @override
    def device_check(self) -> DeviceStatus:
        return DeviceStatus(
            driver_installed=False,
            device_opened=False,
            firmware_present=False,
            error_message=None,
            hints=(),
            state=DeviceState.DEVICE_ABSENT,
            description_ru="Заглушка диагностики: устройства нет.",
            recovery_action_ru="Действия не требуются.",
        )


def _panel(tmp_path: Path, gate: LiveCaptureGate) -> tuple[FastAPI, OperationScheduler]:
    """Минимальная панель: реальный маршрут задач + менеджер с гейтом владения."""
    root = tmp_path / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    runtime_db = tmp_path / "runtime.sqlite3"
    scheduler = OperationScheduler()
    manager = JobManager(
        backend=_NoHardwareBackend(),
        root=root,
        store=JobStore(runtime_db),
        scheduler=scheduler,
        live_ownership=gate,
    )
    app = FastAPI()
    install_services(
        app,
        AppServices(
            root=root,
            catalog_db=tmp_path / "catalog.sqlite3",
            runtime_db=runtime_db,
            jobs=manager,
        ),
    )
    app.include_router(routes_jobs.router)
    return app, scheduler


# ---------------------------------------------------------------------------
# preflight-гейт live-старта
# ---------------------------------------------------------------------------


def test_device_blocker_aborts_start_before_the_device_is_touched() -> None:
    rig = _rig(device_state=DeviceState.HANDLE_BUSY)

    with pytest.raises(LivePreflightBlockedError) as excinfo:
        rig.gate.start(_config())

    blockers = excinfo.value.blockers
    assert [item.code for item in blockers] == ["device_handle_busy"]
    assert all(item.severity is FindingSeverity.BLOCK for item in blockers)
    # Причина видна в сообщении: preflight сначала, прибор потом.
    assert blockers[0].message_ru in str(excinfo.value)
    assert rig.environment.calls == 1
    assert rig.factory.calls == 0
    assert rig.scope.calls == []
    assert rig.gate.is_active is False
    assert rig.gate.service is None


@pytest.mark.parametrize(
    ("device_state", "root_writable", "free_bytes", "expected_code"),
    [
        (DeviceState.DRIVER_MISSING, True, HUGE_FREE_BYTES, "device_driver_missing"),
        (DeviceState.READY, False, HUGE_FREE_BYTES, "session_root_not_writable"),
        (DeviceState.READY, True, 1, "insufficient_disk_space"),
    ],
)
def test_environment_blockers_reach_preflight_and_stop_start(
    device_state: DeviceState,
    root_writable: bool,
    free_bytes: int,
    expected_code: str,
) -> None:
    rig = _rig(
        device_state=device_state,
        root_writable=root_writable,
        free_bytes=free_bytes,
    )

    with pytest.raises(LivePreflightBlockedError) as excinfo:
        rig.gate.start(_config())

    assert [item.code for item in excinfo.value.blockers] == [expected_code]
    assert rig.factory.calls == 0
    assert rig.gate.is_active is False


def test_clean_preflight_starts_live_and_takes_the_handle() -> None:
    rig = _rig()

    service = rig.gate.start(_config())

    assert rig.environment.calls == 1
    assert rig.factory.calls == 1
    assert rig.scope.is_open is True
    assert rig.scope.is_capturing is True
    assert rig.scope.rate_code == RATE_CODE
    assert rig.scope.ch1_range_code == RANGE_CODE_5V
    assert service.is_running is True
    assert rig.gate.service is service
    assert rig.gate.is_active is True


def test_warning_finding_does_not_block_start() -> None:
    # 10x пробник на диапазоне 5 В — WARN weak_signal_resolution: старт разрешён.
    rig = _rig()

    service = rig.gate.start(_config(ch1_probe_multiplier=10.0, ch1_range_v=5.0))

    assert rig.gate.is_active is True
    assert service.is_running is True
    assert rig.factory.calls == 1


def test_double_start_is_rejected_without_a_second_handle() -> None:
    rig = _rig()
    rig.gate.start(_config())

    with pytest.raises(InputError):
        rig.gate.start(_config())

    assert rig.factory.calls == 1
    assert rig.scope.calls.count("open_handle") == 1
    assert rig.gate.is_active is True


def test_device_factory_failure_propagates_typed_and_leaves_the_gate_inactive() -> None:
    clock = ManualClock()
    factory = _FailingFactory()
    environment = _Environment()
    gate = LiveCaptureGate(
        scope_factory=factory,
        environment_probe=environment.probe,
        session_root=Path("sessions"),
        clock=clock,
    )

    with pytest.raises(DeviceNotFoundError):
        gate.start(_config())

    assert factory.calls == 1
    assert gate.is_active is False
    assert gate.service is None
    # Владение не взято: job-захват не блокируется.
    gate.require_device_free()


def test_invalid_config_is_rejected_typed_before_the_environment_probe() -> None:
    rig = _rig()

    with pytest.raises(InputError):
        rig.gate.start(_config(ch1_range_v=2.5))

    assert rig.environment.calls == 0
    assert rig.factory.calls == 0
    assert rig.gate.is_active is False


# ---------------------------------------------------------------------------
# владение прибором: live против job-захвата
# ---------------------------------------------------------------------------


def test_stop_releases_the_device_and_ownership() -> None:
    rig = _rig()
    service = rig.gate.start(_config())

    rig.gate.stop()

    assert rig.gate.is_active is False
    assert service.is_running is False
    assert rig.scope.is_open is False
    assert rig.scope.calls[-1] == "close_handle"
    rig.gate.stop()  # идемпотентно
    assert rig.scope.calls.count("close_handle") == 1


def test_require_device_free_mirrors_live_ownership() -> None:
    rig = _rig()
    rig.gate.require_device_free()

    rig.gate.start(_config())
    with pytest.raises(DeviceBusyError) as excinfo:
        rig.gate.require_device_free()
    rig.gate.stop()
    rig.gate.require_device_free()

    assert str(excinfo.value) == LIVE_BUSY_MESSAGE_RU


def test_single_trigger_self_stop_releases_ownership() -> None:
    # SINGLE сам освобождает прибор после триггерного кадра: владение следует
    # за фактическим состоянием сервиса, а не за флагом «был старт».
    rig = _rig()
    service = rig.gate.start(_config(mode=TriggerMode.SINGLE, level_v=TRIGGER_LEVEL_V))

    rig.advance(4)
    assert service.poll() == 1

    assert rig.gate.is_active is False
    assert rig.scope.is_open is False
    rig.gate.require_device_free()


# ---------------------------------------------------------------------------
# reaper: мёртвый потребитель освобождает прибор за секунды
# ---------------------------------------------------------------------------


def _wait_until(predicate: Callable[[], bool], timeout_s: float) -> bool:
    """Ждёт смены состояния с ограниченным окном; фиксированных таймингов нет."""
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def test_reaper_releases_the_device_when_the_consumer_stops_polling() -> None:
    rig = _rig()
    service = rig.gate.start(_config())
    assert service.last_poll_s == 0.0  # старт засеял момент взятия ручки

    # Потребитель пропал: фейк-часы уходят за порог, ни одного poll.
    rig.clock.advance(11.0)

    assert _wait_until(lambda: not rig.gate.is_active, 5.0) is True
    assert service.state is InstrumentState.STOPPED
    assert service.is_running is False
    assert rig.scope.is_open is False
    assert rig.scope.calls[-1] == "close_handle"
    assert rig.scope.calls.count("close_handle") == 1
    reaper = rig.gate.reaper_thread
    assert reaper is not None
    reaper.join(timeout=5.0)
    assert reaper.is_alive() is False


def test_reaper_stop_honors_the_contract_final_frame_then_close_handle() -> None:
    # Тот же контракт, что у явного stop: финальный кадр уходит подписчику при
    # открытой ручке, затем stop_capture и close_handle. NORMAL без фронта —
    # кадр копится в буфере и достаётся именно финальным сбросом.
    rig = _rig()
    frames: list[LiveFrame] = []
    handle_open: list[bool] = []

    def on_frame(frame: LiveFrame) -> None:
        frames.append(frame)
        handle_open.append(rig.scope.is_open)

    service = rig.gate.start(_config(mode=TriggerMode.NORMAL))
    service.subscribe(on_frame)
    rig.advance(1)
    assert service.poll() == 0
    assert frames == []

    rig.clock.advance(11.0)
    assert _wait_until(lambda: not rig.gate.is_active, 5.0) is True

    assert len(frames) == 1
    assert handle_open == [True]
    assert frames[0].triggered is False
    assert frames[0].ch2.size == 4096
    assert rig.scope.calls[-2:] == ["stop_capture", "close_handle"]
    assert service.state is InstrumentState.STOPPED


def test_regular_polling_keeps_the_reaper_idle() -> None:
    rig = _rig()
    service = rig.gate.start(_config())

    # Живой потребитель: окно ~1.6 с реального времени покрывает тик reaper,
    # фейк-часы шагом 0.3 с — возраст последнего poll далеко от порога.
    deadline = time.monotonic() + 1.6
    while time.monotonic() < deadline:
        rig.clock.advance(0.3)
        service.poll()
        time.sleep(0.02)

    assert rig.gate.is_active is True
    assert service.is_running is True
    assert rig.scope.is_open is True
    assert rig.scope.calls.count("close_handle") == 0

    rig.gate.stop()
    assert rig.scope.calls.count("close_handle") == 1


@pytest.mark.parametrize("reap_after_s", [1.0, 0.0, -1.0, float("nan"), float("inf")])
def test_reap_after_s_outside_the_floor_is_rejected(reap_after_s: float) -> None:
    clock = ManualClock()
    scope = FakeHantekScope(profile=PROFILE, seed=SEED, sample_rate_hz=RATE_HZ, clock=clock)

    with pytest.raises(InputError, match="reap_after_s"):
        LiveCaptureGate(
            scope_factory=_Factory(scope=scope),
            environment_probe=_Environment().probe,
            session_root=Path("sessions"),
            clock=clock,
            reap_after_s=reap_after_s,
        )


def test_restart_joins_the_previous_reaper_and_keeps_one_thread() -> None:
    # SINGLE сам отпускает прибор; повторный старт глушит старый reaper,
    # а не копит их: прибор один — поток слежки тоже один.
    rig = _rig()
    rig.gate.start(_config(mode=TriggerMode.SINGLE, level_v=TRIGGER_LEVEL_V))
    first = rig.gate.reaper_thread
    assert first is not None

    rig.advance(4)
    assert rig.gate.service is not None
    assert rig.gate.service.poll() == 1
    assert rig.gate.is_active is False

    rig.gate.start(_config(mode=TriggerMode.SINGLE, level_v=TRIGGER_LEVEL_V))
    second = rig.gate.reaper_thread
    assert second is not None
    assert second is not first
    first.join(timeout=5.0)
    assert first.is_alive() is False

    rig.gate.stop()
    assert rig.scope.calls.count("close_handle") == 2


# ---------------------------------------------------------------------------
# HTTP-контракт: существующий map_domain_error и реальный POST /api/jobs
# ---------------------------------------------------------------------------


def test_map_domain_error_converts_gate_errors_with_visible_reason() -> None:
    blocked = LivePreflightBlockedError(
        (
            PreflightFinding(
                severity=FindingSeverity.BLOCK,
                code="device_driver_missing",
                message_ru="Устройство не готово: driver_missing.",
                recovery_action_ru="Установите WinUSB и повторите preflight.",
            ),
        ),
    )

    blocked_http = map_domain_error(blocked)
    busy_http = map_domain_error(DeviceBusyError())

    assert blocked_http.status_code == 422
    assert "Устройство не готово: driver_missing." in str(blocked_http.detail)
    assert busy_http.status_code == 409
    assert busy_http.detail == LIVE_BUSY_MESSAGE_RU


def test_capture_post_is_conflict_while_live_active_and_allowed_after_stop(
    tmp_path: Path,
) -> None:
    rig = _rig()
    app, scheduler = _panel(tmp_path, rig.gate)
    rig.gate.start(_config())
    try:
        with TestClient(app) as client:
            security: SecurityContext = app.state.lnt_security
            headers = {"X-LNT-Mutation-Nonce": security.mutation_nonce}

            blocked = client.post("/api/jobs", headers=headers, json={"kind": "capture"})
            assert blocked.status_code == 409
            assert blocked.json() == {"detail": LIVE_BUSY_MESSAGE_RU}
            # Отказ до durable-регистрации: задача захвата не создана.
            assert client.get("/api/jobs").json()["items"] == []

            # «Занято» — только для захвата: диагностика устройства разрешена
            # и во время live (честно вернёт HANDLE_BUSY на реальном железе).
            diagnostic = client.post("/api/jobs", headers=headers, json={"kind": "device_check"})
            assert diagnostic.status_code == 202

            rig.gate.stop()
            allowed = client.post("/api/jobs", headers=headers, json={"kind": "capture"})
            assert allowed.status_code == 202

            # Детерминированная уборка без отмены из постороннего контура:
            # джойним воркеры, терминальные снимки портал-луп применит сам.
            scheduler.close()
    finally:
        rig.gate.stop()
