"""Фейк-прибор живого режима: протокол, кадры и детерминированный каденс.

Время инжектируется (``ManualClock``): ни один тест не спит и не зависит от
реальной длительности ``poll``. Границы кадра берутся из ``lnt.scope_io``
(``BLOCK_SAMPLES`` = 65536 = 2 × 32768 на канал), сигнал — из ``lnt.signals``.
"""

import threading
from dataclasses import dataclass, field

import numpy as np
import pytest

from lnt.errors import InputError
from lnt.instrument import FakeHantekScope, ManualClock
from lnt.scope_io import (
    BLOCK_SAMPLES,
    BLOCK_SAMPLES_PER_CHANNEL,
    MAX_POLL_TIMEOUT_MS,
    NEVER_CANCELLED,
    RANGE_CODE_5V,
    CancellationToken,
    CancelledResult,
    ScopeProtocol,
    run_capture,
)

# 2**20 Гц: интервал кадра 32768/2**20 = 0.03125 с — точная двоичная сетка,
# поэтому границы «ровно в срок» проверяются без допуска на последний ulp.
RATE_HZ = 1_048_576.0
CADENCE_S = BLOCK_SAMPLES_PER_CHANNEL / RATE_HZ
DEVICE_RATE_HZ = 8_000_000.0
DEVICE_RATE_CODE = 8
SEED = 2026
ADC_MID = 128


@dataclass(slots=True)
class _Recorder:
    """Принимает пары каналов из ``read_async`` — зеркало ``_BlockCollector``."""

    frames: list[tuple[bytearray, bytearray]] = field(default_factory=list)

    def on_block(self, ch1: object, ch2: object) -> None:
        assert isinstance(ch1, bytearray)
        assert isinstance(ch2, bytearray)
        self.frames.append((ch1, ch2))

    def channel(self, index: int, frame: int = 0) -> np.ndarray:
        return np.frombuffer(bytes(self.frames[frame][index]), dtype=np.uint8)


@dataclass(slots=True)
class _Armed:
    scope: FakeHantekScope
    recorder: _Recorder
    clock: ManualClock
    shutdown: threading.Event


def _armed(
    *,
    clock: ManualClock | None = None,
    sample_rate_hz: float = RATE_HZ,
    profile: str = "bad",
    seed: int = SEED,
    ch1_range_code: int = RANGE_CODE_5V,
    outstanding_transfers: int = 10,
    buffer_blocks: int = 8,
    data_size: int = BLOCK_SAMPLES,
    cancellation_token: CancellationToken = NEVER_CANCELLED,
) -> _Armed:
    """Проводит фейк по конфигурационному пути драйвера и запускает каденс."""
    used_clock = clock if clock is not None else ManualClock()
    scope = FakeHantekScope(
        profile=profile,
        seed=seed,
        sample_rate_hz=sample_rate_hz,
        clock=used_clock,
        buffer_blocks=buffer_blocks,
        cancellation_token=cancellation_token,
    )
    recorder = _Recorder()
    assert scope.setup() is True
    assert scope.open_handle() is True
    scope.set_interface(0)
    scope.set_num_channels(2)
    scope.set_ch1_voltage_range(ch1_range_code)
    scope.set_ch2_voltage_range(RANGE_CODE_5V)
    shutdown = scope.read_async(recorder.on_block, data_size, outstanding_transfers, raw=True)
    assert scope.start_capture() is True
    return _Armed(scope=scope, recorder=recorder, clock=used_clock, shutdown=shutdown)


def _pump(armed: _Armed, frames: int) -> list[int]:
    """Двигает часы ровно на кадр и поллит: по одному блоку за вызов ``poll``."""
    delivered: list[int] = []
    for _ in range(frames):
        armed.clock.advance(armed.scope.expected_block_interval_s)
        delivered.append(armed.scope.poll(MAX_POLL_TIMEOUT_MS))
    return delivered


def test_manual_clock_moves_only_when_the_test_moves_it() -> None:
    clock = ManualClock()

    assert clock() == 0.0
    assert clock() == 0.0
    assert clock.advance(1.5) == 1.5
    assert clock() == 1.5

    with pytest.raises(InputError):
        clock.advance(-0.5)


