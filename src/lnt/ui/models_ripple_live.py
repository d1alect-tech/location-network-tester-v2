"""Проводной контракт живого риппла: строгая модель отдельного SSE-события.

Событие ``ripple`` не смешивается с кадром: у него свои статус, эпоха/непрерывность,
окно установления, QC рельсов и параметры адаптера. Числа присутствуют только
при ``ready``; недоступное — ``null``, никогда NaN/Infinity. Подпись
«некалиброванные вольты» обязательна в каждом событии.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lnt.instrument.ripple_types import RippleSnapshot, RippleStatus

type _FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
type _NonNegativeInt = Annotated[int, Field(ge=0)]
type _ContinuityBasis = Literal["host_contiguous_unverified", "synthetic_exact"]
type _SettlingBasis = Literal["capture_start_assuming_preconnected", "settling_unknown"]
type _ClipCountScope = Literal["current_span"]
type _VoltageLabel = Literal["некалиброванные вольты"]


class _StrictModel(BaseModel):
    """Неизвестные поля отклоняются, значение неизменяемо."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class RippleAdapterPayload(_StrictModel):
    """Параметры номинального AC-адаптера и честная доступность переноса."""

    topology_id: str
    cap_nf: _FiniteFloat
    series_r_ohm: _FiniteFloat
    probe_multiplier: _FiniteFloat
    component_values_basis: str
    hardware_qualification: str
    transfer_status: str
    rail_nominal_v: _FiniteFloat | None = None
    tau_s: _FiniteFloat | None = None
    fc_hz: _FiniteFloat | None = None
    settling_s: _FiniteFloat | None = None
    settle_samples: int | None = None
    assumption_codes: tuple[str, ...]


class LiveRipplePayload(_StrictModel):
    """Снимок полного тракта: статус, идентичности, метрики и QC."""

    status: RippleStatus
    reason_codes: tuple[str, ...]
    epoch_id: int
    config_id: str
    continuity_id: int
    continuity_basis: _ContinuityBasis
    gap_count: int
    block_count: int
    dropped_blocks: int
    dropped_samples: int
    samples_received: int
    sample_progress: int
    ring_capacity_samples: int
    ring_sample_count: int
    ring_limited: bool
    settle_samples: int | None
    settled: bool
    startup_discard_samples: _NonNegativeInt
    settling_basis: _SettlingBasis
    settling_remaining_samples: _NonNegativeInt | None
    excluded_prefix_samples: _NonNegativeInt | None
    span_start_sample: int | None
    span_sample_count: int
    span_duration_s: _FiniteFloat | None
    mean_v: _FiniteFloat | None
    rms_ac_v: _FiniteFloat | None
    vpp_v: _FiniteFloat | None
    clipped_low: int
    clipped_high: int
    clip_count_scope: _ClipCountScope
    sample_rate_hz: _FiniteFloat
    ch1_range_v: _FiniteFloat
    ch1_probe_multiplier: _FiniteFloat
    calibration_used: bool
    voltage_label: _VoltageLabel
    adapter: RippleAdapterPayload

    @model_validator(mode="after")
    def _metrics_follow_status(self) -> Self:
        """Инвариант статуса: числа ровно у ``ready``, иначе все три ``null``."""
        values = (self.mean_v, self.rms_ac_v, self.vpp_v)
        if self.status is RippleStatus.READY:
            if any(value is None for value in values):
                raise ValueError("ripple: ready обязан нести mean/rms/vpp")
        elif any(value is not None for value in values):
            raise ValueError("ripple: не-ready не может нести числовые метрики")
        return self

    @model_validator(mode="after")
    def _settling_provenance_is_consistent(self) -> Self:
        """Окно установления и его основание не противоречат друг другу."""
        if self.settle_samples is None:
            if self.settling_basis != "settling_unknown":
                raise ValueError("ripple: без окна установления basis обязан быть settling_unknown")
            if self.excluded_prefix_samples is not None:
                raise ValueError("ripple: unknown settling не может нести excluded_prefix_samples")
            if self.settling_remaining_samples is not None:
                raise ValueError("ripple: unknown settling не может нести remaining")
            return self
        if self.settling_basis != "capture_start_assuming_preconnected":
            raise ValueError("ripple: известное окно требует preconnected-основания")
        if self.excluded_prefix_samples != max(self.settle_samples, self.startup_discard_samples):
            raise ValueError("ripple: excluded_prefix_samples не совпадает с границей старта")
        if self.settling_remaining_samples is None:
            raise ValueError("ripple: известное окно требует settling_remaining_samples")
        return self


def ripple_payload(snapshot: RippleSnapshot) -> LiveRipplePayload:
    """Снимок кольца → строгое событие ``ripple`` (без пересчёта метрик)."""
    adapter = snapshot.adapter
    return LiveRipplePayload(
        status=snapshot.status,
        reason_codes=snapshot.reason_codes,
        epoch_id=snapshot.epoch_id,
        config_id=snapshot.config_id,
        continuity_id=snapshot.continuity_id,
        continuity_basis=cast("_ContinuityBasis", snapshot.continuity_basis),
        gap_count=snapshot.gap_count,
        block_count=snapshot.block_count,
        dropped_blocks=snapshot.dropped_blocks,
        dropped_samples=snapshot.dropped_samples,
        samples_received=snapshot.samples_received,
        sample_progress=snapshot.sample_progress,
        ring_capacity_samples=snapshot.ring_capacity_samples,
        ring_sample_count=snapshot.ring_sample_count,
        ring_limited=snapshot.ring_limited,
        settle_samples=snapshot.settle_samples,
        settled=snapshot.settled,
        startup_discard_samples=snapshot.startup_discard_samples,
        settling_basis=cast("_SettlingBasis", snapshot.settling_basis),
        settling_remaining_samples=snapshot.settling_remaining_samples,
        excluded_prefix_samples=snapshot.excluded_prefix_samples,
        span_start_sample=snapshot.span_start_sample,
        span_sample_count=snapshot.span_sample_count,
        span_duration_s=snapshot.span_duration_s,
        mean_v=snapshot.mean_v,
        rms_ac_v=snapshot.rms_ac_v,
        vpp_v=snapshot.vpp_v,
        clipped_low=snapshot.clipped_low,
        clipped_high=snapshot.clipped_high,
        clip_count_scope=cast("_ClipCountScope", snapshot.clip_count_scope),
        sample_rate_hz=snapshot.sample_rate_hz,
        ch1_range_v=snapshot.ch1_range_v,
        ch1_probe_multiplier=snapshot.ch1_probe_multiplier,
        calibration_used=snapshot.calibration_used,
        voltage_label=cast("_VoltageLabel", snapshot.voltage_label),
        adapter=RippleAdapterPayload(
            topology_id=adapter.topology_id,
            cap_nf=adapter.cap_nf,
            series_r_ohm=adapter.series_r_ohm,
            probe_multiplier=adapter.probe_multiplier,
            component_values_basis=adapter.component_values_basis,
            hardware_qualification=adapter.hardware_qualification,
            transfer_status=adapter.transfer_status,
            rail_nominal_v=adapter.rail_nominal_v,
            tau_s=adapter.tau_s,
            fc_hz=adapter.fc_hz,
            settling_s=adapter.settling_s,
            settle_samples=adapter.settle_samples,
            assumption_codes=adapter.assumption_codes,
        ),
    )
