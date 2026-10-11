"""InstrumentService: единственный владелец ручки прибора в живом режиме.

Сервис держит один ``ScopeProtocol`` между ``start`` и ``stop`` и раздаёт кадры
подписчикам: обе живые вкладки (осциллограф и спектроанализатор) читают один
поток, переключение не перезапускает захват (issue #26). Контракт остановки —
``stop -> финальный кадр -> close_handle``: финальный кадр собирает остаток
буфера, а при пустом остатке кадра нет (данные не фабрикуются). Отмена
кооперативная: токен проверяется на границе ``poll`` и освобождает ручку без
финального кадра.

Кадры выдаёт владелец — сервис не спит и не заводит потоков: ``poll`` вызывает
тот, кто крутит контур (SSE-генератор или воркер вкладки). ``RLock`` нужен
только затем, чтобы ``stop`` из другого потока не разошёлся с выдачей кадра.
Preflight железа (``capture_preflight``) перед ``start`` — обязанность вызывающего.
"""

import time
from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Final, Protocol, cast

from lnt.acquire_validation import _range_code, _rate_code
from lnt.adc_calibration import AdcCalibration
from lnt.errors import InputError
from lnt.instrument.device import (
    block_to_volts,
    configure_scope,
    validated_poll_timeout_ms,
    validated_probe_multiplier,
)
from lnt.instrument.frames import (
    DEFAULT_FRAME_SAMPLES,
    DEFAULT_MAX_BUFFERED_BLOCKS,
    UNSTABLE_LEAD_SAMPLES,
    LiveFrame,
)
from lnt.instrument.stream import FrameStream
from lnt.instrument.trigger import TriggerConfig, TriggerMode
from lnt.scope_io import (
    BLOCK_SAMPLES,
    MAX_POLL_TIMEOUT_MS,
    NEVER_CANCELLED,
    OUTSTANDING_TRANSFERS,
    RANGE_CODE_5V,
    CancellationToken,
    ScopeProtocol,
)

Clock = Callable[[], float]
FrameSink = Callable[[LiveFrame], None]

# Дефолты живого режима совпадают с захватом сессии (``lnt.acquire``): 8 МГц в
# dual-режиме и диапазон CH1 +-5 В; CH2 всегда +-5 В (см. ``device``).
DEFAULT_SAMPLE_RATE_HZ: Final = 8_000_000.0
DEFAULT_CH1_RANGE_V: Final = 5.0


class InstrumentState(StrEnum):
    """Статус владения прибором: ручку не держим, держим, отпустили."""

    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"


class _StopEvent(Protocol):
    def set(self) -> None: ...


