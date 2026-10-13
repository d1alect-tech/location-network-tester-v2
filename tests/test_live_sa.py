"""Живой SA: пересчёт спектра на свип, пики до прореживания, бюджет 5000 точек.

Стенд детерминированный, как ``test_live_routes``: прибор — фейк с чистым
синусом на CH1 (10 кГц), время — ``ManualClock`` (ОТНОСИТЕЛЬНЫЙ ``advance``,
чтобы свипы повторялись после перезапуска), SSE читается блокирующим
``TestClient.stream``, а остановку захвата делает фон по событию первого кадра
(``Event.wait`` с дедлайном, не таймер). Первый poll отдаёт ровно два блока
(65 536 отсчётов) — заполнение SA-кольца детерминировано, поэтому разрешение
спектра проверяется точно, а не «где-то рядом».
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, override

import numpy as np
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from lnt.capture_preflight import BaselineCompatibility, CaptureEnvironment
from lnt.device_diagnostics import DeviceState
from lnt.instrument import (
    FakeHantekScope,
    LiveCaptureGate,
    LiveMode,
    ManualClock,
)
from lnt.instrument.fake_scope import _quantize  # pyright: ignore[reportPrivateUsage]
from lnt.runtime.store import JobStore
from lnt.scope_io import BLOCK_SAMPLES_PER_CHANNEL
from lnt.ui import routes_live
from lnt.ui.dependencies import AppServices, install_services
from lnt.ui.jobs import JobManager
from lnt.ui.models_live import MAX_SPECTRUM_POINTS, LiveSpectrumPayload
from lnt.ui.operations import LntBackend

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from httpx2 import Response
    from numpy.typing import NDArray

    from lnt.scope_io import ScopeProtocol

RATE_HZ: Final = 1_000_000.0
CADENCE_S: Final = BLOCK_SAMPLES_PER_CHANNEL / RATE_HZ
TONE_HZ: Final = 10_000.0
TONE_AMPLITUDE_V: Final = 1.0
# Лёгкий детерминированный шум (дитер): у чистого синуса нет шумового пола, и
# prominence-ранжирование поднимает лепестки квантования над тоном. Живой
# прибор шумит всегда — стенд честно имитирует пол прибора.
TONE_NOISE_SIGMA_V: Final = 0.02
BAND_LOW_HZ: Final = 0.0
BAND_HIGH_HZ: Final = 450_000.0
NYQUIST_HZ: Final = RATE_HZ / 2.0
PROFILE: Final = "bad"
SEED: Final = 2026
NEVER_CROSS_V: Final = 100.0
HUGE_FREE_BYTES: Final = 10**12
DEADLINE_S: Final = 30.0
EVENT_LIMIT: Final = 80
FRAME_WAIT_S: Final = 20.0
JOIN_TIMEOUT_S: Final = 20.0
FRAMES_QUERY: Final = "?min_interval_s=0"
RETRY_MS: Final = 1000
# Два блока прибора = 65 536 отсчётов, но развёртка съедает шов и хвост: 15 полных
# кадров = 61 440 отсчётов в кольце SA; rbw 10 Гц при 1 МГц даёт nperseg 2^15.
NPERSEG_FINE: Final = 32_768
NPERSEG_COARSE: Final = 2_048
RESOLUTION_HZ: Final = RATE_HZ / NPERSEG_FINE
# Полоса 0..450 кГц на сетке 32 769 бинов: ~14 746 бинов — прореживание обязано включиться.
DECIMATED_MIN_POINTS: Final = 4_000

START_TRIGGER_BODY: Final[dict[str, object]] = {
    "level_v": NEVER_CROSS_V,
    "slope": "rising",
    "source": "ch2",
    "mode": "auto",
    "auto_timeout_s": CADENCE_S,
}
START_BODY: Final[dict[str, object]] = {
    "sample_rate_hz": RATE_HZ,
    "ch1_range_v": 5.0,
    "ch1_probe_multiplier": 1.0,
    "trigger": START_TRIGGER_BODY,
}


class SineScope(FakeHantekScope):
    """Фейк-прибор с синусом+шумом на CH1: кольцо перекрывается после старта."""

    def __init__(
        self,
        *,
        clock: ManualClock,
        sample_rate_hz: float,
        tone_hz: float,
        amplitude_v: float,
        noise_sigma_v: float,
        buffer_blocks: int = 8,
    ) -> None:
        super().__init__(
            profile=PROFILE,
            seed=SEED,
            sample_rate_hz=sample_rate_hz,
            clock=clock,
            buffer_blocks=buffer_blocks,
        )
        self._tone_hz: float = tone_hz
        self._amplitude_v: float = amplitude_v
        self._noise_sigma_v: float = noise_sigma_v

    @override
    def start_capture(self) -> bool:
        """Собирает кольцо синуса с шумом вместо профиля сети (каденс тот же)."""
        started = super().start_capture()
        rate_hz = self._require_rate_hz()
        count = int(self._ch1_ring.size)
        moments = np.arange(count, dtype=np.float64) / rate_hz
        rng = np.random.default_rng(SEED)
        tone = self._amplitude_v * np.sin(2.0 * np.pi * self._tone_hz * moments) + rng.normal(
            0.0, self._noise_sigma_v, count
        )
        ch1_ring = _quantize(tone.astype(np.float32), self.ch1_range_code)
        ch2_ring = np.zeros(count, dtype=np.uint8)
        self._ch1_ring: NDArray[np.uint8] = ch1_ring
        self._ch2_ring: NDArray[np.uint8] = ch2_ring
        return started


@dataclass(slots=True)
class _Factory:
    """Инжектируемая фабрика прибора: отдаёт один фейк и считает вызовы."""

    scope: SineScope
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
    """Панель живого SA: фейк-синус, инжектируемые часы, nonce запуска."""

    app: FastAPI
    gate: LiveCaptureGate
    scope: SineScope
    clock: ManualClock
    nonce: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-LNT-Mutation-Nonce": self.nonce}

    def advance(self, blocks: int) -> None:
        """Двигает часы ОТНОСИТЕЛЬНО на ``blocks`` кадров прибора (без sleep)."""
        self.clock.advance(blocks * self.scope.expected_block_interval_s)

    def start(self, client: TestClient) -> Response:
        return client.post("/api/live/start", headers=self.headers, json=START_BODY)

    def stop(self, client: TestClient) -> Response:
        return client.post("/api/live/stop", headers=self.headers, json={})

    def configure_sa(self, client: TestClient, sa: dict[str, object] | None) -> Response:
        """POST /api/live/config: триггер эхом + опциональная SA-конфигурация."""
        body: dict[str, object] = {**START_TRIGGER_BODY, "sa": sa}
        return client.post("/api/live/config", headers=self.headers, json=body)


def sa_config(**overrides: object) -> dict[str, object]:
    """Тело SA-конфигурации: перекрытия поверх полного набора ручек."""
    base: dict[str, object] = {
        "rbw_hz": 10.0,
        "window": "hann",
        "band_low_hz": BAND_LOW_HZ,
        "band_high_hz": BAND_HIGH_HZ,
        "detector": "mean",
    }
    return {**base, **overrides}


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    clock = ManualClock()
    scope = SineScope(
        clock=clock,
        sample_rate_hz=RATE_HZ,
        tone_hz=TONE_HZ,
        amplitude_v=TONE_AMPLITUDE_V,
        noise_sigma_v=TONE_NOISE_SIGMA_V,
    )
    factory = _Factory(scope=scope)
    gate = LiveCaptureGate(
        scope_factory=factory,
        environment_probe=_Environment().probe,
        session_root=tmp_path / "sessions",
        clock=clock,
        discard_lead_samples=0,
        mode=LiveMode.SIM,
    )
    root = tmp_path / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    app = FastAPI()
    install_services(
        app,
        AppServices(
            root=root,
            catalog_db=tmp_path / "catalog.sqlite3",
            runtime_db=tmp_path / "runtime.sqlite3",
            jobs=JobManager(
                backend=LntBackend(),
                root=root,
                store=JobStore(tmp_path / "runtime.sqlite3"),
            ),
            instrument=gate,
        ),
    )
    app.include_router(routes_live.router)
    yield Rig(
        app=app,
        gate=gate,
        scope=scope,
        clock=clock,
        nonce=app.state.lnt_security.mutation_nonce,
    )
    gate.stop()


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
            continue
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


def stop_after_first_frame(rig: Rig) -> None:
    """Фон: ждёт первый кадр подпиской на сервис и освобождает прибор."""
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


def first_spectrum(events: list[SseEvent]) -> dict[str, object]:
    """Данные первого события ``spectrum``; отсутствие — падение теста."""
    for event in events:
        if event.name == "spectrum":
            return event.data
    pytest.fail("SSE-поток не дал события spectrum")


# ---------------------------------------------------------------------------
# трасс SA: событие spectrum на каждый опубликованный свип
# ---------------------------------------------------------------------------


def test_spectrum_event_carries_sine_peak_within_resolution(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        assert rig.configure_sa(client, sa_config(rbw_hz=10.0)).status_code == 200
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")

    assert events[0].name == "heartbeat"
    frames = [event for event in events if event.name == "frame"]
    spectra = [event for event in events if event.name == "spectrum"]
    assert frames
    # Один трасс SA на каждый опубликованный свип: без дублей и пропусков.
    assert len(spectra) == len(frames)
    first_frame_position = next(i for i, event in enumerate(events) if event.name == "frame")
    assert events[first_frame_position + 1].name == "spectrum"
    # id события — индекс свипа, общий с кадром; retry — как у задач.
    assert spectra[0].event_id == str(0)
    assert spectra[0].event_id == frames[0].event_id
    assert spectra[0].retry == RETRY_MS

    payload = LiveSpectrumPayload.model_validate(first_spectrum(events))
    assert payload.frame_index == 0
    assert payload.meta.rbw == 10.0
    assert payload.meta.window == "hann"
    assert payload.meta.resolution == pytest.approx(RESOLUTION_HZ)
    assert payload.meta.enbw > 0.0

    # Бюджет точки: полоса ~14 746 бинов прорежена до <= 5000 (прореживание включилось).
    assert len(payload.freq) == len(payload.psd_db)
    assert len(payload.freq) <= MAX_SPECTRUM_POINTS
    assert len(payload.freq) >= DECIMATED_MIN_POINTS
    assert list(payload.freq) == sorted(payload.freq)
    assert all(math.isfinite(value) for value in payload.psd_db)

    # Пики найдены ДО прореживания: уточнённая частота вершины синуса.
    assert payload.peaks
    top = payload.peaks[0]
    assert top.frequency_hz == pytest.approx(TONE_HZ, abs=RESOLUTION_HZ)
    assert all(peak.prominence_db <= top.prominence_db for peak in payload.peaks)


def test_rbw_selector_changes_nperseg(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        assert rig.configure_sa(client, sa_config(rbw_hz=10.0)).status_code == 200
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")
        fine = LiveSpectrumPayload.model_validate(first_spectrum(events))

        # Перезапуск захвата: SA сбрасывается стартом, конфиг — заново.
        assert rig.start(client).status_code == 200
        rig.advance(2)
        assert rig.configure_sa(client, sa_config(rbw_hz=300.0)).status_code == 200
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")
        coarse = LiveSpectrumPayload.model_validate(first_spectrum(events))

    nperseg_fine = round(RATE_HZ / fine.meta.resolution)
    nperseg_coarse = round(RATE_HZ / coarse.meta.resolution)
    assert nperseg_fine == NPERSEG_FINE
    assert nperseg_coarse == NPERSEG_COARSE
    assert fine.meta.rbw == 10.0
    assert coarse.meta.rbw == 300.0
    assert fine.meta.resolution < coarse.meta.resolution


# ---------------------------------------------------------------------------
# POST /api/live/config: контракт SA-конфигурации
# ---------------------------------------------------------------------------


def test_band_above_nyquist_is_unprocessable(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        beyond = rig.configure_sa(client, sa_config(band_high_hz=NYQUIST_HZ * 1.2))
        # Отказ не конфигурирует контур — проверка ДО допустимой границы.
        rejected = rig.gate.spectrum.config
        boundary = rig.configure_sa(client, sa_config(band_high_hz=NYQUIST_HZ))

    assert beyond.status_code == 422
    assert rejected is None
    # Граница Найквиста включительно — допустимая полоса, не отказ.
    assert boundary.status_code == 200
    assert rig.gate.spectrum.config is not None


def test_band_above_nyquist_fraction_is_unprocessable(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        empty = rig.configure_sa(
            client,
            sa_config(band_low_hz=460_000.0, band_high_hz=480_000.0),
        )

    assert empty.status_code == 422
    assert rig.gate.spectrum.config is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rbw_hz", 20.0),
        ("window", "bogus"),
        ("detector", "avg"),
        ("band_low_hz", 500_000.0),
    ],
)
def test_invalid_sa_selector_values_are_unprocessable(rig: Rig, field: str, value: object) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        response = rig.configure_sa(client, sa_config(**{field: value}))

    assert response.status_code == 422
    assert rig.gate.spectrum.config is None


# ---------------------------------------------------------------------------
# обратная совместимость конфигурации только-scope
# ---------------------------------------------------------------------------


def test_scope_only_config_leaves_sa_enabled(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        assert rig.configure_sa(client, sa_config()).status_code == 200
        plain = client.post(
            "/api/live/config",
            headers=rig.headers,
            json=START_TRIGGER_BODY,
        )
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")

    assert plain.status_code == 200
    assert rig.gate.spectrum.config is not None
    assert any(event.name == "spectrum" for event in events)


def test_sa_null_disables_spectrum_events(rig: Rig) -> None:
    with TestClient(rig.app) as client:
        assert rig.start(client).status_code == 200
        rig.advance(2)
        assert rig.configure_sa(client, sa_config()).status_code == 200
        off = rig.configure_sa(client, None)
        events = read_stream(rig, client, f"/api/live/frames{FRAMES_QUERY}")

    assert off.status_code == 200
    assert rig.gate.spectrum.config is None
    assert any(event.name == "frame" for event in events)
    assert not any(event.name == "spectrum" for event in events)