def test_manual_clock_stride_free_runs_without_sleep() -> None:
    clock = ManualClock(now_s=10.0, stride_s=0.25)

    assert [clock(), clock(), clock()] == [10.0, 10.25, 10.5]


def test_fake_covers_the_whole_scope_protocol_surface() -> None:
    # Аннотация — статическая проверка соответствия протоколу (basedpyright).
    scope: ScopeProtocol = FakeHantekScope(clock=ManualClock())
    declared = {name for name in dir(ScopeProtocol) if not name.startswith("_")}
    declared |= set(ScopeProtocol.__annotations__)

    assert {"poll", "read_async", "is_device_firmware_present"} <= declared
    assert sorted(name for name in declared if not hasattr(scope, name)) == []
    assert scope.is_device_firmware_present is True


def test_configuration_calls_reach_the_fake() -> None:
    scope = FakeHantekScope(clock=ManualClock(), is_device_firmware_present=False)

    assert scope.setup() is True
    assert scope.open_handle() is True
    assert scope.is_open is True
    assert scope.flash_firmware() is True
    assert scope.is_device_firmware_present is True
    assert scope.set_interface(0) is True
    assert scope.set_num_channels(2) is True
    assert scope.set_sample_rate(DEVICE_RATE_CODE) is True
    assert scope.set_ch1_voltage_range(5) is True
    assert scope.set_ch2_voltage_range(RANGE_CODE_5V) is True

    assert scope.calls == ["setup", "open_handle", "flash_firmware"]
    assert (scope.interface, scope.channel_count, scope.rate_code) == (0, 2, DEVICE_RATE_CODE)
    assert (scope.ch1_range_code, scope.ch2_range_code) == (5, RANGE_CODE_5V)


def test_frames_arrive_exactly_on_the_expected_cadence() -> None:
    armed = _armed()

    assert armed.scope.expected_block_interval_s == CADENCE_S == 0.03125
    assert armed.scope.blocks_emitted == 0
    # До первого срока кадр не отдаётся, сколько ни поллить.
    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 0
    armed.clock.advance(CADENCE_S / 2)
    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 0
    assert armed.recorder.frames == []

    armed.clock.advance(CADENCE_S / 2)
    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 1
    # Скачок часов на три интервала — три просроченных кадра одним вызовом.
    armed.clock.advance(3 * CADENCE_S)
    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 3

    assert armed.scope.blocks_emitted == 4
    assert armed.scope.block_times == [CADENCE_S, 4 * CADENCE_S, 4 * CADENCE_S, 4 * CADENCE_S]
    assert armed.scope.is_capturing is True

    armed.scope.stop_capture()
    assert armed.scope.is_capturing is False
    armed.clock.advance(10 * CADENCE_S)
    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 0
    assert armed.scope.blocks_emitted == 4


def test_poll_caps_catch_up_at_outstanding_transfers() -> None:
    armed = _armed(outstanding_transfers=3)

    armed.clock.advance(100 * CADENCE_S)

    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 3
    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 3
    assert armed.scope.blocks_emitted == 6
    assert len(armed.recorder.frames) == 6


def test_frame_carries_two_uint8_channels_of_half_the_data_size() -> None:
    armed = _armed()

    assert _pump(armed, 1) == [1]
    ch1_raw, ch2_raw = armed.recorder.frames[0]

    assert isinstance(ch1_raw, bytearray)
    assert isinstance(ch2_raw, bytearray)
    assert len(ch1_raw) == len(ch2_raw) == BLOCK_SAMPLES_PER_CHANNEL == 32_768
    assert len(ch1_raw) + len(ch2_raw) == BLOCK_SAMPLES
    ch1 = armed.recorder.channel(0)
    ch2 = armed.recorder.channel(1)
    assert ch1.dtype == np.uint8
    assert ch2.dtype == np.uint8
    assert ch1.size == ch2.size == BLOCK_SAMPLES_PER_CHANNEL


