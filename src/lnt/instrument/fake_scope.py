"""Фейк-прибор Hantek 6022BE для живого режима: кадры из ``lnt.signals``.

Полный ``ScopeProtocol`` без драйвера и USB: блоки уходят в колбэк
``read_async`` с детерминированным кадровым каденсом по ИНЖЕКТИРУЕМЫМ часам
(``ManualClock``) — тесты не зависят от ``time.sleep``. Отсчёты raw uint8,
кадр интерлейсный (ch1/ch2) как на железе. Кольцо отсчётов собирается
в ``start_capture`` по текущей конфигурации: частота, диапазоны, профиль.
Ручки конструктора kw-only с дефолтами, поэтому класс годится фабрикой
``scope_factory`` для ``lnt.acquire.capture_session``.
"""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from lnt.acquire_validation import MAX_DUAL_RATE_MHZ, MEGA
from lnt.adc_calibration import ADC_CENTER, VOLTS_SCALE
from lnt.errors import InputError
from lnt.scope_io import (
    BLOCK_SAMPLES_PER_CHANNEL,
    CHANNEL_COUNT,
    MAX_POLL_TIMEOUT_MS,
    NEVER_CANCELLED,
    RANGE_CODE_5V,
    CancellationToken,
    RawCallback,
)
from lnt.signals import PROFILES, generate

Clock = Callable[[], float]
MIN_POLL_TIMEOUT_MS = 1
RAW_MAX = 255


@dataclass(slots=True)
class ManualClock:
    """Инжектируемое время: ``now_s`` двигает владелец, а не реальный ``sleep``.

    ``stride_s`` — свободный ход (шаг на каждое чтение) для прогона через
    ``run_capture``, где часы прибора никто не двигает вручную.
    """

    now_s: float = 0.0
    stride_s: float = 0.0

    def __call__(self) -> float:
        """Отдаёт текущий момент и двигает время на ``stride_s``."""
        moment = self.now_s
        self.now_s += self.stride_s
        return moment

    def advance(self, delta_s: float) -> float:
        """Двигает время вперёд и возвращает новый момент; назад — ``InputError``."""
        if delta_s < 0.0:
            raise InputError(f"фейк-часы: шаг {delta_s} с не может быть отрицательным")
        self.now_s += delta_s
        return self.now_s


def _quantize(volts: NDArray[np.float32], range_code: int) -> NDArray[np.uint8]:
    # Вольты -> raw uint8 обратной формулой adc_calibration (без per-device поправки).
    if range_code < 1:
        raise InputError(f"фейк-прибор: код диапазона {range_code} должен быть >= 1")
    scale = VOLTS_SCALE / float(range_code << 7)
    counts = np.rint(volts.astype(np.float64) / scale + ADC_CENTER)
    return np.clip(counts, 0.0, float(RAW_MAX)).astype(np.uint8)


