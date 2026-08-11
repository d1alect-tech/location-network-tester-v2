"""Production providers для безопасного metadata collector LNT."""

import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

from lnt.ui.device import diagnose_device


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildInfo:
    """Версия и режим сборки LNT."""

    version: str
    build: str
    frozen: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatformDiagnostic:
    """Разрешённая неперсональная информация платформы."""

    os_version: str
    architecture: str
    timezone: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceDiagnostic:
    """Разрешённые идентификаторы и состояние драйвера устройства."""

    vid: str | None
    pid: str | None
    model: str | None
    firmware: str | None
    driver: str | None
    reason_code: str | None

    @classmethod
    def offline(cls, reason_code: str) -> "DeviceDiagnostic":
        """Создаёт полностью reason-coded результат недоступного устройства."""
        return cls(
            vid=None,
            pid=None,
            model=None,
            firmware=None,
            driver=None,
            reason_code=reason_code,
        )


@dataclass(frozen=True, slots=True)
class SystemPlatformProbe:
    """Системный адаптер без hostname, пользователя и network identity."""

    def diagnose(self) -> PlatformDiagnostic:
        """Возвращает только версию ОС, архитектуру и часовой пояс."""
        offset = datetime.now().astimezone().utcoffset()
        timezone = "UTC" if offset is None else f"UTC{offset.total_seconds() / 3600:+g}"
        return PlatformDiagnostic(
            os_version=platform.platform(aliased=True, terse=True),
            architecture=platform.machine(),
            timezone=timezone,
        )


@dataclass(frozen=True, slots=True)
class HantekDeviceProbe:
    """Адаптер существующей безопасной диагностики Hantek."""

    def diagnose(self) -> DeviceDiagnostic:
        """Преобразует UI-диагностику в reason-coded metadata."""
        status = diagnose_device()
        if not status.device_opened:
            reason = "driver_unavailable" if not status.driver_installed else "device_offline"
            return DeviceDiagnostic.offline(reason)
        firmware = "present" if status.firmware_present else None
        reason = None if status.firmware_present else "firmware_unavailable"
        return DeviceDiagnostic(
            vid="04B5",
            pid="6022",
            model="Hantek 6022BE",
            firmware=firmware,
            driver="libusb",
            reason_code=reason,
        )


def production_build_info() -> BuildInfo:
    """Определяет версию пакета и frozen/dev режим без персональных данных."""
    try:
        package_version = version("lnt")
    except PackageNotFoundError:
        package_version = "unknown"
    frozen = bool(getattr(sys, "frozen", False))
    return BuildInfo(version=package_version, build=package_version, frozen=frozen)
