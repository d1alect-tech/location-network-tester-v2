"""Preflight-гейт живого режима и владение прибором для job-захвата.

Живая вкладка владеет ручкой Hantek между ``start`` и ``stop`` (issue #26).
Старт всегда проходит через ``capture_preflight.run_capture_preflight``:
BLOCK-findings прерывают старт ДО взятия прибора, причину несёт
``LivePreflightBlockedError`` (панель маппит её в 422 с reason через
``map_domain_error``); WARN-findings старт не блокируют. Пока ``is_active``,
гейт job-захвата ``require_device_free`` поднимает ``DeviceBusyError`` —
панель отвечает 409 «устройство занято вкладкой» через тот же
``map_domain_error``.

Пробы ``CaptureEnvironment`` (диагностика устройства, диск, writability корня)
внедряются: гейт не делает скрытого I/O и не импортирует ``ui/``. Подмены
``/api/device/state`` нет — во время live диагностика честно вернёт
``HANDLE_BUSY``, а владение живёт отдельным статусом ``is_active``.

Пока прибор живой, reaper-поток гейта следит за возрастом последнего ``poll``:
мёртвая вкладка (упал браузер, оборвался SSE) теряет прибор за ``REAP_AFTER_S``
секунд, остановка идёт контрактом ``stop`` (финальный кадр, затем close_handle).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Event, RLock, Thread, current_thread
from typing import TYPE_CHECKING, Final, Protocol

from lnt.capture_preflight import (
    CaptureEnvironment,
    CapturePreflightRequest,
    FindingSeverity,
    run_capture_preflight,
)
from lnt.errors import InputError, LntError
from lnt.instrument.frames import (
    DEFAULT_FRAME_SAMPLES,
    DEFAULT_MAX_BUFFERED_BLOCKS,
    UNSTABLE_LEAD_SAMPLES,
)
from lnt.instrument.ripple_types import continuity_basis_for
from lnt.instrument.sa import SaEngine
from lnt.instrument.service import (
    DEFAULT_CH1_RANGE_V,
    DEFAULT_SAMPLE_RATE_HZ,
    InstrumentService,
)
from lnt.scope_io import BLOCK_SAMPLES_PER_CHANNEL, MAX_POLL_TIMEOUT_MS, NEVER_CANCELLED
from lnt.types import (
    ChannelMode,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    SessionType,
)

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.adc_calibration import AdcCalibration
    from lnt.capture_preflight import PreflightFinding
    from lnt.instrument.service import Clock
    from lnt.instrument.trigger import TriggerConfig
    from lnt.scope_io import CancellationToken, ScopeProtocol

LIVE_BUSY_MESSAGE_RU: Final = "устройство занято вкладкой"

# Reaper: потребитель, не опрашивавший поток дольше REAP_AFTER_S (мёртвая
# вкладка/браузер), теряет прибор за секунды; каденс проверки — REAP_POLL_S.
REAP_AFTER_S: Final = 10.0
REAP_AFTER_FLOOR_S: Final = 2.0
REAP_POLL_S: Final = 1.0

EnvironmentProbe = Callable[[], CaptureEnvironment]


class LiveMode(StrEnum):
    """Происхождение отсчётов живого потока: железо или фейк-прибор.

    Объявляется тем, кто собрал гейт (``scope_factory`` знает только он), и
    отдаётся панелью ОТДЕЛЬНЫМ полем статуса: sim-поток измерим так же, как
    железный, но подпись «Симуляция» обязательна — режим не выводится из
    состояния владения и не угадывается по наличию кадров.
    """

    REAL = "real"
    SIM = "sim"


# Модель входа живой вкладки: тот же номинальный RC-шунт, что у измерения по
# умолчанию в панели (``ui/routes_device._setup``); preflight сверяет её с типом.
_LIVE_CH1_SETUP: Final = FloatingDifferentialRcShunt(
    resistance_ohm=100.0,
    c1_f=10e-9,
    c2_f=10e-9,
    component_values_basis=ComponentValuesBasis.NOMINAL,
    reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
)


class LivePreflightBlockedError(LntError):
    """Старт live отклонён блокером ``capture_preflight``: причины в findings."""

    def __init__(self, blockers: tuple[PreflightFinding, ...]) -> None:
        """Собирает русскую причину из сообщений и восстановлений блокеров."""
        reason = " ".join(f"{item.message_ru} {item.recovery_action_ru}" for item in blockers)
        super().__init__(f"живой режим не запущен: {reason}")
        self.blockers: tuple[PreflightFinding, ...] = blockers


class DeviceBusyError(LntError):
    """Прибор во владении живой вкладки: job-захват запрещён до ``stop``."""

    def __init__(self) -> None:
        """Фиксирует каноническую русскую причину для 409-ответа панели."""
        super().__init__(LIVE_BUSY_MESSAGE_RU)


class LiveOwnership(Protocol):
    """Структурный контракт источника владения прибором для job-захвата."""

    def require_device_free(self) -> None:
        """Поднимает ``DeviceBusyError``, пока прибор держит живая вкладка."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class LiveStartConfig:
    """Параметры старта живого режима: каденс, диапазон, пробник, триггер."""

    trigger: TriggerConfig
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ
    ch1_range_v: float = DEFAULT_CH1_RANGE_V
    ch1_probe_multiplier: float = 1.0