class FakeHantekScope:
    """Фейк-прибор живого режима: ``ScopeProtocol`` и детерминированный каденс."""

    def __init__(  # noqa: PLR0913 - приборная панель: каждая ручка kw-only и с дефолтом
        self,
        *,
        profile: str = "bad",
        seed: int = 20261011,
        sample_rate_hz: float | None = None,
        clock: Clock | None = None,
        cancellation_token: CancellationToken = NEVER_CANCELLED,
        buffer_blocks: int = 8,
        is_device_firmware_present: bool = True,
    ) -> None:
        """Проверяет ручки генератора и запоминает конфигурацию прибора."""
        if profile not in PROFILES:
            known = ", ".join(sorted(PROFILES))
            raise InputError(f"фейк-прибор: неизвестный profile {profile!r}; доступны: {known}")
        if seed < 0:
            raise InputError(f"фейк-прибор: seed {seed} должен быть неотрицательным")
        if buffer_blocks < 1:
            raise InputError(f"фейк-прибор: buffer_blocks {buffer_blocks} должен быть >= 1")
        rate_ok = sample_rate_hz is None or (math.isfinite(sample_rate_hz) and sample_rate_hz > 0.0)
        if not rate_ok:
            raise InputError(f"фейк-прибор: sample_rate_hz {sample_rate_hz} недопустима")
        self.is_device_firmware_present: bool = is_device_firmware_present
        self.cancellation_token: CancellationToken = cancellation_token
        self.sample_rate_hz: float | None = sample_rate_hz
        # calls — жизненный цикл прибора (setup/open/read/start/stop/close),
        # конфигурация драйвера видна в атрибутах ниже.
        self.calls: list[str] = []
        self.poll_timeouts: list[int] = []
        self.block_times: list[float] = []
        self.blocks_emitted: int = 0
        self.interface: int | None = None
        self.channel_count: int | None = None
        self.rate_code: int | None = None
        self.ch1_range_code: int = RANGE_CODE_5V
        self.ch2_range_code: int = RANGE_CODE_5V
        self.is_open: bool = False
        self.is_capturing: bool = False
        self._profile: str = profile
        self._seed: int = seed
        self._buffer_blocks: int = buffer_blocks
        self._clock: Clock = clock if clock is not None else time.monotonic
        self._callback: RawCallback | None = None
        self._shutdown: threading.Event | None = None
        self._outstanding: int = 1
        self._per_channel: int = BLOCK_SAMPLES_PER_CHANNEL
        self._origin_s: float = 0.0
        self._ch1_ring: NDArray[np.uint8] = np.empty(0, dtype=np.uint8)
        self._ch2_ring: NDArray[np.uint8] = np.empty(0, dtype=np.uint8)

    @property
    def expected_block_interval_s(self) -> float:
        """Период кадра: ``BLOCK_SAMPLES_PER_CHANNEL / sample_rate_hz``."""
        return BLOCK_SAMPLES_PER_CHANNEL / self._require_rate_hz()

    def setup(self) -> bool:
        """Моделирует успешную инициализацию драйвера."""
        self.calls.append("setup")
        return True

    def open_handle(self) -> bool:
        """Открывает «устройство»: фейк всегда на месте."""
        self.calls.append("open_handle")
        self.is_open = True
        return True

    def close_handle(self) -> bool:
        """Закрывает ручку и гасит захват."""
        self.calls.append("close_handle")
        self.is_open = False
        self.is_capturing = False
        return True

    def flash_firmware(self) -> bool:
        """«Прошивает» прибор: после прошивки флаг прошивки взведён."""
        self.calls.append("flash_firmware")
        self.is_device_firmware_present = True
        return True

    def set_interface(self, index: int, /) -> bool:
        """Запоминает alt-setting интерфейса (0 = bulk)."""
        self.interface = index
        return True

    def set_num_channels(self, count: int, /) -> bool:
        """Запоминает число каналов; кадр фейка всегда интерлейсный ch1/ch2."""
        self.channel_count = count
        return True

    def set_sample_rate(self, code: int, /) -> bool:
        """Код частоты драйвера (целые МГц) задаёт каденс кадров."""
        if not 1 <= code <= MAX_DUAL_RATE_MHZ:
            raise InputError(f"фейк-прибор: код частоты {code} вне 1..{MAX_DUAL_RATE_MHZ} МГц")
        derived_hz = float(code) * MEGA
        if self.sample_rate_hz is not None and self.sample_rate_hz != derived_hz:
            raise InputError(
                f"фейк-прибор: код {code} != sample_rate_hz {self.sample_rate_hz:.0f} Гц",
            )
        self.rate_code = code
        self.sample_rate_hz = derived_hz
        return True

    def set_ch1_voltage_range(self, code: int, /) -> bool:
        """Код диапазона CH1: определяет масштаб квантования raw."""
        self.ch1_range_code = code
        return True

    def set_ch2_voltage_range(self, code: int, /) -> bool:
        """Код диапазона CH2: определяет масштаб квантования raw."""
        self.ch2_range_code = code
        return True

    def read_async(
        self,
        callback: RawCallback,
        data_size: int,
        outstanding_transfers: int,
        *,
        raw: bool,
    ) -> threading.Event:
        """Регистрирует колбэк блоков и возвращает событие остановки потока."""
        self.calls.append("read_async")
        if not raw:
            raise InputError("фейк-прибор отдаёт только raw-отсчёты uint8 (raw=True)")
        if data_size < CHANNEL_COUNT:
            raise InputError(f"фейк-прибор: data_size {data_size} меньше кадра на канал")
        if outstanding_transfers < 1:
            raise InputError(f"фейк-прибор: outstanding_transfers {outstanding_transfers} < 1")
        self._callback = callback
        self._per_channel = data_size // CHANNEL_COUNT
        self._outstanding = outstanding_transfers
        self._shutdown = threading.Event()
        return self._shutdown

    def start_capture(self) -> bool:
        """Собирает кольцо отсчётов по текущей конфигурации и обнуляет каденс."""
        self.calls.append("start_capture")
        if not self.is_open:
            raise InputError("фейк-прибор: start_capture до open_handle")
        if self._callback is None:
            raise InputError("фейк-прибор: start_capture до read_async")
        rate_hz = self._require_rate_hz()
        samples = self._buffer_blocks * self._per_channel
        session = generate(
            profile=self._profile,
            duration_s=samples / rate_hz,
            sample_rate_hz=rate_hz,
            rng=np.random.default_rng(self._seed),
        )
        self._ch1_ring = _quantize(session.ch1, self.ch1_range_code)
        self._ch2_ring = _quantize(session.ch2, self.ch2_range_code)
        self._origin_s = self._clock()
        self.blocks_emitted = 0
        self.block_times = []
        self.is_capturing = True
        return True

    def stop_capture(self) -> bool:
        """Останавливает каденс; счётчики отданных кадров сохраняются."""
        self.calls.append("stop_capture")
        self.is_capturing = False
        return True

    def poll(self, timeout_ms: int, /) -> int:
        """Отдаёт просроченные кадры: не больше ``outstanding_transfers`` за вызов."""
        # Фейк не спит: окно timeout_ms только проверяется (1..250 мс как у драйвера),
        # время приходит из инжектируемых часов; возврат — число отданных блоков.
        if not MIN_POLL_TIMEOUT_MS <= timeout_ms <= MAX_POLL_TIMEOUT_MS:
            raise ValueError(
                f"poll timeout must be in {MIN_POLL_TIMEOUT_MS}..{MAX_POLL_TIMEOUT_MS} ms",
            )
        self.poll_timeouts.append(timeout_ms)
        shutdown = self._shutdown
        if not self.is_capturing or shutdown is None or shutdown.is_set():
            return 0
        if self.cancellation_token.is_cancelled():
            return 0
        now_s = self._clock()
        delivered = 0
        while delivered < self._outstanding:
            # Срок кадра N: origin + (N + 1) * expected_block_interval_s.
            due_s = self._origin_s + (self.blocks_emitted + 1) * self.expected_block_interval_s
            if due_s > now_s:
                break
            self._emit_block(now_s)
            delivered += 1
        return delivered

    def _require_rate_hz(self) -> float:
        rate_hz = self.sample_rate_hz
        if rate_hz is None:
            raise InputError("фейк-прибор: частота не задана (sample_rate_hz или set_sample_rate)")
        return rate_hz

    def _emit_block(self, now_s: float) -> None:
        callback = self._callback
        if callback is None:
            raise InputError("фейк-прибор: кадр без колбэка read_async")
        start = (self.blocks_emitted * self._per_channel) % self._ch1_ring.size
        stop = start + self._per_channel
        # Кадр провода: чётные байты CH1, нечётные CH2; колбэк драйвера получает
        # уже разнесённые каналы (контракт lnt.scope_io.RawCallback).
        frame = np.empty(self._per_channel * CHANNEL_COUNT, dtype=np.uint8)
        frame[0::2] = self._ch1_ring[start:stop]
        frame[1::2] = self._ch2_ring[start:stop]
        callback(bytearray(frame[0::2].tobytes()), bytearray(frame[1::2].tobytes()))
        self.blocks_emitted += 1
        self.block_times.append(now_s)
