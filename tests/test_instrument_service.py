"""InstrumentService: владение прибором, софт edge-триггер, контракт stop.

Время инжектируется (``ManualClock`` из ``lnt.instrument.fake_scope``): ни один
тест не спит и не зависит от реальной длительности ``poll``. Прибор — только
фейк, реальный драйвер не импортируется. Эталонный поток вольт считается
НЕЗАВИСИМО от сервиса: тот же фейк пишется в рекордер, raw -> В через
``apply_adc_calibration``, фронты ищутся прямой формулой пересечения порога.

Контракт остановки (issue #26): ``stop -> финальный кадр -> close_handle``.
Предтриггера нет (железо его не даёт, issue #22): окно кадра начинается НА
фронте, отсчётов до него в кадре не бывает.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields
from typing import TYPE_CHECKING, override

import numpy as np
import pytest

from lnt.adc_calibration import VOLTS_SCALE, AdcCalibration, apply_adc_calibration
from lnt.errors import DeviceNotFoundError, InputError
from lnt.instrument import (
    UNSTABLE_LEAD_SAMPLES,
    FakeHantekScope,
    FrameAssembler,
    InstrumentService,
    InstrumentState,
    LiveFrame,
    ManualClock,
    TriggerConfig,
    TriggerMode,
    TriggerSlope,
    TriggerSource,
    find_edge,
)
from lnt.scope_io import (
    BLOCK_SAMPLES,
    BLOCK_SAMPLES_PER_CHANNEL,
    MAX_POLL_TIMEOUT_MS,
    NEVER_CANCELLED,
    RANGE_CODE_5V,
    CancellationToken,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.scope_io import ScopeProtocol

# 1 МГц (код 1): блок 32768 отсчётов = 32.768 мс = 1.64 периода сети, поэтому
# фронт 50 Гц попадает почти в каждый блок — триггерные тесты не ждут десятков
# кадров. Часы СТАВЯТСЯ одним умножением (``blocks * interval``), как считает
# срок кадра фейк: накопления ulp нет и границы «ровно в срок» точны.
RATE_HZ = 1_000_000.0
RATE_CODE = 1
CADENCE_S = BLOCK_SAMPLES_PER_CHANNEL / RATE_HZ
FRAME_SAMPLES = 4096
FRAMES_PER_BLOCK = BLOCK_SAMPLES_PER_CHANNEL // FRAME_SAMPLES
SEED = 2026
PROFILE = "bad"
# Порог выше амплитуды сети (±3 В), но в окне триггера (±5 В): пересечение
# недостижимо ни на одном отсчёте, а конфиг остаётся валидным.
NEVER_CROSS_V = 4.9
LF_PEAK_V = 3.0
RANGE_V = 5.0
TRIGGER_LEVEL_V = 0.0


@dataclass(slots=True)
class _Sink:
    """Подписчик кадров: фиксирует кадр и состояние ручки в момент выдачи."""

    scope: FakeHantekScope
    frames: list[LiveFrame] = field(default_factory=list)
    handle_open: list[bool] = field(default_factory=list)

    def on_frame(self, frame: LiveFrame) -> None:
        self.frames.append(frame)
        self.handle_open.append(self.scope.is_open)

    @property
    def stream_ch1(self) -> NDArray[np.float32]:
        return _concat([frame.ch1 for frame in self.frames])

    @property
    def stream_ch2(self) -> NDArray[np.float32]:
        return _concat([frame.ch2 for frame in self.frames])


@dataclass(slots=True)
class _Factory:
    """Инжектируемая фабрика прибора: отдаёт один фейк и считает вызовы."""

    scope: FakeHantekScope
    calls: int = 0

    def __call__(self) -> ScopeProtocol:
        self.calls += 1
        return self.scope


@dataclass(slots=True)
class _Rig:
    service: InstrumentService
    scope: FakeHantekScope
    clock: ManualClock
    sink: _Sink
    factory: _Factory
    pumped_blocks: int = 0

    def pump(self, blocks: int) -> int:
        """Ставит часы на ``blocks`` кадров прибора и делает один ``poll`` сервиса."""
        self.pumped_blocks += blocks
        self.clock.now_s = self.pumped_blocks * self.scope.expected_block_interval_s
        return self.service.poll()


def _concat(frames: list[NDArray[np.float32]]) -> NDArray[np.float32]:
    if not frames:
        return np.empty(0, dtype=np.float32)
    return np.concatenate(frames)


def _sweep_trigger(
    mode: TriggerMode = TriggerMode.AUTO,
    timeout_s: float = CADENCE_S,
) -> TriggerConfig:
    """Недостижимый порог: кадры даёт только развёртка AUTO (в NORMAL — ничего)."""
    return TriggerConfig(
        level_v=NEVER_CROSS_V,
        slope=TriggerSlope.RISING,
        source=TriggerSource.CH2,
        mode=mode,
        auto_timeout_s=timeout_s,
    )


def _edge_trigger(
    slope: TriggerSlope = TriggerSlope.RISING,
    source: TriggerSource = TriggerSource.CH2,
    mode: TriggerMode = TriggerMode.NORMAL,
    level_v: float = TRIGGER_LEVEL_V,
    auto_timeout_s: float = CADENCE_S,
) -> TriggerConfig:
    """Достижимый порог: кадры даёт фронт, а AUTO-развёртка — раз в ``auto_timeout_s``."""
    return TriggerConfig(
        level_v=level_v,
        slope=slope,
        source=source,
        mode=mode,
        auto_timeout_s=auto_timeout_s,
    )


def _rig(
    *,
    trigger: TriggerConfig | None = None,
    frame_samples: int = FRAME_SAMPLES,
    max_buffered_blocks: int = 4,
    discard_lead_samples: int = 0,
    profile: str = PROFILE,
    seed: int = SEED,
    sample_rate_hz: float = RATE_HZ,
    ch1_range_v: float = RANGE_V,
    clock: ManualClock | None = None,
    cancellation_token: CancellationToken = NEVER_CANCELLED,
    adc_calibration: AdcCalibration | None = None,
) -> _Rig:
    """Собирает сервис на фейке с инжектируемыми часами (без ``start``).

    Прогрев по умолчанию выключен (``discard_lead_samples=0``), чтобы индексы
    эталонного потока совпадали с индексами буфера; тесты прогрева передают
    ``UNSTABLE_LEAD_SAMPLES`` явно.
    """
    used_clock = clock if clock is not None else ManualClock()
    scope = FakeHantekScope(
        profile=profile,
        seed=seed,
        sample_rate_hz=sample_rate_hz,
        clock=used_clock,
        buffer_blocks=8,
    )
    sink = _Sink(scope=scope)
    factory = _Factory(scope=scope)
    service = InstrumentService(
        scope_factory=factory,
        sample_rate_hz=sample_rate_hz,
        ch1_range_v=ch1_range_v,
        trigger=trigger if trigger is not None else _sweep_trigger(),
        frame_samples=frame_samples,
        max_buffered_blocks=max_buffered_blocks,
        discard_lead_samples=discard_lead_samples,
        clock=used_clock,
        cancellation_token=cancellation_token,
        adc_calibration=adc_calibration,
    )
    service.subscribe(sink.on_frame)
    return _Rig(service=service, scope=scope, clock=used_clock, sink=sink, factory=factory)


def _reference_volts(
    *,
    blocks: int,
    profile: str = PROFILE,
    seed: int = SEED,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Эталон: тот же фейк в рекордер, raw -> В документированным масштабом."""
    clock = ManualClock()
    scope = FakeHantekScope(
        profile=profile,
        seed=seed,
        sample_rate_hz=RATE_HZ,
        clock=clock,
        buffer_blocks=8,
    )
    raw: list[tuple[bytearray, bytearray]] = []

    def on_block(ch1: object, ch2: object) -> None:
        assert isinstance(ch1, bytearray)
        assert isinstance(ch2, bytearray)
        raw.append((ch1, ch2))

    assert scope.setup() is True
    assert scope.open_handle() is True
    scope.set_sample_rate(RATE_CODE)
    scope.set_ch1_voltage_range(RANGE_CODE_5V)
    scope.set_ch2_voltage_range(RANGE_CODE_5V)
    scope.read_async(on_block, BLOCK_SAMPLES, 10, raw=True)
    assert scope.start_capture() is True
    clock.advance(blocks * scope.expected_block_interval_s)
    assert scope.poll(MAX_POLL_TIMEOUT_MS) == blocks
    ch1 = np.concatenate([np.frombuffer(bytes(pair[0]), dtype=np.uint8) for pair in raw])
    ch2 = np.concatenate([np.frombuffer(bytes(pair[1]), dtype=np.uint8) for pair in raw])
    return (
        apply_adc_calibration(ch1, range_code=RANGE_CODE_5V),
        apply_adc_calibration(ch2, range_code=RANGE_CODE_5V),
    )