class InstrumentService:
    """Живой поток прибора: владение ручкой, софт edge-триггер, кадры подписчикам."""

    def __init__(  # noqa: PLR0913 - приборная панель: каждая ручка kw-only и с дефолтом
        self,
        *,
        scope_factory: Callable[[], ScopeProtocol],
        trigger: TriggerConfig,
        sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
        ch1_range_v: float = DEFAULT_CH1_RANGE_V,
        ch1_probe_multiplier: float = 1.0,
        frame_samples: int = DEFAULT_FRAME_SAMPLES,
        max_buffered_blocks: int = DEFAULT_MAX_BUFFERED_BLOCKS,
        discard_lead_samples: int = UNSTABLE_LEAD_SAMPLES,
        clock: Clock = time.monotonic,
        cancellation_token: CancellationToken = NEVER_CANCELLED,
        adc_calibration: AdcCalibration | None = None,
        poll_timeout_ms: int = MAX_POLL_TIMEOUT_MS,
    ) -> None:
        """Проверяет границы входа и запоминает конфигурацию; прибор не открывает."""
        self._scope_factory: Final = scope_factory
        self._sample_rate_hz: Final = sample_rate_hz
        self._rate_code: Final = _rate_code(sample_rate_hz)
        self._ch1_range_code: Final = _range_code(ch1_range_v)
        self._ch1_probe_multiplier: Final = validated_probe_multiplier(ch1_probe_multiplier)
        self._poll_timeout_ms: Final = validated_poll_timeout_ms(poll_timeout_ms)
        self._adc_calibration: Final = adc_calibration
        self._clock: Final = clock
        self._cancellation_token: Final = cancellation_token
        self._stream: Final = FrameStream(
            sample_rate_hz=sample_rate_hz,
            frame_samples=frame_samples,
            max_buffered_blocks=max_buffered_blocks,
            discard_lead_samples=discard_lead_samples,
        )
        self._lock: Final = RLock()
        self._sinks: list[FrameSink] = []
        self._pending: list[tuple[object, object]] = []
        self._scope: ScopeProtocol | None = None
        self._shutdown: _StopEvent | None = None
        self._trigger: TriggerConfig = trigger
        self._state: InstrumentState = InstrumentState.IDLE
        self._last_emit_s: float = 0.0

    @property
    def state(self) -> InstrumentState:
        """Статус владения прибором."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Ручка в нашем владении: между ``start`` и ``stop``."""
        return self._state is InstrumentState.RUNNING

    @property
    def trigger(self) -> TriggerConfig:
        """Действующая конфигурация софтверного триггера."""
        return self._trigger

    @property
    def sample_rate_hz(self) -> float:
        """Частота дискретизации живого потока."""
        return self._sample_rate_hz

    @property
    def frame_samples(self) -> int:
        """Длина окна кадра в отсчётах на канал."""
        return self._stream.frame_samples

    @property
    def calibration_used(self) -> bool:
        """Провенанс вольт кадра: True только когда передана per-device таблица."""
        return self._adc_calibration is not None

    def subscribe(self, on_frame: FrameSink) -> Callable[[], None]:
        """Подписывает на кадры; возвращает функцию отписки."""
        with self._lock:
            self._sinks.append(on_frame)

        def detach() -> None:
            with self._lock:
                self._sinks = [sink for sink in self._sinks if sink is not on_frame]

        return detach

    def start(self) -> None:
        """Берёт ручку прибора, настраивает тракт и запускает непрерывный захват."""
        with self._lock:
            if self._state is InstrumentState.RUNNING:
                raise InputError("живой режим уже запущен: сначала stop")
            scope = self._scope_factory()
            armed = False
            try:
                configure_scope(
                    scope,
                    rate_code=self._rate_code,
                    ch1_range_code=self._ch1_range_code,
                )
                self._shutdown = cast(
                    "_StopEvent",
                    scope.read_async(
                        self._on_block,
                        BLOCK_SAMPLES,
                        OUTSTANDING_TRANSFERS,
                        raw=True,
                    ),
                )
                scope.start_capture()
                armed = True
            finally:
                if not armed:
                    # Отказ старта не должен оставлять ручку и поток колбэков.
                    if self._shutdown is not None:
                        self._shutdown.set()
                    self._shutdown = None
                    scope.close_handle()
            self._scope = scope
            self._stream.reset()
            self._pending.clear()
            self._last_emit_s = self._clock()
            self._state = InstrumentState.RUNNING

    def poll(self) -> int:
        """Один шаг владельца: опрос прибора, сборка кадров; возврат — число кадров."""
        with self._lock:
            scope = self._require_scope("poll")
            if self._cancellation_token.is_cancelled():
                self._release(emit_final=False)
                return 0
            scope.poll(self._poll_timeout_ms)
            self._absorb_blocks()
            return self._emit_ready()

    def stop(self) -> None:
        """Контракт остановки: финальный кадр из остатка буфера, затем ``close_handle``."""
        with self._lock:
            if self._state is not InstrumentState.RUNNING:
                return
            self._release(emit_final=True)

    def update_trigger(self, trigger: TriggerConfig) -> None:
        """Меняет триггер на ходу: захват не перезапускается, буфер не перематывается."""
        with self._lock:
            self._require_scope("update_trigger")
            self._trigger = trigger

    def _require_scope(self, action: str) -> ScopeProtocol:
        scope = self._scope
        if self._state is not InstrumentState.RUNNING or scope is None:
            raise InputError(f"живой режим не запущен: {action} до start")
        return scope

    def _on_block(self, ch1_raw: object, ch2_raw: object) -> None:
        """Колбэк ``read_async``: блок ждёт следующего ``poll`` в очереди."""
        self._pending.append((ch1_raw, ch2_raw))

    def _absorb_blocks(self) -> None:
        pending, self._pending = self._pending, []
        for ch1_raw, ch2_raw in pending:
            ch1 = block_to_volts(
                ch1_raw,
                range_code=self._ch1_range_code,
                probe_multiplier=self._ch1_probe_multiplier,
                calibration=self._adc_calibration,
            )
            ch2 = block_to_volts(
                ch2_raw, range_code=RANGE_CODE_5V, calibration=self._adc_calibration
            )
            self._stream.push(ch1, ch2)

    def _emit_ready(self) -> int:
        trigger = self._trigger
        now_s = self._clock()
        sweep = (
            trigger.mode is TriggerMode.AUTO and now_s - self._last_emit_s >= trigger.auto_timeout_s
        )
        frames = self._stream.emit(trigger, now_s=now_s, sweep=sweep)
        if not frames:
            return 0
        self._last_emit_s = now_s
        for frame in frames:
            self._publish(frame)
        if frames[-1].triggered and trigger.mode is TriggerMode.SINGLE:
            self._release(emit_final=False)
        return len(frames)

    def _publish(self, frame: LiveFrame) -> None:
        for sink in tuple(self._sinks):
            sink(frame)

    def _release(self, *, emit_final: bool) -> None:
        """Отдаёт финальный кадр (если попрошен) и освобождает ручку прибора."""
        if emit_final:
            frame = self._stream.flush(now_s=self._clock())
            if frame is not None:
                self._publish(frame)
        scope = self._scope
        shutdown = self._shutdown
        self._scope = None
        self._shutdown = None
        self._state = InstrumentState.STOPPED
        if scope is None:
            return
        scope.stop_capture()
        if shutdown is not None:
            shutdown.set()
        scope.close_handle()
