"""Живые полные метрики риппла: кольцо, settle-гейт, непрерывность и SSE.

Стенд без железа и без ``sleep``: прибор — детерминированный фейк с непрерывным
синусом на CH1, время — ``ManualClock`` (блоки ставятся одним присваиванием),
SSE читается генератором маршрута. Метрики сверяются с независимым пересчётом
по ТОЧНОМУ ряду, который отдал фейк (float64), а не с выходами движка.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, cast, override

import numpy as np
import pytest
from pydantic import ValidationError

from lnt.adc_calibration import apply_adc_calibration
from lnt.capture_preflight import BaselineCompatibility, CaptureEnvironment
from lnt.device_diagnostics import DeviceState
from lnt.errors import InputError
from lnt.instrument import (
    FakeHantekScope,
    InstrumentService,
    LiveCaptureGate,
    LiveMode,
    LiveStartConfig,
    ManualClock,
    TriggerConfig,
    TriggerMode,
    TriggerSlope,
    TriggerSource,
)
from lnt.instrument.fake_scope import _quantize  # pyright: ignore[reportPrivateUsage]
from lnt.instrument.ripple import RippleEngine
from lnt.instrument.ripple_types import (
    MIN_METRIC_SAMPLES,
    RIPPLE_BUFFER_SAMPLES,
    SYNTHETIC_EXACT,
    UNCALIBRATED_VOLTS_LABEL_RU,
    RippleConfig,
    RippleStatus,
)
from lnt.ripple.adapter import AdapterSpec, TransferStatus
from lnt.scope_io import BLOCK_SAMPLES_PER_CHANNEL, RawCallback
from lnt.ui import routes_live
from lnt.ui.live_ripple_events import RippleEmitter
from lnt.ui.models_live import MAX_FRAME_POINTS
from lnt.ui.models_ripple_live import LiveRipplePayload, ripple_payload

if TYPE_CHECKING:
    import threading
    from collections.abc import AsyncIterator
    from pathlib import Path

    from fastapi.sse import ServerSentEvent
    from numpy.typing import NDArray

    from lnt.instrument.frames import LiveFrame
    from lnt.scope_io import ScopeProtocol

RATE_HZ: Final = 1_000_000.0
CADENCE_S: Final = BLOCK_SAMPLES_PER_CHANNEL / RATE_HZ
SETTLE_SAMPLES: Final = 1_000_000
BLOCKS_TO_SETTLE: Final = 32
PROFILE: Final = "bad"
SEED: Final = 2026
NEVER_CROSS_V: Final = 4.9
TONE_HZ: Final = 10_000.0
TONE_AMPLITUDE_V: Final = 0.5
TONE_DC_V: Final = 0.25
HUGE_FREE_BYTES: Final = 10**12
EVENT_LIMIT: Final = 500


def _sine_scope(
    clock: ManualClock,
    *,
    sample_rate_hz: float = RATE_HZ,
    buffer_blocks: int = 64,
    tone_hz: float = TONE_HZ,
    amplitude_v: float = TONE_AMPLITUDE_V,
    dc_v: float = TONE_DC_V,
) -> RippleSineScope:
    return RippleSineScope(
        clock=clock,
        sample_rate_hz=sample_rate_hz,
        buffer_blocks=buffer_blocks,
        tone_hz=tone_hz,
        amplitude_v=amplitude_v,
        dc_v=dc_v,
    )


class RippleSineScope(FakeHantekScope):
    """Фейк-прибор с непрерывным синусом на CH1 на всё кольцо захвата."""

    def __init__(
        self,
        *,
        clock: ManualClock,
        sample_rate_hz: float,
        buffer_blocks: int,
        tone_hz: float,
        amplitude_v: float,
        dc_v: float,
    ) -> None:
        super().__init__(
            profile=PROFILE,
            seed=SEED,
            sample_rate_hz=sample_rate_hz,
            clock=clock,
            buffer_blocks=buffer_blocks,
        )
        self._tone_hz: Final = tone_hz
        self._amplitude_v: Final = amplitude_v
        self._dc_v: Final = dc_v

    @override
    def start_capture(self) -> bool:
        """Собирает непрерывный синус вместо профиля сети; каденс тот же."""
        started = super().start_capture()
        rate_hz = self._require_rate_hz()
        count = int(self._ch1_ring.size)
        moments = np.arange(count, dtype=np.float64) / rate_hz
        tone = self._dc_v + self._amplitude_v * np.sin(2.0 * np.pi * self._tone_hz * moments)
        self._ch1_ring: NDArray[np.uint8] = _quantize(tone.astype(np.float32), self.ch1_range_code)
        self._ch2_ring: NDArray[np.uint8] = np.zeros(count, dtype=np.uint8)
        return started

    def ch1_ring_tail(self, count: int) -> NDArray[np.uint8]:
        """Точный ряд, который фейк отдаёт первыми блоками (для сверки)."""
        return self._ch1_ring[:count]


@dataclass(slots=True)
class _Factory:
    scope: FakeHantekScope
    calls: int = 0

    def __call__(self) -> ScopeProtocol:
        self.calls += 1
        return self.scope


@dataclass(slots=True)
class _Environment:
    calls: int = 0

    def probe(self) -> CaptureEnvironment:
        self.calls += 1
        return CaptureEnvironment(
            device_state=DeviceState.READY,
            free_bytes=HUGE_FREE_BYTES,
            root_writable=True,
            baseline_compatibility=BaselineCompatibility.NOT_REQUESTED,
        )


class _DripScope(FakeHantekScope):
    """Фейк, отдающий наружу колбэк ``read_async``: блоки сыплются без poll."""

    on_block: RawCallback | None = None

    @override
    def read_async(
        self,
        callback: RawCallback,
        data_size: int,
        outstanding_transfers: int,
        *,
        raw: bool,
    ) -> threading.Event:
        self.on_block = callback
        return super().read_async(callback, data_size, outstanding_transfers, raw=raw)


@dataclass(slots=True)
class ServiceRig:
    service: InstrumentService
    scope: RippleSineScope
    clock: ManualClock
    factory: _Factory
    frames: list[LiveFrame] = field(default_factory=list)
    target_blocks: int = 0

    def pump(self, blocks: int) -> None:
        """Отдаёт ровно ``blocks`` блоков по одному на poll — без sleep и бурста."""
        for _ in range(blocks):
            self.target_blocks += 1
            self.clock.now_s = self.target_blocks * self.scope.expected_block_interval_s
            before = self.scope.blocks_emitted
            self.service.poll()
            assert self.scope.blocks_emitted == before + 1, "блок прибора не пришёл до дедлайна"

    def reference_ch1(self, blocks: int) -> NDArray[np.float32]:
        raw = self.scope.ch1_ring_tail(blocks * BLOCK_SAMPLES_PER_CHANNEL)
        return apply_adc_calibration(
            raw,
            range_code=self.scope.ch1_range_code,
            probe_multiplier=1.0,
        )


def service_rig(
    *,
    sample_rate_hz: float = RATE_HZ,
    ch1_range_v: float = 5.0,
    ch1_probe_multiplier: float = 1.0,
    trigger: TriggerConfig | None = None,
    max_buffered_blocks: int = 4,
    discard_lead_samples: int = 0,
    continuity_basis: str = SYNTHETIC_EXACT,
    scope: RippleSineScope | None = None,
) -> ServiceRig:
    clock = ManualClock()
    used_scope = scope if scope is not None else _sine_scope(clock, sample_rate_hz=sample_rate_hz)
    factory = _Factory(scope=used_scope)
    service = InstrumentService(
        scope_factory=factory,
        trigger=trigger if trigger is not None else _normal_trigger(),
        sample_rate_hz=sample_rate_hz,
        ch1_range_v=ch1_range_v,
        ch1_probe_multiplier=ch1_probe_multiplier,
        max_buffered_blocks=max_buffered_blocks,
        discard_lead_samples=discard_lead_samples,
        clock=clock,
        continuity_basis=continuity_basis,
    )
    rig = ServiceRig(service=service, scope=used_scope, clock=clock, factory=factory)
    service.subscribe(rig.frames.append)
    return rig


def _normal_trigger() -> TriggerConfig:
    """Недостижимый порог на нулевом CH2: кадров нет, блоки идут."""
    return TriggerConfig(
        level_v=NEVER_CROSS_V,
        slope=TriggerSlope.RISING,
        source=TriggerSource.CH2,
        mode=TriggerMode.NORMAL,
        auto_timeout_s=CADENCE_S,
    )


def _edge_trigger() -> TriggerConfig:
    return TriggerConfig(
        level_v=0.0,
        slope=TriggerSlope.RISING,
        source=TriggerSource.CH2,
        mode=TriggerMode.AUTO,
        auto_timeout_s=CADENCE_S,
    )


@dataclass(slots=True)
class GateRig:
    gate: LiveCaptureGate
    scope: RippleSineScope
    clock: ManualClock

    def start(self, *, sample_rate_hz: float = RATE_HZ) -> None:
        self.gate.start(
            LiveStartConfig(
                trigger=_normal_trigger(),
                sample_rate_hz=sample_rate_hz,
                ch1_range_v=5.0,
                ch1_probe_multiplier=1.0,
            ),
        )

    def advance_blocks(self, blocks: int) -> None:
        self.clock.advance(blocks * self.scope.expected_block_interval_s)


def gate_rig(
    tmp_path: Path,
    *,
    mode: LiveMode = LiveMode.SIM,
) -> GateRig:
    clock = ManualClock()
    scope = _sine_scope(clock)
    factory = _Factory(scope=scope)
    gate = LiveCaptureGate(
        scope_factory=factory,
        environment_probe=_Environment().probe,
        session_root=tmp_path / "sessions",
        clock=clock,
        discard_lead_samples=0,
        max_buffered_blocks=5,
        mode=mode,
    )
    return GateRig(gate=gate, scope=scope, clock=clock)


def live_stream(gate: LiveCaptureGate) -> AsyncIterator[ServerSentEvent]:
    return routes_live.live_frames(
        gate=gate,
        max_points=MAX_FRAME_POINTS,
        min_interval_s=0.0,
    )


def _ripples(events: list[ServerSentEvent]) -> list[LiveRipplePayload]:
    return [
        event.data
        for event in events
        if event.event == "ripple" and isinstance(event.data, LiveRipplePayload)
    ]


# ---------------------------------------------------------------------------
# движок: settle-гейт, пустое/короткое кольцо, рельсы
# ---------------------------------------------------------------------------


_TINY_ADAPTER: Final = AdapterSpec(cap_nf=0.001)


def _tiny_config(
    *,
    sample_rate_hz: float = 1_000.0,
    ch1_range_v: float = 5.0,
    probe_multiplier: float = 1.0,
    calibration_used: bool = False,
    continuity_basis: str = SYNTHETIC_EXACT,
    adapter: AdapterSpec | None = _TINY_ADAPTER,
    startup_discard_samples: int = 0,
) -> RippleConfig:
    return RippleConfig(
        adapter=adapter,
        probe_multiplier=probe_multiplier,
        sample_rate_hz=sample_rate_hz,
        ch1_range_v=ch1_range_v,
        calibration_used=calibration_used,
        continuity_basis=continuity_basis,
        startup_discard_samples=startup_discard_samples,
    )


def _feed(engine: RippleEngine, values: list[float], raw: list[int], sequence: int) -> None:
    start = sequence * len(values)
    engine.absorb_block(
        np.asarray(values, dtype=np.float32),
        raw=bytes(raw),
        sequence=sequence,
        sample_start=start,
    )


def test_empty_ring_is_never_fabricated() -> None:
    engine = RippleEngine(config=_tiny_config())

    snapshot = engine.snapshot()

    assert snapshot.status is RippleStatus.SETTLING
    assert snapshot.samples_received == 0
    assert snapshot.span_sample_count == 0
    assert snapshot.settling_basis == "capture_start_assuming_preconnected"
    assert snapshot.settling_remaining_samples == 1
    assert snapshot.excluded_prefix_samples == 1
    assert snapshot.clip_count_scope == "current_span"
    assert (snapshot.mean_v, snapshot.rms_ac_v, snapshot.vpp_v) == (None, None, None)


def test_short_record_has_no_metric_values() -> None:
    engine = RippleEngine(config=_tiny_config())
    engine.restart()
    _feed(engine, [0.1], [128], sequence=0)

    snapshot = engine.snapshot()

    assert snapshot.status is RippleStatus.UNAVAILABLE
    assert "insufficient_samples" in snapshot.reason_codes
    assert snapshot.samples_received == 1
    assert snapshot.settling_remaining_samples == 0
    assert snapshot.excluded_prefix_samples == 1
    assert (snapshot.mean_v, snapshot.rms_ac_v, snapshot.vpp_v) == (None, None, None)


def test_pre_settle_samples_are_settling_without_metrics() -> None:
    engine = RippleEngine(
        config=_tiny_config(adapter=AdapterSpec(cap_nf=1_000.0)),
    )
    engine.restart()
    _feed(engine, [0.1] * 100, [128] * 100, sequence=0)

    snapshot = engine.snapshot()

    assert snapshot.status is RippleStatus.SETTLING
    assert snapshot.settled is False
    assert snapshot.settle_samples == 10_000
    assert snapshot.settling_remaining_samples == 9_900
    assert snapshot.excluded_prefix_samples == 10_000
    assert snapshot.span_start_sample is None
    assert snapshot.span_sample_count == 0
    assert (snapshot.mean_v, snapshot.rms_ac_v, snapshot.vpp_v) == (None, None, None)


def test_startup_discard_is_the_later_excluded_boundary() -> None:
    engine = RippleEngine(
        config=_tiny_config(startup_discard_samples=4),
        capacity_samples=64,
    )
    engine.restart()
    _feed(engine, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], [128] * 6, sequence=0)

    snapshot = engine.snapshot()

    assert snapshot.status is RippleStatus.READY
    assert snapshot.startup_discard_samples == 4
    assert snapshot.excluded_prefix_samples == 4
    assert snapshot.settling_remaining_samples == 0
    assert snapshot.span_start_sample == 4
    assert snapshot.span_sample_count == 2
    assert snapshot.mean_v == pytest.approx(0.55, abs=1e-6)
    assert snapshot.rms_ac_v == pytest.approx(0.05, abs=1e-6)
    assert snapshot.vpp_v == pytest.approx(0.1, abs=1e-6)


def test_startup_discard_gates_settled_even_when_rc_window_is_shorter() -> None:
    engine = RippleEngine(
        config=_tiny_config(startup_discard_samples=4),
        capacity_samples=64,
    )
    engine.restart()
    _feed(engine, [0.1, 0.2], [128, 129], sequence=0)

    snapshot = engine.snapshot()

    assert snapshot.settle_samples == 1
    assert snapshot.settled is False
    assert snapshot.status is RippleStatus.SETTLING
    assert snapshot.settling_remaining_samples == 2


def test_settling_gate_excludes_the_nominal_rc_window() -> None:
    engine = RippleEngine(config=_tiny_config(), capacity_samples=64)
    engine.restart()
    for sequence in range(10):
        _feed(engine, [0.1, 0.2, 0.3, 0.4], [128, 129, 130, 131], sequence=sequence)

    settling = engine.snapshot()

    assert settling.settle_samples == 1
    assert settling.settled is True
    assert settling.settling_basis == "capture_start_assuming_preconnected"
    assert settling.excluded_prefix_samples == 1
    assert settling.settling_remaining_samples == 0
    assert settling.status is RippleStatus.READY
    assert settling.span_start_sample == 1
    assert settling.span_sample_count == 39
    assert settling.mean_v is not None
    assert settling.rms_ac_v is not None
    assert settling.vpp_v is not None


def test_rail_evidence_makes_span_unavailable_without_deleting_samples() -> None:
    engine = RippleEngine(config=_tiny_config(), capacity_samples=8)
    engine.restart()
    _feed(engine, [0.1, 0.1, -5.1, 0.1], [128, 128, 0, 128], sequence=0)
    _feed(engine, [0.1, 0.1, 0.1, 0.1], [128, 128, 128, 128], sequence=1)

    clipped = engine.snapshot()

    assert clipped.status is RippleStatus.UNAVAILABLE
    assert "clipped_span" in clipped.reason_codes
    assert clipped.clipped_low == 1
    assert clipped.clipped_high == 0
    assert clipped.clip_count_scope == "current_span"
    assert clipped.samples_received == 8
    assert (clipped.mean_v, clipped.rms_ac_v, clipped.vpp_v) == (None, None, None)

    _feed(engine, [0.1] * 4, [128] * 4, sequence=2)
    _feed(engine, [0.1] * 4, [128] * 4, sequence=3)

    recovered = engine.snapshot()

    assert recovered.samples_received == 16
    assert recovered.ring_sample_count == 8
    assert recovered.status is RippleStatus.READY
    assert recovered.mean_v == pytest.approx(0.1, abs=1e-6)
    assert recovered.rms_ac_v == pytest.approx(0.0, abs=1e-12)
    assert recovered.vpp_v == pytest.approx(0.0, abs=1e-12)


def test_gap_invalidates_span_and_changes_continuity() -> None:
    engine = RippleEngine(config=_tiny_config(), capacity_samples=64)
    engine.restart()
    _feed(engine, [0.1, 0.2], [128, 129], sequence=0)
    first = engine.snapshot()
    engine.absorb_block(
        np.asarray([0.3, 0.4], dtype=np.float32),
        raw=bytes([130, 131]),
        sequence=2,
        sample_start=4,
    )

    after = engine.snapshot()

    assert after.gap_count == first.gap_count + 1
    assert after.dropped_blocks == 1
    assert after.dropped_samples == 2
    assert after.continuity_id == first.continuity_id + 1
    assert after.span_start_sample == 4
    assert after.span_sample_count == 2


def test_initial_dropped_prefix_is_a_gap_not_silent_progress() -> None:
    engine = RippleEngine(config=_tiny_config())
    engine.restart()
    engine.absorb_block(
        np.asarray([0.1], dtype=np.float32),
        raw=bytes([128]),
        sequence=3,
        sample_start=3,
    )

    snapshot = engine.snapshot()

    assert snapshot.gap_count == 1
    assert snapshot.dropped_blocks == 3
    assert snapshot.dropped_samples == 3
    assert snapshot.continuity_id == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sample_rate_hz", 2_000.0),
        ("ch1_range_v", 1.0),
        ("probe_multiplier", 10.0),
        ("calibration_used", True),
    ],
)
def test_config_identity_change_invalidates_span(field: str, value: object) -> None:
    engine = RippleEngine(config=_tiny_config(), capacity_samples=64)
    engine.restart()
    _feed(engine, [0.1, 0.2], [128, 129], sequence=0)
    before = engine.snapshot()
    overrides: dict[str, object] = {field: value}
    if field == "probe_multiplier":
        overrides["adapter"] = AdapterSpec(cap_nf=0.001, probe_multiplier=10)
    engine.configure(_tiny_config(**overrides))  # pyright: ignore[reportArgumentType]
    after = engine.snapshot()

    assert after.config_id != before.config_id
    assert after.epoch_id == before.epoch_id + 1
    assert after.continuity_id == before.continuity_id + 1
    assert after.samples_received == 0
    assert after.span_start_sample is None
    assert (after.mean_v, after.rms_ac_v, after.vpp_v) == (None, None, None)


def test_stopped_status_drops_metric_values_but_keeps_custody() -> None:
    engine = RippleEngine(config=_tiny_config(), capacity_samples=64)
    engine.restart()
    _feed(engine, [0.1, 0.2, 0.3], [128, 129, 130], sequence=0)
    assert engine.snapshot().status is RippleStatus.READY

    engine.stop()
    stopped = engine.snapshot()

    assert stopped.status is RippleStatus.STOPPED
    assert "capture_stopped" in stopped.reason_codes
    assert stopped.samples_received == 3
    assert (stopped.mean_v, stopped.rms_ac_v, stopped.vpp_v) == (None, None, None)


def test_x10_probe_has_no_declared_settling_or_metrics() -> None:
    engine = RippleEngine(
        config=_tiny_config(probe_multiplier=10.0, adapter=None),
    )
    engine.restart()
    _feed(engine, [0.1, 0.2], [128, 129], sequence=0)

    snapshot = engine.snapshot()

    assert snapshot.settle_samples is None
    assert snapshot.status is RippleStatus.UNAVAILABLE
    assert "settling_unknown_unknown_probe_topology" in snapshot.reason_codes
    assert snapshot.settling_basis == "settling_unknown"
    assert snapshot.excluded_prefix_samples is None
    assert snapshot.settling_remaining_samples is None
    assert snapshot.adapter.probe_multiplier == 10.0
    assert snapshot.adapter.transfer_status == TransferStatus.UNAVAILABLE.value
    assert (snapshot.mean_v, snapshot.rms_ac_v, snapshot.vpp_v) == (None, None, None)


def test_live_preset_x10_is_unavailable_not_a_crash() -> None:
    config = RippleConfig.for_live(
        sample_rate_hz=1_000.0,
        ch1_range_v=5.0,
        probe_multiplier=10.0,
        calibration_used=False,
    )
    engine = RippleEngine(config=config)
    engine.restart()
    _feed(engine, [0.1, 0.2], [128, 129], sequence=0)

    snapshot = engine.snapshot()

    assert config.adapter is not None
    assert config.adapter.probe_multiplier == 10
    assert config.settle_samples is None
    assert snapshot.status is RippleStatus.UNAVAILABLE
    assert snapshot.adapter.transfer_status == TransferStatus.UNAVAILABLE.value
    assert snapshot.settling_basis == "settling_unknown"
    assert snapshot.excluded_prefix_samples is None
    assert (snapshot.mean_v, snapshot.rms_ac_v, snapshot.vpp_v) == (None, None, None)


def test_live_preset_nonintegral_probe_is_unavailable() -> None:
    config = RippleConfig.for_live(
        sample_rate_hz=1_000.0,
        ch1_range_v=5.0,
        probe_multiplier=2.5,
        calibration_used=False,
    )
    engine = RippleEngine(config=config)
    engine.restart()

    snapshot = engine.snapshot()

    assert config.adapter is None
    assert snapshot.status is RippleStatus.UNAVAILABLE
    assert snapshot.adapter.probe_multiplier == 2.5
    assert snapshot.adapter.transfer_status == TransferStatus.UNAVAILABLE.value
    assert snapshot.settling_basis == "settling_unknown"
    assert (snapshot.mean_v, snapshot.rms_ac_v, snapshot.vpp_v) == (None, None, None)


def test_nonintegral_probe_stays_honest_and_unavailable() -> None:
    engine = RippleEngine(config=_tiny_config(probe_multiplier=2.5, adapter=None))

    snapshot = engine.snapshot()

    assert snapshot.adapter.probe_multiplier == 2.5
    assert snapshot.adapter.transfer_status == TransferStatus.UNAVAILABLE.value
    assert snapshot.status is RippleStatus.UNAVAILABLE


def test_config_rejects_a_mismatched_adapter_probe() -> None:
    with pytest.raises(InputError, match="probe"):
        RippleConfig(
            adapter=AdapterSpec(probe_multiplier=1),
            probe_multiplier=10.0,
            sample_rate_hz=RATE_HZ,
            ch1_range_v=5.0,
            calibration_used=False,
        )


def test_engine_capacity_is_bounded_and_positive() -> None:
    with pytest.raises(InputError, match="capacity"):
        RippleEngine(config=_tiny_config(), capacity_samples=MIN_METRIC_SAMPLES - 1)


# ---------------------------------------------------------------------------
# сервис: тап до FrameStream.push, независимость от кадров, restart/trigger
# ---------------------------------------------------------------------------


def test_service_passes_startup_discard_to_the_engine() -> None:
    rig = service_rig(discard_lead_samples=123)

    assert rig.service.ripple.config.startup_discard_samples == 123


def test_tap_accumulates_full_blocks_without_any_trigger_frame() -> None:
    rig = service_rig()
    rig.service.start()
    rig.pump(8)

    snapshot = rig.service.ripple.snapshot()

    assert rig.frames == []
    assert snapshot.samples_received == 8 * BLOCK_SAMPLES_PER_CHANNEL
    assert snapshot.block_count == 8
    assert snapshot.gap_count == 0
    assert snapshot.continuity_basis == SYNTHETIC_EXACT


def test_sine_through_fake_scope_matches_independent_float64_analytics() -> None:
    rig = service_rig()
    rig.service.start()
    rig.pump(BLOCKS_TO_SETTLE)
    snapshot = rig.service.ripple.snapshot()

    assert snapshot.status is RippleStatus.READY
    assert snapshot.span_start_sample == SETTLE_SAMPLES
    expected = rig.reference_ch1(BLOCKS_TO_SETTLE).astype(np.float64)
    span = expected[
        snapshot.span_start_sample : snapshot.span_start_sample + snapshot.span_sample_count
    ]
    assert span.size == snapshot.span_sample_count
    mean_expected = float(np.mean(span))
    rms_expected = float(np.sqrt(np.mean((span - mean_expected) ** 2)))
    vpp_expected = float(np.max(span) - np.min(span))

    assert snapshot.mean_v == pytest.approx(mean_expected, rel=1e-12, abs=1e-15)
    assert snapshot.rms_ac_v == pytest.approx(rms_expected, rel=1e-12, abs=1e-15)
    assert snapshot.vpp_v == pytest.approx(vpp_expected, rel=1e-12, abs=1e-15)
    assert snapshot.rms_ac_v == pytest.approx(TONE_AMPLITUDE_V / math.sqrt(2.0), rel=0.02)
    assert snapshot.vpp_v == pytest.approx(2.0 * TONE_AMPLITUDE_V, rel=0.02)


def test_pending_overflow_is_stamped_before_discard_and_becomes_a_gap() -> None:
    clock = ManualClock()
    scope = _DripScope(profile=PROFILE, seed=SEED, sample_rate_hz=RATE_HZ, clock=clock)
    service = InstrumentService(
        scope_factory=_Factory(scope=scope),
        trigger=_normal_trigger(),
        sample_rate_hz=RATE_HZ,
        clock=clock,
        max_buffered_blocks=2,
        discard_lead_samples=0,
        continuity_basis=SYNTHETIC_EXACT,
    )
    service.start()
    callback = scope.on_block
    assert callback is not None
    callback(bytearray([128]), bytearray([128]))
    service.poll()
    first = service.ripple.snapshot()

    for _ in range(5):
        callback(bytearray([128]), bytearray([128]))
    service.poll()
    after = service.ripple.snapshot()

    assert service.dropped_blocks == 1
    assert after.gap_count == first.gap_count + 1
    assert after.dropped_blocks == 1
    assert after.dropped_samples == 1
    assert after.continuity_id == first.continuity_id + 1
    assert after.samples_received == 5


def test_trigger_only_change_preserves_the_span() -> None:
    rig = service_rig()
    rig.service.start()
    rig.pump(BLOCKS_TO_SETTLE)
    before = rig.service.ripple.snapshot()
    assert before.status is RippleStatus.READY

    rig.service.update_trigger(_edge_trigger())
    rig.pump(1)
    after = rig.service.ripple.snapshot()

    assert after.epoch_id == before.epoch_id
    assert after.config_id == before.config_id
    assert after.continuity_id == before.continuity_id
    assert after.span_start_sample == before.span_start_sample
    assert after.gap_count == before.gap_count
    assert after.samples_received > before.samples_received


def test_restart_gets_a_fresh_epoch_continuity_and_no_stale_gap() -> None:
    rig = service_rig()
    rig.service.start()
    rig.pump(1)
    first = rig.service.ripple.snapshot()

    rig.service.stop()
    rig.service.start()
    rig.pump(1)
    second = rig.service.ripple.snapshot()

    assert second.epoch_id == first.epoch_id + 1
    assert second.continuity_id > first.continuity_id
    assert second.gap_count == 0
    assert second.dropped_blocks == 0
    assert second.samples_received == BLOCK_SAMPLES_PER_CHANNEL


def test_gate_declares_synthetic_only_for_sim_mode(tmp_path: Path) -> None:
    sim = gate_rig(tmp_path, mode=LiveMode.SIM)
    real = gate_rig(tmp_path, mode=LiveMode.REAL)
    try:
        sim.start()
        real.start()
        assert sim.gate.service is not None
        assert real.gate.service is not None
        assert sim.gate.service.ripple.snapshot().continuity_basis == SYNTHETIC_EXACT
        assert real.gate.service.ripple.snapshot().continuity_basis == (
            "host_contiguous_unverified"
        )
    finally:
        sim.gate.stop()
        real.gate.stop()


# ---------------------------------------------------------------------------
# SSE: именованное событие ripple, независимое от кадров триггера
# ---------------------------------------------------------------------------


def test_ripple_sse_contract_carries_adapter_and_uncalibrated_label(tmp_path: Path) -> None:
    rig = gate_rig(tmp_path)

    async def scenario() -> list[ServerSentEvent]:
        events: list[ServerSentEvent] = []
        started = False
        async for event in live_stream(rig.gate):
            events.append(event)
            if not started:
                assert event.event == "heartbeat"
                rig.start()
                started = True
            elif any(item.event == "ripple" for item in events):
                break
            assert len(events) < EVENT_LIMIT
        return events

    try:
        events = asyncio.run(scenario())
    finally:
        rig.gate.stop()

    ripple = _ripples(events)
    assert ripple
    payload = ripple[0]
    assert payload.status is RippleStatus.SETTLING
    assert payload.voltage_label == UNCALIBRATED_VOLTS_LABEL_RU
    assert payload.adapter.cap_nf == 100.0
    assert payload.adapter.series_r_ohm == 0.0
    assert payload.adapter.probe_multiplier == 1.0
    assert payload.adapter.transfer_status == TransferStatus.NOMINAL.value
    assert payload.adapter.hardware_qualification == "unverified"
    assert payload.adapter.component_values_basis == "nominal"
    assert payload.adapter.settle_samples == SETTLE_SAMPLES
    assert payload.continuity_basis == SYNTHETIC_EXACT
    assert payload.calibration_used is False
    assert payload.settling_basis == "capture_start_assuming_preconnected"
    assert payload.startup_discard_samples == 0
    assert payload.excluded_prefix_samples == SETTLE_SAMPLES
    assert payload.settling_remaining_samples == SETTLE_SAMPLES - payload.samples_received
    assert payload.clip_count_scope == "current_span"
    assert (payload.mean_v, payload.rms_ac_v, payload.vpp_v) == (None, None, None)


def test_ripple_ready_is_published_without_trigger_frames(tmp_path: Path) -> None:
    rig = gate_rig(tmp_path)
    advanced = False

    async def scenario() -> list[ServerSentEvent]:
        nonlocal advanced
        events: list[ServerSentEvent] = []
        started = False
        advanced = False
        async for event in live_stream(rig.gate):
            events.append(event)
            if not started:
                assert event.event == "heartbeat"
                rig.start()
                started = True
            elif not advanced and any(
                item.event == "ripple" and item.data.status is RippleStatus.SETTLING
                for item in events
                if isinstance(item.data, LiveRipplePayload)
            ):
                rig.advance_blocks(BLOCKS_TO_SETTLE)
                advanced = True
            if any(
                item.event == "ripple" and item.data.status is RippleStatus.READY
                for item in events
                if isinstance(item.data, LiveRipplePayload)
            ):
                break
            assert len(events) < EVENT_LIMIT
        return events

    try:
        events = asyncio.run(scenario())
    finally:
        rig.gate.stop()

    assert advanced
    assert not any(event.event == "frame" for event in events)
    ready = [payload for payload in _ripples(events) if payload.status is RippleStatus.READY]
    assert ready
    for payload in _ripples(events):
        assert payload.adapter.cap_nf == 100.0
        assert payload.voltage_label == UNCALIBRATED_VOLTS_LABEL_RU
    assert ready[-1].mean_v is not None
    assert ready[-1].rms_ac_v is not None
    assert ready[-1].vpp_v is not None
    assert ready[-1].span_sample_count > 0


class _SnapshotCounter:
    """Обёртка движка: считает, сколько раз эмиттер построил снимок."""

    _engine: RippleEngine
    calls: int

    def __init__(self, engine: RippleEngine) -> None:
        self._engine = engine
        self.calls = 0

    def snapshot(self) -> object:
        self.calls += 1
        return self._engine.snapshot()


def test_ripple_emitter_does_not_compute_snapshot_between_intervals() -> None:
    engine = RippleEngine(config=_tiny_config())
    engine.restart()
    counter = _SnapshotCounter(engine)
    emitter = RippleEmitter(interval_s=1_000.0)
    counted = cast("RippleEngine", cast("object", counter))

    assert emitter.event_if_due(counted) is not None
    assert counter.calls == 1
    assert emitter.event_if_due(counted) is None
    assert counter.calls == 1


def test_ripple_emitter_rate_limits_but_forces_stopped() -> None:
    rig = service_rig()
    rig.service.start()
    emitter = RippleEmitter(interval_s=1_000.0)
    try:
        first = emitter.event_if_due(rig.service.ripple)
        second = emitter.event_if_due(rig.service.ripple)
        assert first is not None
        assert second is None
        rig.service.stop()
        forced = emitter.event_if_due(rig.service.ripple, force=True)
        assert forced is not None
        assert isinstance(forced.data, LiveRipplePayload)
        assert forced.data.status is RippleStatus.STOPPED
    finally:
        rig.service.stop()


def test_stop_publishes_a_stopped_ripple_and_ends_the_stream(tmp_path: Path) -> None:
    rig = gate_rig(tmp_path)
    stopped = False

    async def scenario() -> list[ServerSentEvent]:
        nonlocal stopped
        events: list[ServerSentEvent] = []
        started = False
        stopped = False
        async for event in live_stream(rig.gate):
            events.append(event)
            if not started:
                assert event.event == "heartbeat"
                rig.start()
                started = True
            elif not stopped and _ripples(events):
                rig.gate.stop()
                stopped = True
            assert len(events) < EVENT_LIMIT
        return events

    events = asyncio.run(scenario())

    assert stopped
    stopped_payloads = [
        payload for payload in _ripples(events) if payload.status is RippleStatus.STOPPED
    ]
    assert stopped_payloads
    assert stopped_payloads[-1].status is RippleStatus.STOPPED
    assert (stopped_payloads[-1].mean_v, stopped_payloads[-1].rms_ac_v) == (None, None)
    assert rig.gate.is_active is False


def test_stop_after_ready_publishes_stopped_before_the_final_frame(tmp_path: Path) -> None:
    rig = gate_rig(tmp_path)
    advanced = False
    stopped = False

    async def scenario() -> list[ServerSentEvent]:
        nonlocal advanced, stopped
        events: list[ServerSentEvent] = []
        started = False
        async for event in live_stream(rig.gate):
            events.append(event)
            if not started:
                assert event.event == "heartbeat"
                rig.start()
                started = True
            elif not advanced and _ripples(events):
                rig.advance_blocks(BLOCKS_TO_SETTLE)
                advanced = True
            elif not stopped and any(
                payload.status is RippleStatus.READY for payload in _ripples(events)
            ):
                rig.gate.stop()
                stopped = True
            assert len(events) < EVENT_LIMIT
        return events

    events = asyncio.run(scenario())

    assert advanced
    assert stopped
    statuses = [payload.status for payload in _ripples(events)]
    assert RippleStatus.READY in statuses
    assert statuses[-1] is RippleStatus.STOPPED
    assert events[-1].event == "frame"


def test_reconnect_reads_the_same_accumulator_without_resetting(tmp_path: Path) -> None:
    rig = gate_rig(tmp_path)

    async def first() -> LiveRipplePayload:
        started = False
        async for event in live_stream(rig.gate):
            if not started:
                assert event.event == "heartbeat"
                rig.start()
                started = True
                rig.advance_blocks(8)
                continue
            if (
                event.event == "ripple"
                and isinstance(event.data, LiveRipplePayload)
                and event.data.samples_received >= 8 * BLOCK_SAMPLES_PER_CHANNEL
            ):
                return event.data
        pytest.fail("первый стрим не отдал ripple")

    async def second() -> LiveRipplePayload:
        async for event in live_stream(rig.gate):
            if event.event == "ripple" and isinstance(event.data, LiveRipplePayload):
                return event.data
        pytest.fail("второй стрим не отдал ripple")

    try:
        before = asyncio.run(first())
        after = asyncio.run(second())
    finally:
        rig.gate.stop()

    assert after.epoch_id == before.epoch_id
    assert after.config_id == before.config_id
    assert after.continuity_id == before.continuity_id
    assert after.samples_received >= before.samples_received
    assert after.samples_received > 0


def test_ripple_payload_enforces_metrics_only_when_ready() -> None:
    engine = RippleEngine(config=_tiny_config())
    engine.restart()
    _feed(engine, [0.1, 0.2, 0.3], [128, 129, 130], sequence=0)
    payload = ripple_payload(engine.snapshot())
    assert payload.status is RippleStatus.READY
    settling = payload.model_dump(mode="json")
    settling["status"] = RippleStatus.SETTLING.value

    with pytest.raises(ValidationError):
        LiveRipplePayload.model_validate(settling)

    tampered = payload.model_dump(mode="json")
    tampered["rms_ac_v"] = None
    with pytest.raises(ValidationError):
        LiveRipplePayload.model_validate(tampered)


def test_ripple_ring_is_bounded_by_default() -> None:
    engine = RippleEngine(config=_tiny_config())
    assert engine.capacity_samples == RIPPLE_BUFFER_SAMPLES
    assert MIN_METRIC_SAMPLES == 2