def _crossings(samples: NDArray[np.float32], level_v: float, slope: TriggerSlope) -> list[int]:
    """Прямая формула фронта: индексы отсчётов, НА которых пересечён порог."""
    if slope is TriggerSlope.RISING:
        hits = (samples[:-1] < level_v) & (samples[1:] >= level_v)
    else:
        hits = (samples[:-1] > level_v) & (samples[1:] <= level_v)
    return [int(index) + 1 for index in np.flatnonzero(hits)]


def _layout(
    crossings: list[int],
    total: int,
    frame_samples: int,
    *,
    sweep: bool = False,
) -> list[tuple[int, bool]]:
    """Независимое зеркало разбора буфера: фронт приоритетен, AUTO доедает остаток.

    Возвращает пары (начало окна, triggered). Окно начинается НА фронте, поэтому
    отсчёты между курсором и фронтом в кадры не попадают — как на DSO.
    """
    picked: list[tuple[int, bool]] = []
    cursor = 1
    while True:
        edge = next((index for index in crossings if index >= cursor), None)
        if edge is not None:
            if total - edge < frame_samples:
                break
            picked.append((edge, True))
            cursor = edge + frame_samples
            continue
        if not sweep or total - cursor < frame_samples:
            break
        picked.append((cursor, False))
        cursor += frame_samples
    return picked


