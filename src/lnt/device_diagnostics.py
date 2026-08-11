"""Типизированные состояния готовности измерительного устройства."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol


class DeviceState(StrEnum):
    """Стабильные состояния цепочки backend → USB → firmware."""

    BACKEND_UNAVAILABLE = "backend_unavailable"
    DRIVER_MISSING = "driver_missing"
    DEVICE_ABSENT = "device_absent"
    BOOTLOADER_VID = "bootloader_vid"
    RUNNING_VID = "running_vid"
    HANDLE_BUSY = "handle_busy"
    FIRMWARE_MISSING = "firmware_missing"
    FIRMWARE_UPLOAD_FAILED = "firmware_upload_failed"
    READY = "ready"


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceProbeSnapshot:
    """Немутабельный результат внедряемых низкоуровневых проб."""

    backend_available: bool
    driver_available: bool = False
    detected_vid: str | None = None
    handle_opened: bool = False
    handle_busy: bool = False
    firmware_present: bool = False
    firmware_upload_failed: bool = False
    detail: str | None = None


class DeviceProbe(Protocol):
    """Неинвазивный источник фактов о цепочке устройства."""

    def probe(self) -> DeviceProbeSnapshot:
        """Возвращает факты без прошивки, настройки или захвата."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceDiagnostic:
    """Состояние устройства с русским объяснением и действием оператора."""

    state: DeviceState
    description_ru: str
    recovery_action_ru: str
    detected_vid: str | None
    detail: str | None = None


_TEXT: Final[dict[DeviceState, tuple[str, str]]] = {
    DeviceState.BACKEND_UNAVAILABLE: (
        "Backend Hantek/libusb недоступен.",
        "Установите extra lnt[hantek] и положите совместимую libusb-1.0.dll рядом с Python.",
    ),
    DeviceState.DRIVER_MISSING: (
        "USB-устройство видно, но WinUSB для его VID не установлен.",
        "Установите WinUSB через Zadig отдельно для обнаруженного VID и повторите проверку.",
    ),
    DeviceState.DEVICE_ABSENT: (
        "Hantek DSO-6022BE не обнаружен на USB.",
        "Подключите устройство и проверьте кабель/порт; переустановка backend не требуется.",
    ),
    DeviceState.BOOTLOADER_VID: (
        "Обнаружен загрузочный VID 04B4; рабочая RAM-прошивка ещё не активна.",
        "Проверьте WinUSB для VID 04B4; прошивку загружайте только явной операцией захвата.",
    ),
    DeviceState.RUNNING_VID: (
        "Обнаружен рабочий VID 04B5, но готовность handle не подтверждена.",
        "Закройте другие программы с осциллографом и повторите проверку.",
    ),
    DeviceState.HANDLE_BUSY: (
        "USB-handle осциллографа занят другим процессом.",
        "Закройте программу, удерживающую Hantek, и повторите проверку.",
    ),
    DeviceState.FIRMWARE_MISSING: (
        "Устройство открыто, но RAM-прошивка отсутствует.",
        "Запустите захват явно: диагностика не загружает прошивку автоматически.",
    ),
    DeviceState.FIRMWARE_UPLOAD_FAILED: (
        "Предыдущая явная загрузка RAM-прошивки завершилась ошибкой.",
        "Переподключите устройство, проверьте firmware-файлы и повторите явную операцию.",
    ),
    DeviceState.READY: (
        "Устройство, WinUSB и RAM-прошивка готовы.",
        "Дополнительные действия не требуются.",
    ),
}


def diagnose_device_state(probe: DeviceProbe) -> DeviceDiagnostic:
    """Детерминированно выводит одно состояние из внедряемых фактов."""
    snapshot = probe.probe()
    if not snapshot.backend_available:
        state = DeviceState.BACKEND_UNAVAILABLE
    elif not snapshot.driver_available:
        state = DeviceState.DRIVER_MISSING
    elif snapshot.firmware_upload_failed:
        state = DeviceState.FIRMWARE_UPLOAD_FAILED
    elif snapshot.detected_vid is None:
        state = DeviceState.DEVICE_ABSENT
    elif snapshot.handle_busy:
        state = DeviceState.HANDLE_BUSY
    elif snapshot.detected_vid.upper() == "04B4":
        state = DeviceState.BOOTLOADER_VID
    elif snapshot.handle_opened and snapshot.firmware_present:
        state = DeviceState.READY
    elif snapshot.handle_opened:
        state = DeviceState.FIRMWARE_MISSING
    else:
        state = DeviceState.RUNNING_VID
    description, recovery = _TEXT[state]
    return DeviceDiagnostic(
        state=state,
        description_ru=description,
        recovery_action_ru=recovery,
        detected_vid=snapshot.detected_vid,
        detail=snapshot.detail,
    )