class LiveCaptureGate:
    """Владелец живого потока: preflight-гейт старта и владение для job-захвата."""

    def __init__(  # noqa: PLR0913 - приборная панель: каждая ручка kw-only и с дефолтом
        self,
        *,
        scope_factory: Callable[[], ScopeProtocol],
        environment_probe: EnvironmentProbe,
        session_root: Path,
        clock: Clock = time.monotonic,
        frame_samples: int = DEFAULT_FRAME_SAMPLES,
        max_buffered_blocks: int = DEFAULT_MAX_BUFFERED_BLOCKS,
        discard_lead_samples: int = UNSTABLE_LEAD_SAMPLES,
        adc_calibration: AdcCalibration | None = None,
        cancellation_token: CancellationToken = NEVER_CANCELLED,
        poll_timeout_ms: int = MAX_POLL_TIMEOUT_MS,
        reap_after_s: float = REAP_AFTER_S,
        mode: LiveMode = LiveMode.REAL,
    ) -> None:
        """Запоминает зависимости; прибор не открывает и preflight не запускает."""
        if not (REAP_AFTER_FLOOR_S <= reap_after_s < float("inf")):
            raise InputError(f"reap_after_s {reap_after_s} должен быть >= 2 с и конечным")
        self._scope_factory: Final = scope_factory
        self._environment_probe: Final = environment_probe
        self._session_root: Final = session_root
        self._clock: Final = clock
        self._frame_samples: Final = frame_samples
        self._max_buffered_blocks: Final = max_buffered_blocks
        self._discard_lead_samples: Final = discard_lead_samples
        self._adc_calibration: Final = adc_calibration
        self._cancellation_token: Final = cancellation_token
        self._poll_timeout_ms: Final = poll_timeout_ms
        self._lock: Final = RLock()
        self._service: InstrumentService | None = None
        self._mode: Final = mode
        self._reap_after_s: Final = reap_after_s
        self._reaper: Thread | None = None
        self._reaper_stop: Event | None = None
        # Живой SA-контур: конфигурация и кольцо живут здесь, пересчёт на свип
        # гоняет SSE-контур панели (владелец потока), а не гейт.
        self._spectrum: Final = SaEngine()

    @property
    def mode(self) -> LiveMode:
        """Происхождение отсчётов потока: объявлено при сборке гейта."""
        return self._mode

    @property
    def spectrum(self) -> SaEngine:
        """Живой SA-контур: конфигурация и кольцо потока (см. ``instrument/sa``)."""
        return self._spectrum

    @property
    def service(self) -> InstrumentService | None:
        """Сервис живого потока: работающий или последний остановленный."""
        return self._service

    @property
    def reaper_thread(self) -> Thread | None:
        """Поток слежки за простоем потребителя (для тестов и диагностики)."""
        return self._reaper

    @property
    def is_active(self) -> bool:
        """Прибор во владении живой вкладки прямо сейчас (единственная правда)."""
        service = self._service
        return service is not None and service.is_running

    def start(self, config: LiveStartConfig) -> InstrumentService:
        """Валидирует конфигурацию, прогоняет preflight и только затем берёт прибор.

        Порядок: конструктор ``InstrumentService`` отклоняет недопустимые
        параметры типизированным ``InputError`` (прибор ещё не тронут, проба
        среды не вызвана); затем ``run_capture_preflight`` — BLOCK-findings
        прерывают старт до взятия ручки; WARN не блокирует. Отказ самого
        прибора при старте (например ``DeviceNotFoundError``) пробрасывается
        типизированно, гейт остаётся неактивным.
        """
        # Старый reaper глушим до блокировки: SINGLE-рестарт без stop не копит потоки.
        self._stop_reaper()
        with self._lock:
            if self.is_active:
                raise InputError("живой режим уже запущен: сначала stop")
            service = InstrumentService(
                scope_factory=self._scope_factory,
                trigger=config.trigger,
                sample_rate_hz=config.sample_rate_hz,
                ch1_range_v=config.ch1_range_v,
                ch1_probe_multiplier=config.ch1_probe_multiplier,
                frame_samples=self._frame_samples,
                max_buffered_blocks=self._max_buffered_blocks,
                discard_lead_samples=self._discard_lead_samples,
                clock=self._clock,
                cancellation_token=self._cancellation_token,
                adc_calibration=self._adc_calibration,
                poll_timeout_ms=self._poll_timeout_ms,
                continuity_basis=continuity_basis_for(self._mode.value),
            )
            blockers = self._blockers(config)
            if blockers:
                raise LivePreflightBlockedError(blockers)
            # SA-контур перезапускается вместе с захватом: кольцо пустое, конфигурация
            # сброшена (как триггер), подписка одна — кадры не задваиваются по стримам.
            self._spectrum.reset()
            service.subscribe(self._spectrum.offer)
            service.start()
            self._service = service
            stop_flag = Event()
            self._reaper_stop = stop_flag
            self._reaper = Thread(target=self._reap_loop, args=(stop_flag,), daemon=True)
            self._reaper.start()
            return service

    def stop(self) -> None:
        """Освобождает прибор: ``stop -> финальный кадр -> close_handle``; идемпотентно."""
        # reaper глушим до прибора: мёртвый потребитель — не повод потерять кадр.
        self._stop_reaper()
        with self._lock:
            if self._service is not None:
                self._service.stop()

    def require_device_free(self) -> None:
        """Гейт job-захвата: ``DeviceBusyError``, пока прибор держит вкладка."""
        if self.is_active:
            raise DeviceBusyError

    def _stop_reaper(self) -> None:
        """Глушит и джойнит reaper с ограниченным окном; сам себя поток не ждёт."""
        if self._reaper_stop is not None:
            self._reaper_stop.set()
        reaper = self._reaper
        if reaper is not None and reaper is not current_thread():
            reaper.join(timeout=2 * REAP_POLL_S)

    def _reap_loop(self, stop_flag: Event) -> None:
        """Контур reaper: раз в ``REAP_POLL_S`` проверяет простой потребителя."""
        while not stop_flag.wait(REAP_POLL_S):
            self._reap_check()

    def _reap_check(self) -> None:
        """Проверка: потребитель не опрашивал дольше порога — ``stop`` по контракту."""
        service = self._service
        if service is None or not service.is_running:
            return
        if self._clock() - service.last_poll_s > self._reap_after_s:
            self.stop()

    def _blockers(self, config: LiveStartConfig) -> tuple[PreflightFinding, ...]:
        findings = run_capture_preflight(
            self._preflight_request(config),
            self._environment_probe(),
        )
        return tuple(item for item in findings if item.severity is FindingSeverity.BLOCK)

    def _preflight_request(self, config: LiveStartConfig) -> CapturePreflightRequest:
        # Живой режим ничего не пишет на диск: горизонт capacity-проверки —
        # ограниченное RAM-кольцо сервиса (``max_buffered_blocks`` блоков прибора),
        # а не длительность сессии. Деление безопасно: частота уже проверена
        # конструктором ``InstrumentService`` (целые МГц 1..15).
        horizon_samples = self._max_buffered_blocks * BLOCK_SAMPLES_PER_CHANNEL
        return CapturePreflightRequest(
            session_root=self._session_root,
            session_type=SessionType.MEASUREMENT,
            channel_mode=ChannelMode.DUAL,
            ch1_setup=_LIVE_CH1_SETUP,
            sample_rate_hz=config.sample_rate_hz,
            duration_s=horizon_samples / config.sample_rate_hz,
            range_v=config.ch1_range_v,
            probe_multiplier=config.ch1_probe_multiplier,
            baseline_requested=False,
        )