# ---------------------------------------------------------------------------
# владение прибором и жизненный цикл
# ---------------------------------------------------------------------------


def test_start_takes_ownership_and_configures_the_device_once() -> None:
    rig = _rig()

    assert rig.service.state is InstrumentState.IDLE
    assert rig.service.is_running is False
    assert rig.factory.calls == 0

    rig.service.start()

    assert rig.factory.calls == 1
    assert rig.scope.calls == ["setup", "open_handle", "read_async", "start_capture"]
    assert rig.scope.is_open is True
    assert rig.scope.is_capturing is True
    assert (rig.scope.interface, rig.scope.channel_count) == (0, 2)
    assert rig.scope.rate_code == RATE_CODE
    assert (rig.scope.ch1_range_code, rig.scope.ch2_range_code) == (RANGE_CODE_5V, RANGE_CODE_5V)
    assert rig.service.state is InstrumentState.RUNNING
    assert rig.service.is_running is True
    assert rig.service.frame_samples == FRAME_SAMPLES
    assert rig.service.sample_rate_hz == RATE_HZ


def test_poll_before_start_is_an_input_error() -> None:
    rig = _rig()

    with pytest.raises(InputError):
        rig.service.poll()
    with pytest.raises(InputError):
        rig.service.update_trigger(_sweep_trigger())

    assert rig.scope.calls == []


def test_double_start_does_not_take_a_second_handle() -> None:
    rig = _rig()
    rig.service.start()

    with pytest.raises(InputError):
        rig.service.start()

    assert rig.factory.calls == 1
    assert rig.scope.calls.count("open_handle") == 1
    assert rig.service.is_running is True


class _FailingStart(FakeHantekScope):
    """Фейк с отказом ``start_capture``: проверка, что ручка не утекает."""

    @override
    def start_capture(self) -> bool:
        self.calls.append("start_capture")
        raise DeviceNotFoundError("имитация отказа старта захвата")


def test_start_failure_releases_the_handle_and_leaves_the_service_idle() -> None:
    scope = _FailingStart(clock=ManualClock(), sample_rate_hz=RATE_HZ)
    service = InstrumentService(
        scope_factory=lambda: scope,
        trigger=_sweep_trigger(),
        sample_rate_hz=RATE_HZ,
        clock=ManualClock(),
    )

    with pytest.raises(DeviceNotFoundError):
        service.start()

    assert scope.is_open is False
    assert scope.calls[-1] == "close_handle"
    assert service.state is InstrumentState.IDLE
    assert service.is_running is False
    with pytest.raises(InputError):
        service.poll()


def test_stop_without_start_is_a_noop() -> None:
    rig = _rig()

    rig.service.stop()

    assert rig.service.state is InstrumentState.IDLE
    assert rig.scope.calls == []
    assert rig.sink.frames == []


def test_poll_uses_the_driver_poll_window() -> None:
    rig = _rig(discard_lead_samples=0)
    rig.service.start()

    assert rig.pump(1) == FRAMES_PER_BLOCK - 1

    assert rig.scope.poll_timeouts == [MAX_POLL_TIMEOUT_MS]


# ---------------------------------------------------------------------------
# кадры: сборка из блоков прибора, вольты, непрерывность
# ---------------------------------------------------------------------------


