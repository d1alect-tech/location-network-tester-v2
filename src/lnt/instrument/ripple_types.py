"""Типы живого риппла: статусы, идентичности, конфигурация и снимок кольца.

Модуль не считает метрики и не трогает прибор: он фиксирует словарь статусов и
провенанса, который SSE-клиент проверяет строго. Номинальный adapter preset
и его вид события живут в ``ripple_adapter_view``.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from lnt.errors import InputError
from lnt.instrument.ripple_adapter_view import (
    RippleAdapterView,
    build_adapter_view,
    default_adapter,
)

if TYPE_CHECKING:
    from lnt.ripple.adapter import AdapterSpec

RIPPLE_BUFFER_SAMPLES: Final = 2**19
MIN_METRIC_SAMPLES: Final = 2
UNCALIBRATED_VOLTS_LABEL_RU: Final = "некалиброванные вольты"
HOST_CONTIGUOUS_UNVERIFIED: Final = "host_contiguous_unverified"
SYNTHETIC_EXACT: Final = "synthetic_exact"
CONTINUITY_BASES: Final = frozenset({HOST_CONTIGUOUS_UNVERIFIED, SYNTHETIC_EXACT})

REASON_SETTLING: Final = "settling_window"
REASON_SETTLING_UNKNOWN: Final = "settling_unknown_unknown_probe_topology"
REASON_INSUFFICIENT: Final = "insufficient_samples"
REASON_GAP_RESET: Final = "gap_reset"
REASON_CLIPPED: Final = "clipped_span"
REASON_METRICS: Final = "metrics_unavailable"
REASON_STOPPED: Final = "capture_stopped"
SETTLING_BASIS_PRECONNECTED: Final = "capture_start_assuming_preconnected"
SETTLING_BASIS_UNKNOWN: Final = "settling_unknown"
CLIP_COUNT_SCOPE_CURRENT_SPAN: Final = "current_span"


class RippleStatus(StrEnum):
    """Статус живого измерения: числа есть только у ``ready``."""

    SETTLING = "settling"
    UNAVAILABLE = "unavailable"
    READY = "ready"
    STOPPED = "stopped"


def continuity_basis_for(mode_value: str) -> str:
    """Объявленный режим: только детерминированный фейк даёт ``synthetic_exact``."""
    return SYNTHETIC_EXACT if mode_value == "sim" else HOST_CONTIGUOUS_UNVERIFIED


@dataclass(frozen=True, slots=True, kw_only=True)
class RippleConfig:
    """Неизменяемая конфигурация одного кольца: геометрия, пробник, адаптер."""

    adapter: AdapterSpec | None
    probe_multiplier: float
    sample_rate_hz: float
    ch1_range_v: float
    calibration_used: bool
    continuity_basis: str = HOST_CONTIGUOUS_UNVERIFIED
    startup_discard_samples: int = 0
    min_metric_samples: int = MIN_METRIC_SAMPLES

    def __post_init__(self) -> None:
        """Отклоняет нефизическую геометрию и несогласованный адаптер."""
        rate = _positive("sample_rate_hz", self.sample_rate_hz)
        range_v = _positive("ch1_range_v", self.ch1_range_v)
        probe = _positive("probe_multiplier", self.probe_multiplier)
        startup = _nonnegative_int("startup_discard_samples", self.startup_discard_samples)
        if self.continuity_basis not in CONTINUITY_BASES:
            raise InputError(f"риппл: неизвестная база непрерывности {self.continuity_basis!r}")
        if self.min_metric_samples < MIN_METRIC_SAMPLES:
            raise InputError("риппл: min_metric_samples должен быть >= 2")
        adapter = self.adapter
        if adapter is not None:
            consistent = probe.is_integer() and adapter.probe_multiplier == int(probe)
            if not consistent:
                raise InputError("риппл: probe_multiplier адаптера не совпадает с живым конфигом")
        object.__setattr__(self, "sample_rate_hz", rate)
        object.__setattr__(self, "ch1_range_v", range_v)
        object.__setattr__(self, "probe_multiplier", probe)
        object.__setattr__(self, "startup_discard_samples", startup)

    @classmethod
    def for_live(  # noqa: PLR0913 - живой preset: каждая ручка kw-only
        cls,
        *,
        sample_rate_hz: float,
        ch1_range_v: float,
        probe_multiplier: float,
        calibration_used: bool,
        continuity_basis: str = HOST_CONTIGUOUS_UNVERIFIED,
        startup_discard_samples: int = 0,
    ) -> RippleConfig:
        """Живой preset: номинальный адаптер и пробник из текущего конфига."""
        probe = _positive("probe_multiplier", probe_multiplier)
        return cls(
            adapter=default_adapter(probe),
            probe_multiplier=probe,
            sample_rate_hz=sample_rate_hz,
            ch1_range_v=ch1_range_v,
            calibration_used=calibration_used,
            continuity_basis=continuity_basis,
            startup_discard_samples=startup_discard_samples,
        )

    @property
    def config_id(self) -> str:
        """Короткая детерминированная идентичность конфигурации."""
        payload = {
            "adapter": None
            if self.adapter is None
            else {
                "cap_nf": self.adapter.cap_nf,
                "series_r_ohm": self.adapter.series_r_ohm,
                "probe_multiplier": self.adapter.probe_multiplier,
                "basis": self.adapter.component_values_basis.value,
            },
            "probe_multiplier": self.probe_multiplier,
            "sample_rate_hz": self.sample_rate_hz,
            "ch1_range_v": self.ch1_range_v,
            "calibration_used": self.calibration_used,
            "continuity_basis": self.continuity_basis,
            "startup_discard_samples": self.startup_discard_samples,
            "min_metric_samples": self.min_metric_samples,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    @property
    def settle_samples(self) -> int | None:
        """Номинальное окно 10*tau в отсчётах, либо ``None`` без модели."""
        if self.adapter is None:
            return None
        return self.adapter.settle_samples(self.sample_rate_hz)

    @property
    def settling_basis(self) -> str:
        """Основание окна: старт захвата как «уже подключено», либо неизвестно."""
        if self.settle_samples is None:
            return SETTLING_BASIS_UNKNOWN
        return SETTLING_BASIS_PRECONNECTED

    @property
    def adapter_view(self) -> RippleAdapterView:
        """Провенанс адаптера для каждого события."""
        return build_adapter_view(
            self.adapter,
            probe_multiplier=self.probe_multiplier,
            sample_rate_hz=self.sample_rate_hz,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RippleSnapshot:
    """Согласованный снимок кольца: статус, идентичности, метрики и QC."""

    status: RippleStatus
    reason_codes: tuple[str, ...]
    epoch_id: int
    config_id: str
    continuity_id: int
    continuity_basis: str
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
    startup_discard_samples: int
    settling_basis: str
    settling_remaining_samples: int | None
    excluded_prefix_samples: int | None
    span_start_sample: int | None
    span_sample_count: int
    span_duration_s: float | None
    mean_v: float | None
    rms_ac_v: float | None
    vpp_v: float | None
    clipped_low: int
    clipped_high: int
    clip_count_scope: str
    sample_rate_hz: float
    ch1_range_v: float
    ch1_probe_multiplier: float
    calibration_used: bool
    voltage_label: str
    adapter: RippleAdapterView


def _positive(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"риппл: {name} должен быть конечным числом > 0")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise InputError(f"риппл: {name} должен быть конечным числом > 0")
    return number


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputError(f"риппл: {name} должен быть целым >= 0")
    return value
