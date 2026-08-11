"""I/O-слой Hantek 6022BE: протокол драйвера, сбор блоков, цикл захвата.

Код перенесён из acquire.py без изменения семантики (гейт <=250 строк);
сигнатуры драйвера — из репо-дайва Ho-Ro/Hantek6022API@e65d52b. Драйвер
импортируется лениво: без библиотеки и устройства всё сводится к
``DeviceNotFoundError`` (exit 3).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from lnt.errors import DeviceNotFoundError
from lnt.types import AcquisitionTelemetry

RawCallback = Callable[[object, object], None]

RANGE_CODE_5V = 1
RAW_LOW = 0
RAW_HIGH = 255
BLOCK_SAMPLES = 65_536
CHANNEL_COUNT = 2
BLOCK_SAMPLES_PER_CHANNEL = BLOCK_SAMPLES // CHANNEL_COUNT
OUTSTANDING_TRANSFERS = 10
STALL_TIMEOUT_EXTRA_S = 2.0
MAX_POLL_TIMEOUT_MS: Final = 250


@dataclass(frozen=True, slots=True)
class CancellationToken:
    """Cooperative cancellation query, safe to call at poll boundaries."""

    is_cancelled: Callable[[], bool] = lambda: False


@dataclass(frozen=True, slots=True)
class CancelledResult:
    """Typed acknowledgement that acquisition stopped without a session."""


NEVER_CANCELLED: Final = CancellationToken()


class ScopeProtocol(Protocol):
    """Протокол устройства: зеркало API ``PyHT6022.LibUsbScope.Oscilloscope``.

    Параметры позиционные (``/``), возвраты ``object``: у реального драйвера
    свои имена аргументов (``alt``, ``rate_index``) и bool-возвраты, у фейков
    тестов — свои; протокол обязан покрывать обоих структурно.
    """

    is_device_firmware_present: bool

    def setup(self) -> object: ...
    def open_handle(self) -> object: ...
    def close_handle(self) -> object: ...
    def flash_firmware(self) -> object: ...
    def set_interface(self, index: int, /) -> object: ...
    def set_num_channels(self, count: int, /) -> object: ...
    def set_sample_rate(self, code: int, /) -> object: ...
    def set_ch1_voltage_range(self, code: int, /) -> object: ...
    def set_ch2_voltage_range(self, code: int, /) -> object: ...
    def read_async(
        self,
        callback: RawCallback,
        data_size: int,
        outstanding_transfers: int,
        *,
        raw: bool,
    ) -> object: ...
    def start_capture(self) -> object: ...
    def stop_capture(self) -> object: ...
    def poll(self, timeout_ms: int, /) -> object:
        """Handle events for at most ``timeout_ms`` (1..250 ms)."""
        ...


class _ShutdownEvent(Protocol):
    def set(self) -> None: ...


@dataclass(slots=True)
class _BlockCollector:
    ch1_blocks: list[NDArray[np.uint8]] = field(default_factory=list)
    ch2_blocks: list[NDArray[np.uint8]] = field(default_factory=list)
    callback_times: list[float] = field(default_factory=list)
    total_samples: int = 0

    def on_block(self, ch1_raw: object, ch2_raw: object) -> None:
        ch1 = np.frombuffer(bytes(cast("bytearray", ch1_raw)), dtype=np.uint8)
        ch2 = np.frombuffer(bytes(cast("bytearray", ch2_raw)), dtype=np.uint8)
        self.ch1_blocks.append(ch1)
        self.ch2_blocks.append(ch2)
        self.callback_times.append(time.monotonic())
        self.total_samples += ch1.size


def open_real_scope() -> ScopeProtocol:
    """Лениво импортирует драйвер; его отсутствие -> ``DeviceNotFoundError``."""
    try:
        from PyHT6022.LibUsbScope import Oscilloscope  # noqa: PLC0415
    except ImportError as exc:
        raise DeviceNotFoundError(
            "драйвер hantek6022api не установлен: pip install 'lnt[hantek]' (см. README)",
        ) from exc
    driver = cast("_HantekDriver", cast("object", Oscilloscope()))
    return cast("ScopeProtocol", cast("object", _HantekScope(driver)))


class _UsbContext(Protocol):
    def handleEventsTimeout(self, timeout_s: float, /) -> None: ...  # noqa: N802


class _HantekDriver(Protocol):
    context: _UsbContext


class _HantekScope:
    """Pinned Hantek adapter replacing its implicit libusb timeout with an explicit bound."""

    def __init__(self, driver: _HantekDriver) -> None:
        self._driver: _HantekDriver = driver

    def __getattr__(self, name: str) -> object:
        return getattr(self._driver, name)

    def poll(self, timeout_ms: int, /) -> None:
        _poll_hantek(self._driver, timeout_ms)


def _poll_hantek(driver: _HantekDriver, timeout_ms: int) -> None:
    """Use libusb's explicit timeout; the pinned driver's ``poll`` hides its bound."""
    if not 1 <= timeout_ms <= MAX_POLL_TIMEOUT_MS:
        raise ValueError("poll timeout must be in 1..250 ms")
    driver.context.handleEventsTimeout(timeout_ms / 1_000)


def _configure_scope(scope: ScopeProtocol, rate_code: int, ch1_range_code: int) -> None:
    scope.setup()
    if not scope.open_handle():
        raise DeviceNotFoundError("Hantek 6022BE не найден (open_handle не удался)")
    if not scope.is_device_firmware_present:
        scope.flash_firmware()
    # Bulk (alt 0), не iso: WinUSB отверг iso-transfer.submit() на железе
    # 2026-07-26 (LIBUSB_ERROR_INVALID_PARAM); bulk на FX2 держит 16 МБ/с.
    scope.set_interface(0)
    scope.set_num_channels(CHANNEL_COUNT)
    scope.set_sample_rate(rate_code)
    scope.set_ch1_voltage_range(ch1_range_code)
    scope.set_ch2_voltage_range(RANGE_CODE_5V)


def run_capture(  # noqa: PLR0913 - backend contract keeps acquisition settings explicit
    scope: ScopeProtocol,
    *,
    rate_code: int,
    ch1_range_code: int,
    sample_rate_hz: float,
    requested_samples: int,
    cancellation_token: CancellationToken = NEVER_CANCELLED,
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], AcquisitionTelemetry] | CancelledResult:
    """Гонит поток до ``requested_samples``; возвращает raw-каналы и телеметрию.

    Ошибки драйвера (``usb1.*``) отображаются в ``DeviceNotFoundError``:
    контракт CLI — exit 3 одной строкой, без traceback.
    """
    try:
        return _stream_capture(
            scope,
            rate_code=rate_code,
            ch1_range_code=ch1_range_code,
            sample_rate_hz=sample_rate_hz,
            requested_samples=requested_samples,
            cancellation_token=cancellation_token,
        )
    except Exception as exc:
        if type(exc).__module__.partition(".")[0] == "usb1":
            raise DeviceNotFoundError(f"USB-ошибка драйвера: {exc}") from exc
        raise


def _stream_capture(  # noqa: PLR0913 - mirrors the public backend contract
    scope: ScopeProtocol,
    *,
    rate_code: int,
    ch1_range_code: int,
    sample_rate_hz: float,
    requested_samples: int,
    cancellation_token: CancellationToken,
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], AcquisitionTelemetry] | CancelledResult:
    collector = _BlockCollector()
    if cancellation_token.is_cancelled():
        return CancelledResult()
    try:
        _configure_scope(scope, rate_code, ch1_range_code)
        shutdown = cast(
            "_ShutdownEvent",
            scope.read_async(collector.on_block, BLOCK_SAMPLES, OUTSTANDING_TRANSFERS, raw=True),
        )
        try:
            scope.start_capture()
            deadline = time.monotonic() + requested_samples / sample_rate_hz + STALL_TIMEOUT_EXTRA_S
            while collector.total_samples < requested_samples:
                if cancellation_token.is_cancelled():
                    return CancelledResult()
                scope.poll(MAX_POLL_TIMEOUT_MS)
                if time.monotonic() > deadline:
                    raise DeviceNotFoundError(
                        f"поток прервался: {collector.total_samples}/{requested_samples} отсчётов",
                    )
        finally:
            scope.stop_capture()
            shutdown.set()
    finally:
        scope.close_handle()
    ch1 = np.concatenate(collector.ch1_blocks)[:requested_samples]
    ch2 = np.concatenate(collector.ch2_blocks)[:requested_samples]
    block_lengths = tuple(int(block.size) for block in collector.ch1_blocks)
    gaps = tuple(float(gap) for gap in np.diff(np.asarray(collector.callback_times)))
    ch1_clip_low, ch1_clip_high = _clip_counts(ch1)
    ch2_clip_low, ch2_clip_high = _clip_counts(ch2)
    telemetry = AcquisitionTelemetry(
        requested_samples=requested_samples,
        captured_samples=collector.total_samples,
        callback_count=len(collector.callback_times),
        block_lengths=block_lengths,
        callback_gaps_s=gaps,
        expected_block_interval_s=BLOCK_SAMPLES_PER_CHANNEL / sample_rate_hz,
        short_block_count=sum(1 for length in block_lengths if length < BLOCK_SAMPLES_PER_CHANNEL),
        ch1_clip_low_count=ch1_clip_low,
        ch1_clip_high_count=ch1_clip_high,
        ch2_clip_low_count=ch2_clip_low,
        ch2_clip_high_count=ch2_clip_high,
        calibration_used=False,
    )
    return ch1, ch2, telemetry


def _clip_counts(raw: NDArray[np.uint8]) -> tuple[int, int]:
    return (
        int(np.count_nonzero(raw == RAW_LOW)),
        int(np.count_nonzero(raw == RAW_HIGH)),
    )