def test_auto_sweep_frames_tile_the_stream_without_gaps() -> None:
    rig = _rig(discard_lead_samples=0)
    rig.service.start()
    reference_ch1, reference_ch2 = _reference_volts(blocks=2)

    # Первый блок даёт 7 полных кадров (один отсчёт остаётся швом для поиска
    # фронта), второй — остальные 8: поток разрезан на окна без пропусков.
    assert rig.pump(1) == FRAMES_PER_BLOCK - 1
    assert rig.pump(1) == FRAMES_PER_BLOCK

    frames = rig.sink.frames
    assert [frame.frame_index for frame in frames] == list(range(2 * FRAMES_PER_BLOCK - 1))
    assert all(frame.triggered is False for frame in frames)
    assert all(frame.ch1.shape == (FRAME_SAMPLES,) for frame in frames)
    assert all(frame.ch2.shape == (FRAME_SAMPLES,) for frame in frames)
    assert all(frame.ch1.dtype == np.float32 for frame in frames)
    assert all(frame.dropped_samples == 0 for frame in frames)
    assert all(frame.emitted_at_s == CADENCE_S for frame in frames[: FRAMES_PER_BLOCK - 1])
    size = rig.sink.stream_ch2.size
    assert np.array_equal(rig.sink.stream_ch2, reference_ch2[1 : 1 + size])
    assert np.array_equal(rig.sink.stream_ch1, reference_ch1[1 : 1 + size])


def test_frames_carry_volts_not_raw_counts() -> None:
    rig = _rig(discard_lead_samples=0)
    rig.service.start()

    assert rig.pump(2) == 2 * FRAMES_PER_BLOCK - 1
    ch1 = rig.sink.stream_ch1
    ch2 = rig.sink.stream_ch2

    # CH2 — 50 Гц +-3 В: в raw это 128 +-75 LSB, в вольтах — около +-3.
    assert LF_PEAK_V * 0.6 < float(ch2.max()) < LF_PEAK_V * 1.4
    assert -LF_PEAK_V * 1.4 < float(ch2.min()) < -LF_PEAK_V * 0.6
    # CH1 — ВЧ-картина пробника: иголки на порядок меньше амплитуды сети.
    assert float(ch1.max()) < LF_PEAK_V
    assert rig.service.calibration_used is False


def test_adc_calibration_table_reaches_the_frame_volts() -> None:
    plain = _rig(discard_lead_samples=0)
    corrected = _rig(
        discard_lead_samples=0,
        adc_calibration=AdcCalibration(offset_lsb=1.0, device_serial="test"),
    )
    plain.service.start()
    corrected.service.start()

    assert plain.pump(1) == FRAMES_PER_BLOCK - 1
    assert corrected.pump(1) == FRAMES_PER_BLOCK - 1
    assert corrected.service.calibration_used is True

    step_v = VOLTS_SCALE / float(RANGE_CODE_5V << 7)
    delta = corrected.sink.frames[0].ch2 - plain.sink.frames[0].ch2
    assert np.allclose(delta, -step_v, atol=1e-6)


def test_overflow_is_bounded_and_reported_on_the_next_frame() -> None:
    rig = _rig(
        trigger=_sweep_trigger(TriggerMode.NORMAL),
        max_buffered_blocks=2,
        discard_lead_samples=0,
    )
    rig.service.start()

    assert rig.pump(4) == 0
    rig.service.stop()

    final = rig.sink.frames[-1]
    assert final.dropped_samples == 2 * BLOCK_SAMPLES_PER_CHANNEL
    reference_ch1, reference_ch2 = _reference_volts(blocks=4)
    tail = 2 * BLOCK_SAMPLES_PER_CHANNEL
    assert np.array_equal(final.ch2, reference_ch2[tail + 1 : tail + 1 + FRAME_SAMPLES])
    assert np.array_equal(final.ch1, reference_ch1[tail + 1 : tail + 1 + FRAME_SAMPLES])


# ---------------------------------------------------------------------------
# софтверный edge-триггер
# ---------------------------------------------------------------------------


def test_find_edge_returns_the_crossing_sample_itself() -> None:
    samples = np.array([-1.0, -0.5, 0.5, 1.0, 0.4, -0.2], dtype=np.float32)
    empty = np.empty(0, dtype=np.float32)

    assert find_edge(samples, level_v=0.0, slope=TriggerSlope.RISING) == 2
    assert find_edge(samples, level_v=0.0, slope=TriggerSlope.FALLING) == 5
    assert find_edge(samples, level_v=0.0, slope=TriggerSlope.RISING, start=3) is None
    assert find_edge(samples, level_v=5.0, slope=TriggerSlope.RISING) is None
    assert find_edge(empty, level_v=0.0, slope=TriggerSlope.RISING) is None


