"""Безопасная диагностика Hantek 6022BE для панели управления."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from lnt.device_diagnostics import (
    DeviceDiagnostic,
    DeviceProbeSnapshot,
    DeviceState,
    diagnose_device_state,
)
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
    state: DeviceState
    description_ru: str
    recovery_action_ru: str


@dataclass(frozen=True, slots=True)
class _SnapshotProbe:
    snapshot: DeviceProbeSnapshot

    def probe(self) -> DeviceProbeSnapshot:
        return self.snapshot


def _legacy_status(diagnostic: DeviceDiagnostic) -> DeviceStatus:
    driver_installed = diagnostic.state not in {
        DeviceState.BACKEND_UNAVAILABLE,
        DeviceState.DRIVER_MISSING,
    }
    device_opened = diagnostic.state in {DeviceState.FIRMWARE_MISSING, DeviceState.READY}
    firmware_present = diagnostic.state is DeviceState.READY
    return DeviceStatus(
        driver_installed=driver_installed,
        device_opened=device_opened,
        firmware_present=firmware_present,
        error_message=None if firmware_present else diagnostic.detail or diagnostic.description_ru,
        hints=() if firmware_present else (diagnostic.recovery_action_ru,),
        state=diagnostic.state,
        description_ru=diagnostic.description_ru,
        recovery_action_ru=diagnostic.recovery_action_ru,
    )


def diagnose_device(
    scope_factory: Callable[[], ScopeProtocol] = open_real_scope,
) -> DeviceStatus:
    """Проверяет доступность устройства без настройки, прошивки или захвата."""
    try:
        scope = scope_factory()
    except DeviceNotFoundError as exc:
        snapshot = DeviceProbeSnapshot(
            backend_available=False,
            detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - граница UI не выпускает ошибки драйвера
        snapshot = DeviceProbeSnapshot(
            backend_available=True,
            driver_available=False,
            detail=str(exc),
        )
    else:
        handle_opened = False
        try:
            scope.setup()
            handle_opened = bool(scope.open_handle())
            snapshot = DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B5" if handle_opened else None,
                handle_opened=handle_opened,
                firmware_present=handle_opened and scope.is_device_firmware_present,
            )
        except Exception as exc:  # noqa: BLE001 - граница UI не выпускает ошибки драйвера
            detail = str(exc)
            snapshot = DeviceProbeSnapshot(
                backend_available=True,
                driver_available=True,
                detected_vid="04B5",
                handle_busy="busy" in detail.casefold() or "access" in detail.casefold(),
                detail=detail,
            )
        finally:
            if handle_opened:
                try:
                    scope.close_handle()
                except Exception as exc:  # noqa: BLE001 - ошибка закрытия также диагностируется
                    snapshot = DeviceProbeSnapshot(
                        backend_available=True,
                        driver_available=True,
                        detected_vid="04B5",
                        handle_busy=True,
                        detail=str(exc),
                    )
    return _legacy_status(diagnose_device_state(_SnapshotProbe(snapshot)))
