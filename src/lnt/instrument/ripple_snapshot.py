"""Публичный снимок живого риппла: статус, участок, QC рельсов и метрики.

Чистая функция от состояния кольца: чисел нет, пока не закрыто окно
установления, нет непрерывного участка нужной длины или в нём есть рельсы АЦП.
Клиппинг не удаляет отсчёты — он делает публичный участок недоступным.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.instrument.ripple_types import (
    CLIP_COUNT_SCOPE_CURRENT_SPAN,
    REASON_CLIPPED,
    REASON_GAP_RESET,
    REASON_INSUFFICIENT,
    REASON_METRICS,
    REASON_SETTLING,
    REASON_SETTLING_UNKNOWN,
    REASON_STOPPED,
    UNCALIBRATED_VOLTS_LABEL_RU,
    RippleConfig,
    RippleSnapshot,
    RippleStatus,
)
from lnt.ripple.metrics import mean_v, rms_ac_v, vpp_v
from lnt.scope_io import RAW_HIGH, RAW_LOW

Float32Array = NDArray[np.float32]
_RAIL_LOW_CODE: Final = -1.0
_RAIL_HIGH_CODE: Final = 1.0


@dataclass(frozen=True, slots=True, kw_only=True)
class RippleState:
    """Неизменяемый вход рендера: конфигурация, кольцо и счётчики эпохи."""

    config: RippleConfig
    capacity_samples: int
    samples: Float32Array
    rails: Float32Array
    epoch_id: int
    continuity_id: int
    capture_samples: int
    observed_total: int
    span_start_abs: int
    block_count: int
    gap_count: int
    dropped_blocks: int
    dropped_samples: int
    span_from_gap: bool
    stopped: bool


def build_snapshot(state: RippleState) -> RippleSnapshot:
    """Собирает снимок; числа считаются только по чистому непрерывному участку."""
    config = state.config
    ring_count = int(state.samples.size)
    oldest_abs = state.capture_samples - ring_count
    settle = config.settle_samples
    startup = config.startup_discard_samples
    excluded_prefix = None if settle is None else max(settle, startup)
    settled = excluded_prefix is not None and state.capture_samples >= excluded_prefix
    span_floor = max(state.span_start_abs, settle, startup) if settled and settle is not None else 0
    start_abs = max(span_floor, oldest_abs) if settled else None
    settling_remaining = (
        None if excluded_prefix is None else max(excluded_prefix - state.capture_samples, 0)
    )
    span_count = 0 if start_abs is None else max(state.capture_samples - start_abs, 0)
    offset = 0 if start_abs is None else start_abs - oldest_abs
    span = state.samples[offset : offset + span_count]
    span_rails = state.rails[offset : offset + span_count]
    clipped_low = int(np.count_nonzero(span_rails < 0.0))
    clipped_high = int(np.count_nonzero(span_rails > 0.0))
    clipped = clipped_low + clipped_high
    status = _status(state=state, settled=settled, span_count=span_count, clipped=clipped)
    metrics = _metrics(status=status, span=span)
    metrics_failed = status is RippleStatus.READY and any(value is None for value in metrics)
    if metrics_failed:
        status = RippleStatus.UNAVAILABLE
    duration = None if start_abs is None else span_count / config.sample_rate_hz
    return RippleSnapshot(
        status=status,
        reason_codes=_reasons(
            state=state,
            status=status,
            span_count=span_count,
            clipped=clipped,
            metrics_failed=metrics_failed,
        ),
        epoch_id=state.epoch_id,
        config_id=config.config_id,
        continuity_id=state.continuity_id,
        continuity_basis=config.continuity_basis,
        gap_count=state.gap_count,
        block_count=state.block_count,
        dropped_blocks=state.dropped_blocks,
        dropped_samples=state.dropped_samples,
        samples_received=state.observed_total,
        sample_progress=state.capture_samples,
        ring_capacity_samples=state.capacity_samples,
        ring_sample_count=ring_count,
        ring_limited=start_abs is not None and start_abs > span_floor,
        settle_samples=settle,
        settled=settled,
        startup_discard_samples=startup,
        settling_basis=config.settling_basis,
        settling_remaining_samples=settling_remaining,
        excluded_prefix_samples=excluded_prefix,
        span_start_sample=start_abs,
        span_sample_count=span_count,
        span_duration_s=duration,
        mean_v=metrics[0],
        rms_ac_v=metrics[1],
        vpp_v=metrics[2],
        clipped_low=clipped_low,
        clipped_high=clipped_high,
        clip_count_scope=CLIP_COUNT_SCOPE_CURRENT_SPAN,
        sample_rate_hz=config.sample_rate_hz,
        ch1_range_v=config.ch1_range_v,
        ch1_probe_multiplier=config.probe_multiplier,
        calibration_used=config.calibration_used,
        voltage_label=UNCALIBRATED_VOLTS_LABEL_RU,
        adapter=config.adapter_view,
    )


def rail_codes(raw: object) -> Float32Array:
    """Сырые рельсы блока: -1 низ, +1 верх, 0 чисто (без удаления отсчётов)."""
    counts = np.frombuffer(bytes(cast("bytearray", raw)), dtype=np.uint8)
    codes = np.zeros(counts.size, dtype=np.float32)
    codes[counts == RAW_LOW] = _RAIL_LOW_CODE
    codes[counts == RAW_HIGH] = _RAIL_HIGH_CODE
    return codes


def _status(
    *,
    state: RippleState,
    settled: bool,
    span_count: int,
    clipped: int,
) -> RippleStatus:
    if state.stopped:
        return RippleStatus.STOPPED
    if state.config.settle_samples is None:
        return RippleStatus.UNAVAILABLE
    if not settled:
        return RippleStatus.SETTLING
    if span_count < state.config.min_metric_samples or clipped > 0:
        return RippleStatus.UNAVAILABLE
    return RippleStatus.READY


def _reasons(  # noqa: PLR0911 - статусный разбор читается ранними выходами
    *,
    state: RippleState,
    status: RippleStatus,
    span_count: int,
    clipped: int,
    metrics_failed: bool,
) -> tuple[str, ...]:
    if status is RippleStatus.STOPPED:
        return (REASON_STOPPED,)
    if metrics_failed:
        return (REASON_METRICS,)
    if state.config.settle_samples is None:
        return (REASON_SETTLING_UNKNOWN,)
    if status is RippleStatus.SETTLING:
        return (REASON_SETTLING,)
    if span_count < state.config.min_metric_samples:
        extra = (REASON_GAP_RESET,) if state.span_from_gap else ()
        return (*extra, REASON_INSUFFICIENT)
    if clipped > 0:
        return (REASON_CLIPPED,)
    return ()


def _metrics(
    *,
    status: RippleStatus,
    span: Float32Array,
) -> tuple[float | None, float | None, float | None]:
    if status is not RippleStatus.READY:
        return (None, None, None)
    try:
        return (mean_v(span), rms_ac_v(span), vpp_v(span))
    except InputError:
        return (None, None, None)