def test_normal_mode_stays_silent_without_an_edge() -> None:
    rig = _rig(trigger=_sweep_trigger(TriggerMode.NORMAL), discard_lead_samples=0)
    rig.service.start()

    assert rig.pump(4) == 0

    assert rig.sink.frames == []
    assert rig.scope.blocks_emitted == 4
    assert rig.service.state is InstrumentState.RUNNING
    assert rig.service.is_running is True


def test_normal_mode_emits_every_edge_window_and_nothing_else() -> None:
    rig = _rig(trigger=_edge_trigger(), discard_lead_samples=0)
    rig.service.start()
    _, reference = _reference_volts(blocks=4)
    crossings = _crossings(reference, TRIGGER_LEVEL_V, TriggerSlope.RISING)
    expected = _layout(crossings, reference.size, FRAME_SAMPLES)

    assert rig.pump(4) == len(expected)
    assert len(expected) >= 4
    assert all(triggered for _, triggered in expected)

    frames = rig.sink.frames
    assert all(frame.triggered is True for frame in frames)
    for frame, (start, _) in zip(frames, expected, strict=True):
        assert np.array_equal(frame.ch2, reference[start : start + FRAME_SAMPLES])


def test_the_window_starts_at_the_edge_because_there_is_no_pretrigger() -> None:
    rig = _rig(trigger=_edge_trigger(), discard_lead_samples=0)
    rig.service.start()
    _, reference = _reference_volts(blocks=4)
    crossings = _crossings(reference, TRIGGER_LEVEL_V, TriggerSlope.RISING)

    assert rig.pump(4) >= 1
    first = rig.sink.frames[0]
    edge = crossings[0]

    assert first.ch2[0] >= TRIGGER_LEVEL_V
    assert reference[edge - 1] < TRIGGER_LEVEL_V
    assert np.array_equal(first.ch2, reference[edge : edge + FRAME_SAMPLES])


def test_falling_slope_triggers_the_opposite_crossing() -> None:
    rig = _rig(trigger=_edge_trigger(slope=TriggerSlope.FALLING), discard_lead_samples=0)
    rig.service.start()
    _, reference = _reference_volts(blocks=4)
    crossings = _crossings(reference, TRIGGER_LEVEL_V, TriggerSlope.FALLING)
    expected = _layout(crossings, reference.size, FRAME_SAMPLES)

    assert rig.pump(4) == len(expected)

    for frame, (start, _) in zip(rig.sink.frames, expected, strict=True):
        assert frame.ch2[0] <= TRIGGER_LEVEL_V
        assert reference[start - 1] > TRIGGER_LEVEL_V


def test_trigger_source_selects_the_channel_being_searched() -> None:
    rig = _rig(
        trigger=_edge_trigger(source=TriggerSource.CH1, level_v=0.1),
        discard_lead_samples=0,
    )
    rig.service.start()
    reference_ch1, reference_ch2 = _reference_volts(blocks=2)
    crossings = _crossings(reference_ch1, 0.1, TriggerSlope.RISING)
    expected = _layout(crossings, reference_ch1.size, FRAME_SAMPLES)

    assert rig.pump(2) == len(expected)
    assert len(expected) >= 2

    for frame, (start, _) in zip(rig.sink.frames, expected, strict=True):
        assert np.array_equal(frame.ch1, reference_ch1[start : start + FRAME_SAMPLES])
        assert frame.ch2[0] == pytest.approx(float(reference_ch2[start]))


def test_auto_mode_mixes_triggered_frames_with_sweeps() -> None:
    rig = _rig(trigger=_edge_trigger(mode=TriggerMode.AUTO), discard_lead_samples=0)
    rig.service.start()
    _, reference = _reference_volts(blocks=2)
    crossings = _crossings(reference, TRIGGER_LEVEL_V, TriggerSlope.RISING)
    expected = _layout(crossings, reference.size, FRAME_SAMPLES, sweep=True)

    assert rig.pump(2) == len(expected)

    flags = [frame.triggered for frame in rig.sink.frames]
    assert flags == [triggered for _, triggered in expected]
    assert any(flags)
    assert not all(flags)
    for frame, (start, _) in zip(rig.sink.frames, expected, strict=True):
        assert np.array_equal(frame.ch2, reference[start : start + FRAME_SAMPLES])