def test_channels_carry_the_synthetic_mains_picture() -> None:
    armed = _armed(profile="bad")

    assert _pump(armed, 1) == [1]
    ch1 = armed.recorder.channel(0)
    ch2 = armed.recorder.channel(1)

    # CH2 — 50 Гц ±3 В на 5 В диапазоне: ±75 LSB вокруг середины шкалы.
    assert float(ch2.std()) > 20.0
    assert int(ch2.min()) < ADC_MID - 40
    assert int(ch2.max()) > ADC_MID + 40
    # CH1 — ВЧ-картина пробника: иголки есть, но размах на порядок меньше.
    assert np.unique(ch1).size > 1
    assert float(ch1.std()) < float(ch2.std())


def test_ch1_range_code_rescales_the_raw_counts() -> None:
    wide = _armed(profile="bad", ch1_range_code=1)
    narrow = _armed(profile="bad", ch1_range_code=10)

    assert _pump(wide, 1) == [1]
    assert _pump(narrow, 1) == [1]
    wide_std = float(wide.recorder.channel(0).std())
    narrow_std = float(narrow.recorder.channel(0).std())

    assert wide.recorder.channel(0).tobytes() != narrow.recorder.channel(0).tobytes()
    # Код 10 = 0.5 В против 5 В: масштаб raw растёт в 10 раз (клиппинга нет).
    assert narrow_std > 4.0 * wide_std
    assert int(narrow.recorder.channel(0).max()) <= 255


def test_same_seed_repeats_the_stream_byte_for_byte() -> None:
    first = _armed(seed=5)
    second = _armed(seed=5)
    other = _armed(seed=6)

    assert _pump(first, 3) == [1, 1, 1]
    assert _pump(second, 3) == [1, 1, 1]
    assert _pump(other, 3) == [1, 1, 1]

    assert first.recorder.frames == second.recorder.frames
    assert first.recorder.frames != other.recorder.frames


def test_ring_wraps_after_the_configured_number_of_frames() -> None:
    armed = _armed(buffer_blocks=2)

    assert _pump(armed, 3) == [1, 1, 1]
    frames = armed.recorder.frames

    assert frames[1] != frames[0]
    assert frames[2] == frames[0]


def test_cancellation_token_stops_the_cadence() -> None:
    state = {"cancelled": False}
    armed = _armed(cancellation_token=CancellationToken(lambda: state["cancelled"]))

    assert _pump(armed, 2) == [1, 1]
    state["cancelled"] = True
    armed.clock.advance(10 * CADENCE_S)

    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 0
    assert armed.scope.blocks_emitted == 2
    assert armed.scope.is_capturing is True


def test_shutdown_event_stops_the_cadence() -> None:
    armed = _armed()

    assert _pump(armed, 1) == [1]
    armed.shutdown.set()
    armed.clock.advance(10 * CADENCE_S)

    assert armed.scope.poll(MAX_POLL_TIMEOUT_MS) == 0
    assert armed.scope.blocks_emitted == 1


@pytest.mark.parametrize("timeout_ms", [0, -1, 251, 1000])
def test_poll_rejects_timeout_outside_the_driver_window(timeout_ms: int) -> None:
    scope = FakeHantekScope(clock=ManualClock(), sample_rate_hz=RATE_HZ)

    with pytest.raises(ValueError, match=r"1\.\.250"):
        scope.poll(timeout_ms)


@pytest.mark.parametrize("timeout_ms", [1, 250])
def test_poll_accepts_the_driver_window_bounds(timeout_ms: int) -> None:
    scope = FakeHantekScope(clock=ManualClock(), sample_rate_hz=RATE_HZ)

    assert scope.poll(timeout_ms) == 0
    assert scope.poll_timeouts == [timeout_ms]


def test_rate_code_from_the_capture_flow_sets_the_cadence() -> None:
    scope = FakeHantekScope(clock=ManualClock())

    with pytest.raises(InputError):
        _ = scope.expected_block_interval_s

    assert scope.set_sample_rate(DEVICE_RATE_CODE) is True

    assert scope.sample_rate_hz == DEVICE_RATE_HZ
    assert scope.expected_block_interval_s == BLOCK_SAMPLES_PER_CHANNEL / DEVICE_RATE_HZ


