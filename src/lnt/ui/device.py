"""Безопасная диагностика Hantek 6022BE для панели управления."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from lnt.errors import DeviceNotFoundError
from lnt.scope_io import ScopeProtocol, open_real_scope

_INSTALL_HINTS: Final[tuple[str, ...]] = (
    "Установка: pip install 'lnt[hantek]' + libusb-1.0.dll рядом с python.exe (см. README).",
)
_OPEN_HINTS: Final[tuple[str, ...]] = (
    "Zadig: подключить Hantek, выбрать его через Options → List All Devices и установить WinUSB.",
    "До прошивки устройство видно с VID 04B4, после — с VID 04B5.",
    "Если устройство «пропало» после первого запуска, повторить WinUSB для нового VID.",
)
_FIRMWARE_HINTS: Final[tuple[str, ...]] = (
    "Прошивка RAM-resident: lnt capture зальёт её автоматически при захвате.",
)
_GENERIC_HINTS: Final[tuple[str, ...]] = (
    "Проверьте USB-подключение, WinUSB и libusb-1.0.dll (см. README).",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceStatus:
    """Состояние драйвера, устройства и RAM-прошивки осциллографа."""

    driver_installed: bool
    device_opened: bool
    firmware_present: bool
    error_message: str | None
    hints: tuple[str, ...]


def diagnose_device(
    scope_factory: Callable[[], ScopeProtocol] = open_real_scope,
) -> DeviceStatus:
    """Проверяет доступность устройства без настройки, прошивки или захвата."""
    try:
        scope = scope_factory()
    except DeviceNotFoundError as exc:
        return DeviceStatus(
            driver_installed=False,
            device_opened=False,
            firmware_present=False,
            error_message=str(exc),
            hints=_INSTALL_HINTS,
        )
    except Exception as exc:  # noqa: BLE001 - граница UI не выпускает ошибки драйвера
        return DeviceStatus(
            driver_installed=True,
            device_opened=False,
            firmware_present=False,
            error_message=str(exc),
            hints=_GENERIC_HINTS,
        )

    handle_opened = False
    try:
        scope.setup()
        handle_opened = scope.open_handle()
        if handle_opened:
            firmware_present = scope.is_device_firmware_present
            status = DeviceStatus(
                driver_installed=True,
                device_opened=True,
                firmware_present=firmware_present,
                error_message=None,
                hints=() if firmware_present else _FIRMWARE_HINTS,
            )
        else:
            status = DeviceStatus(
                driver_installed=True,
                device_opened=False,
                firmware_present=False,
                error_message="Hantek 6022BE не найден",
                hints=_OPEN_HINTS,
            )
    except Exception as exc:  # noqa: BLE001 - граница UI не выпускает ошибки драйвера
        status = DeviceStatus(
            driver_installed=True,
            device_opened=False,
            firmware_present=False,
            error_message=str(exc),
            hints=_GENERIC_HINTS,
        )
    finally:
        if handle_opened:
            try:
                scope.close_handle()
            except Exception as exc:  # noqa: BLE001 - ошибка закрытия также диагностируется
                status = DeviceStatus(
                    driver_installed=True,
                    device_opened=False,
                    firmware_present=False,
                    error_message=str(exc),
                    hints=_GENERIC_HINTS,
                )
    return status