def test_single_mode_emits_one_triggered_frame_then_releases_the_device() -> None:
    rig = _rig(trigger=_edge_trigger(mode=TriggerMode.SINGLE), discard_lead_samples=0)
    rig.service.start()

    assert rig.pump(4) == 1

    assert len(rig.sink.frames) == 1
    assert rig.sink.frames[0].triggered is True
    assert rig.sink.handle_open == [True]
    assert rig.service.state is InstrumentState.STOPPED
    assert rig.service.is_running is False
    assert rig.scope.calls[-2:] == ["stop_capture", "close_handle"]
    assert rig.scope.is_open is False
    assert rig.scope.is_capturing is False

    with pytest.raises(InputError):
        rig.service.poll()


def test_update_trigger_applies_without_restarting_the_capture() -> None:
    rig = _rig(trigger=_sweep_trigger(TriggerMode.NORMAL), discard_lead_samples=0)
    rig.service.start()

    assert rig.pump(2) == 0

    rig.service.update_trigger(_edge_trigger())

    assert rig.service.trigger.level_v == TRIGGER_LEVEL_V
    assert rig.pump(2) >= 1
    assert all(frame.triggered for frame in rig.sink.frames)
    assert rig.scope.calls.count("start_capture") == 1
    assert rig.scope.calls.count("open_handle") == 1
    assert rig.service.is_running is True


# ---------------------------------------------------------------------------
# контракт остановки: финальный кадр, затем close_handle
# ---------------------------------------------------------------------------


def test_stop_emits_the_final_frame_before_closing_the_handle() -> None:
    rig = _rig(
        trigger=_sweep_trigger(TriggerMode.AUTO, timeout_s=100.0),
        frame_samples=5000,
        discard_lead_samples=0,
    )
    rig.service.start()

    assert rig.pump(1) == 0
    assert rig.sink.frames == []

    rig.service.stop()

    assert len(rig.sink.frames) == 1
    final = rig.sink.frames[0]
    assert final.triggered is False
    assert final.ch1.size == final.ch2.size == 5000
    # Финальный кадр ушёл подписчику, когда ручка была ещё открыта.
    assert rig.sink.handle_open == [True]
    assert rig.scope.is_open is False
    assert rig.scope.calls == [
        "setup",
        "open_handle",
        "read_async",
        "start_capture",
        "stop_capture",
        "close_handle",
    ]
    assert rig.service.state is InstrumentState.STOPPED
    reference_ch1, reference_ch2 = _reference_volts(blocks=1)
    assert np.array_equal(final.ch2, reference_ch2[1:5001])
    assert np.array_equal(final.ch1, reference_ch1[1:5001])


def test_stop_with_nothing_left_to_flush_does_not_fabricate_a_frame() -> None:
    # Кадр ровно на блок без одного отсчёта: после выдачи буфер пуст (остался
    # только шов) — финального кадра нет, но ручка закрыта.
    rig = _rig(frame_samples=BLOCK_SAMPLES_PER_CHANNEL - 1, discard_lead_samples=0)
    rig.service.start()

    assert rig.pump(1) == 1
    assert rig.sink.frames[0].ch2.size == BLOCK_SAMPLES_PER_CHANNEL - 1

    rig.service.stop()

    assert len(rig.sink.frames) == 1
    assert rig.scope.calls[-1] == "close_handle"
    assert rig.scope.is_open is False
    assert rig.service.state is InstrumentState.STOPPED


def test_stop_is_idempotent_and_does_not_touch_the_handle_twice() -> None:
    rig = _rig(discard_lead_samples=0)
    rig.service.start()
    rig.service.stop()

    rig.service.stop()

    assert rig.scope.calls.count("close_handle") == 1
    assert rig.service.state is InstrumentState.STOPPED


def test_restart_after_stop_takes_a_fresh_handle_and_discards_the_lead_again() -> None:
    rig = _rig(discard_lead_samples=UNSTABLE_LEAD_SAMPLES)
    rig.service.start()
    assert rig.pump(2) == FRAMES_PER_BLOCK - 1
    rig.service.stop()
    first_run = len(rig.sink.frames)

    rig.service.start()

    assert rig.factory.calls == 2
    assert rig.scope.calls.count("open_handle") == 2
    assert rig.service.state is InstrumentState.RUNNING
    # Прогрев снова в силе: первый блок свежего старта в кадры не попадает.
    assert rig.pump(1) == 0
    assert rig.pump(1) == FRAMES_PER_BLOCK - 1
    assert len(rig.sink.frames) == first_run + FRAMES_PER_BLOCK - 1
    assert rig.sink.frames[-1].frame_index == FRAMES_PER_BLOCK - 2