def test_rate_code_conflicting_with_the_configured_rate_is_an_input_error() -> None:
    scope = FakeHantekScope(clock=ManualClock(), sample_rate_hz=DEVICE_RATE_HZ)

    assert scope.set_sample_rate(DEVICE_RATE_CODE) is True
    with pytest.raises(InputError, match="sample_rate_hz"):
        scope.set_sample_rate(4)
    with pytest.raises(InputError):
        scope.set_sample_rate(0)
    with pytest.raises(InputError):
        scope.set_sample_rate(48)


def test_start_capture_needs_rate_handle_and_callback() -> None:
    recorder = _Recorder()
    without_rate = FakeHantekScope(clock=ManualClock())
    assert without_rate.open_handle() is True
    without_rate.read_async(recorder.on_block, BLOCK_SAMPLES, 10, raw=True)
    with pytest.raises(InputError, match="частот"):
        without_rate.start_capture()

    without_handle = FakeHantekScope(clock=ManualClock(), sample_rate_hz=RATE_HZ)
    with pytest.raises(InputError, match="open_handle"):
        without_handle.start_capture()

    without_callback = FakeHantekScope(clock=ManualClock(), sample_rate_hz=RATE_HZ)
    assert without_callback.open_handle() is True
    with pytest.raises(InputError, match="read_async"):
        without_callback.start_capture()


def test_read_async_rejects_volts_mode_and_degenerate_sizes() -> None:
    scope = FakeHantekScope(clock=ManualClock(), sample_rate_hz=RATE_HZ)
    recorder = _Recorder()

    with pytest.raises(InputError, match="raw"):
        scope.read_async(recorder.on_block, BLOCK_SAMPLES, 10, raw=False)
    with pytest.raises(InputError):
        scope.read_async(recorder.on_block, 1, 10, raw=True)
    with pytest.raises(InputError):
        scope.read_async(recorder.on_block, BLOCK_SAMPLES, 0, raw=True)


def test_constructor_rejects_degenerate_generator_settings() -> None:
    with pytest.raises(InputError):
        FakeHantekScope(clock=ManualClock(), seed=-1)
    with pytest.raises(InputError):
        FakeHantekScope(clock=ManualClock(), buffer_blocks=0)
    with pytest.raises(InputError):
        FakeHantekScope(clock=ManualClock(), sample_rate_hz=0.0)
    with pytest.raises(InputError):
        FakeHantekScope(clock=ManualClock(), profile="нет-такого-профиля")


def test_run_capture_streams_requested_samples_through_the_fake() -> None:
    requested = 2 * BLOCK_SAMPLES_PER_CHANNEL
    interval_s = BLOCK_SAMPLES_PER_CHANNEL / DEVICE_RATE_HZ
    scope = FakeHantekScope(
        profile="quiet",
        seed=SEED,
        sample_rate_hz=DEVICE_RATE_HZ,
        clock=ManualClock(stride_s=interval_s),
    )

    result = run_capture(
        scope,
        rate_code=DEVICE_RATE_CODE,
        ch1_range_code=RANGE_CODE_5V,
        sample_rate_hz=DEVICE_RATE_HZ,
        requested_samples=requested,
    )

    assert not isinstance(result, CancelledResult)
    ch1, ch2, telemetry = result
    assert ch1.size == ch2.size == requested
    assert telemetry.captured_samples >= requested
    assert telemetry.expected_block_interval_s == interval_s
    assert set(telemetry.block_lengths) == {BLOCK_SAMPLES_PER_CHANNEL}
    assert telemetry.short_block_count == 0
    assert scope.poll_timeouts == [MAX_POLL_TIMEOUT_MS] * len(scope.poll_timeouts)
    assert scope.calls == [
        "setup",
        "open_handle",
        "read_async",
        "start_capture",
        "stop_capture",
        "close_handle",
    ]
    assert scope.is_open is False
    assert float(ch2.std()) > 20.0
