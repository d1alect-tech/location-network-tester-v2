"""Детерминированный сбор безопасного автоматического metadata snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from lnt.metadata_probes import (
    BuildInfo,
    DeviceDiagnostic,
    HantekDeviceProbe,
    PlatformDiagnostic,
    SystemPlatformProbe,
    production_build_info,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from lnt.profiles import FrontEndProfile
    from lnt.types import AcquisitionTelemetry, ChannelMode

type MetadataValue = str | int | float | bool | tuple[int, ...] | tuple[float, ...]

__all__ = [
    "AcquisitionSettings",
    "BuildInfo",
    "DeviceDiagnostic",
    "MetadataCollector",
    "MetadataField",
    "MetadataSnapshot",
    "PlatformDiagnostic",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadataField:
    """Собранное значение либо явная причина его недоступности."""

    value: MetadataValue | None
    reason_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AcquisitionSettings:
    """Настройки, действовавшие для конкретного захвата."""

    sample_rate_hz: float
    sample_count: int
    probe_multiplier: float
    range_v: float
    channel_mode: ChannelMode
    front_end: FrontEndProfile


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadataSnapshot:
    """Версионированный privacy-bounded снимок автоматических полей."""

    schema_version: int
    captured_at: str
    fields: Mapping[str, MetadataField]

    def to_json(self) -> str:
        """Сериализует снимок с устойчивой сортировкой ключей."""
        payload = {
            "schema_version": self.schema_version,
            "captured_at": self.captured_at,
            "fields": {
                key: {"value": field.value, "reason_code": field.reason_code}
                for key, field in sorted(self.fields.items())
            },
        }
        return (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            + "\n"
        )


class PlatformProbe(Protocol):
    """Поставщик только разрешённой информации ОС."""

    def diagnose(self) -> PlatformDiagnostic:
        """Возвращает разрешённую диагностику платформы."""
        ...


class DeviceProbe(Protocol):
    """Поставщик ограниченной диагностики измерительного устройства."""

    def diagnose(self) -> DeviceDiagnostic:
        """Возвращает разрешённую диагностику устройства."""
        ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class MetadataCollector:
    """Материализует разрешённый набор metadata из внедрённых providers."""

    def __init__(
        self,
        *,
        clock: Callable[[], str] = _utc_now,
        platform_probe: PlatformProbe | None = None,
        device_probe: DeviceProbe | None = None,
        build: BuildInfo | None = None,
    ) -> None:
        """Внедряет deterministic providers либо безопасные production defaults."""
        self._clock: Callable[[], str] = clock
        self._platform: PlatformProbe = platform_probe or SystemPlatformProbe()
        self._device: DeviceProbe = device_probe or HantekDeviceProbe()
        self._build: BuildInfo = build or production_build_info()

    def collect(
        self,
        *,
        settings: AcquisitionSettings,
        telemetry: AcquisitionTelemetry | None,
    ) -> MetadataSnapshot:
        """Собирает snapshot; недоступное устройство не прерывает сбор."""
        system = self._platform.diagnose()
        device = self._device.diagnose()
        fields = self._base_fields(system, device, settings)
        fields.update(_telemetry_fields(telemetry))
        return MetadataSnapshot(
            schema_version=1,
            captured_at=self._clock(),
            fields=MappingProxyType(fields),
        )

    def _base_fields(
        self,
        system: PlatformDiagnostic,
        device: DeviceDiagnostic,
        settings: AcquisitionSettings,
    ) -> dict[str, MetadataField]:
        available = _available
        return {
            "lnt.version": available(self._build.version),
            "lnt.build": available(self._build.build),
            "lnt.mode": available("frozen" if self._build.frozen else "dev"),
            "os.version": available(system.os_version),
            "os.architecture": available(system.architecture),
            "os.timezone": available(system.timezone),
            "device.vid": _device_field(device.vid, device.reason_code),
            "device.pid": _device_field(device.pid, device.reason_code),
            "device.model": _device_field(device.model, device.reason_code),
            "device.firmware": _device_field(device.firmware, device.reason_code),
            "device.driver": _device_field(device.driver, device.reason_code),
            "sample.rate_hz": available(settings.sample_rate_hz),
            "sample.count": available(settings.sample_count),
            "probe.multiplier": available(settings.probe_multiplier),
            "range.v": available(settings.range_v),
            "channel.mode": available(settings.channel_mode.value),
            "front_end.resistance_ohm": available(settings.front_end.resistance.value),
            "front_end.c1_f": available(settings.front_end.c1.value),
            "front_end.c2_f": available(settings.front_end.c2.value),
        }


def _available(value: MetadataValue) -> MetadataField:
    return MetadataField(value=value, reason_code=None)


def _device_field(value: str | None, reason_code: str | None) -> MetadataField:
    if value is None:
        return MetadataField(value=None, reason_code=reason_code or "device_field_unavailable")
    return _available(value)


def _telemetry_fields(telemetry: AcquisitionTelemetry | None) -> dict[str, MetadataField]:
    if telemetry is None:
        unavailable = MetadataField(value=None, reason_code="telemetry_unavailable")
        return dict.fromkeys(_TELEMETRY_KEYS, unavailable)
    return {
        "acquisition.telemetry": _available("available"),
        "acquisition.requested_samples": _available(telemetry.requested_samples),
        "acquisition.captured_samples": _available(telemetry.captured_samples),
        "acquisition.callback_count": _available(telemetry.callback_count),
        "acquisition.block_lengths": _available(telemetry.block_lengths),
        "acquisition.callback_gaps_s": _available(telemetry.callback_gaps_s),
        "acquisition.expected_block_interval_s": _available(telemetry.expected_block_interval_s),
        "acquisition.short_block_count": _available(telemetry.short_block_count),
        "acquisition.ch1_clip_low_count": _available(telemetry.ch1_clip_low_count),
        "acquisition.ch1_clip_high_count": _available(telemetry.ch1_clip_high_count),
        "acquisition.ch2_clip_low_count": _available(telemetry.ch2_clip_low_count),
        "acquisition.ch2_clip_high_count": _available(telemetry.ch2_clip_high_count),
        "acquisition.calibration_used": _available(telemetry.calibration_used),
    }


_TELEMETRY_KEYS = (
    "acquisition.telemetry",
    "acquisition.requested_samples",
    "acquisition.captured_samples",
    "acquisition.callback_count",
    "acquisition.block_lengths",
    "acquisition.callback_gaps_s",
    "acquisition.expected_block_interval_s",
    "acquisition.short_block_count",
    "acquisition.ch1_clip_low_count",
    "acquisition.ch1_clip_high_count",
    "acquisition.ch2_clip_low_count",
    "acquisition.ch2_clip_high_count",
    "acquisition.calibration_used",
)