def test_cancellation_releases_the_handle_without_a_final_frame() -> None:
    state = {"cancelled": False}
    rig = _rig(
        trigger=_sweep_trigger(TriggerMode.AUTO, timeout_s=100.0),
        cancellation_token=CancellationToken(lambda: state["cancelled"]),
        discard_lead_samples=0,
    )
    rig.service.start()
    assert rig.pump(1) == 0

    state["cancelled"] = True

    assert rig.service.poll() == 0
    assert rig.sink.frames == []
    assert rig.service.state is InstrumentState.STOPPED
    assert rig.service.is_running is False
    assert rig.scope.calls[-2:] == ["stop_capture", "close_handle"]
    assert rig.scope.is_open is False

    with pytest.raises(InputError):
        rig.service.poll()


# ---------------------------------------------------------------------------
# отбрасывание нестабильных отсчётов свежего старта
# ---------------------------------------------------------------------------


def test_the_unstable_lead_of_a_fresh_start_never_reaches_a_frame() -> None:
    rig = _rig(discard_lead_samples=UNSTABLE_LEAD_SAMPLES)
    rig.service.start()
    reference_ch1, reference_ch2 = _reference_volts(blocks=3)
    lead = UNSTABLE_LEAD_SAMPLES

    assert lead > 0
    assert rig.pump(1) == 0
    assert rig.pump(2) == 2 * FRAMES_PER_BLOCK - 1

    stream = rig.sink.stream_ch2
    assert stream.size == (2 * FRAMES_PER_BLOCK - 1) * FRAME_SAMPLES
    assert np.array_equal(stream, reference_ch2[lead + 1 : lead + 1 + stream.size])
    assert np.array_equal(
        rig.sink.stream_ch1,
        reference_ch1[lead + 1 : lead + 1 + stream.size],
    )


def test_lead_discard_knob_shifts_the_stream_by_exactly_that_many_samples() -> None:
    lead = 1024
    rig = _rig(discard_lead_samples=lead)
    rig.service.start()
    _, reference = _reference_volts(blocks=2)

    assert rig.pump(2) == 2 * FRAMES_PER_BLOCK - 1

    stream = rig.sink.stream_ch2
    assert stream.size > 0
    assert np.array_equal(stream, reference[lead + 1 : lead + 1 + stream.size])


# ---------------------------------------------------------------------------
# подписка и границы входа
# ---------------------------------------------------------------------------


def test_frames_reach_every_subscriber_and_unsubscribe_detaches() -> None:
    rig = _rig(discard_lead_samples=0)
    second: list[LiveFrame] = []
    detach = rig.service.subscribe(second.append)
    rig.service.start()

    assert rig.pump(1) == FRAMES_PER_BLOCK - 1
    detach()
    assert rig.pump(1) == FRAMES_PER_BLOCK

    assert len(second) == FRAMES_PER_BLOCK - 1
    assert len(rig.sink.frames) == 2 * FRAMES_PER_BLOCK - 1


def test_constructor_rejects_degenerate_settings() -> None:
    with pytest.raises(InputError, match="frame_samples"):
        _rig(frame_samples=1)
    with pytest.raises(InputError, match="frame_samples"):
        _rig(frame_samples=BLOCK_SAMPLES_PER_CHANNEL + 1)
    with pytest.raises(InputError, match="max_buffered_blocks"):
        _rig(max_buffered_blocks=0)
    with pytest.raises(InputError, match="discard_lead_samples"):
        _rig(discard_lead_samples=-1)
    with pytest.raises(InputError, match="частота"):
        _rig(sample_rate_hz=1_500_000.0)
    with pytest.raises(InputError, match="диапазон"):
        _rig(ch1_range_v=2.5)


@pytest.mark.parametrize("timeout_ms", [0, -1, MAX_POLL_TIMEOUT_MS + 1])
def test_constructor_rejects_a_poll_window_outside_the_driver_bounds(timeout_ms: int) -> None:
    scope = FakeHantekScope(clock=ManualClock(), sample_rate_hz=RATE_HZ)

    with pytest.raises(InputError, match="poll_timeout_ms"):
        InstrumentService(
            scope_factory=lambda: scope,
            trigger=_sweep_trigger(),
            poll_timeout_ms=timeout_ms,
        )


def test_constructor_rejects_a_non_physical_probe_multiplier() -> None:
    scope = FakeHantekScope(clock=ManualClock(), sample_rate_hz=RATE_HZ)

    with pytest.raises(InputError, match="ch1_probe_multiplier"):
        InstrumentService(
            scope_factory=lambda: scope,
            trigger=_sweep_trigger(),
            ch1_probe_multiplier=0.0,
        )


@pytest.mark.parametrize("level_v", [float("nan"), float("inf")])
def test_trigger_config_rejects_a_non_finite_level(level_v: float) -> None:
    with pytest.raises(InputError):
        TriggerConfig(level_v=level_v)


@pytest.mark.parametrize("timeout_s", [0.0, -1.0, float("nan")])
def test_trigger_config_rejects_a_non_positive_auto_timeout(timeout_s: float) -> None:
    with pytest.raises(InputError):
        TriggerConfig(level_v=TRIGGER_LEVEL_V, auto_timeout_s=timeout_s)


@pytest.mark.parametrize("level_v", [-5.0, -4.999, 0.0, 4.999, 5.0])
def test_trigger_config_accepts_levels_inside_the_input_window(level_v: float) -> None:
    config = TriggerConfig(level_v=level_v)

    assert config.level_v == level_v


@pytest.mark.parametrize("level_v", [5.001, -5.001])
def test_trigger_config_rejects_levels_outside_the_input_window(level_v: float) -> None:
    # Порог вне окна входа ±5 В: явная ошибка с пределами, а не молчаливый
    # NORMAL без кадров (граница ±5 В раньше жила только на клиенте).
    with pytest.raises(InputError, match="вне диапазона") as excinfo:
        TriggerConfig(level_v=level_v)

    assert "−5…+5 В" in str(excinfo.value)


def test_trigger_config_requires_a_level() -> None:
    # Отсутствующий уровень — не молчаливый ноль: поле обязательное
    # (без дефолта — вызов без него даёт TypeError).
    required = {
        f.name
        for f in fields(TriggerConfig)
        if f.default is MISSING and f.default_factory is MISSING
    }
    assert "level_v" in required


# ---------------------------------------------------------------------------
# сборщик кадров как отдельная единица
# ---------------------------------------------------------------------------


def test_assembler_discards_a_lead_longer_than_one_block() -> None:
    assembler = FrameAssembler(
        frame_samples=1024,
        max_buffered_blocks=4,
        discard_lead_samples=BLOCK_SAMPLES_PER_CHANNEL + 4096,
    )
    zeros = np.zeros(BLOCK_SAMPLES_PER_CHANNEL, dtype=np.float32)

    assert assembler.push(zeros, zeros) == 0
    assert assembler.available == 0
    assert assembler.push(zeros, zeros) == 0
    assert assembler.available == BLOCK_SAMPLES_PER_CHANNEL - 4096


def test_assembler_is_bounded_and_keeps_the_newest_samples() -> None:
    assembler = FrameAssembler(frame_samples=1024, max_buffered_blocks=1, discard_lead_samples=0)
    old = np.zeros(BLOCK_SAMPLES_PER_CHANNEL, dtype=np.float32)
    fresh = np.ones(BLOCK_SAMPLES_PER_CHANNEL, dtype=np.float32)

    assert assembler.push(old, old) == 0
    assert assembler.push(fresh, fresh) == BLOCK_SAMPLES_PER_CHANNEL
    assert assembler.available == BLOCK_SAMPLES_PER_CHANNEL

    ch1, ch2 = assembler.take(0, 4)
    assert np.array_equal(ch1, np.ones(4, dtype=np.float32))
    assert np.array_equal(ch2, np.ones(4, dtype=np.float32))


def test_assembler_take_clamps_to_the_available_tail() -> None:
    assembler = FrameAssembler(frame_samples=1024, max_buffered_blocks=1, discard_lead_samples=0)
    ramp = np.arange(BLOCK_SAMPLES_PER_CHANNEL, dtype=np.float32)

    assert assembler.push(ramp, ramp) == 0

    ch1, _ = assembler.take(10, 10**6)
    assert ch1.size == BLOCK_SAMPLES_PER_CHANNEL - 10
    assert float(ch1[0]) == 10.0


def test_assembler_reset_rearms_the_lead_discard() -> None:
    assembler = FrameAssembler(
        frame_samples=1024,
        max_buffered_blocks=2,
        discard_lead_samples=BLOCK_SAMPLES_PER_CHANNEL,
    )
    block = np.zeros(BLOCK_SAMPLES_PER_CHANNEL, dtype=np.float32)

    assert assembler.push(block, block) == 0
    assert assembler.available == 0

    assembler.reset()

    assert assembler.push(block, block) == 0
    assert assembler.available == 0
