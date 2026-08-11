"""Frozen Hantek diagnostic spike; never captures or changes firmware/drivers."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
from ctypes import wintypes
from dataclasses import asdict
from pathlib import Path
from typing import Final

import PyHT6022
import usb1

from lnt.ui.device import diagnose_device
from packaging.spike.fake_adapter import FakeState, fake_factory

FIRMWARE_NAMES: Final = (
    "dds120-firmware.hex",
    "dso6021-firmware.hex",
    "dso6022be-firmware.hex",
    "dso6022bl-firmware.hex",
    "mod_fw_01.ihex",
    "mod_fw_iso.ihex",
    "stock_fw.ihex",
)
X64_PE_MACHINE: Final = 0x8664


def _loaded_libusb() -> dict[str, str | bool]:
    with usb1.USBContext() as context:
        list(context.getDeviceIterator(skip_on_error=True))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleFileNameW.argtypes = [
            wintypes.HMODULE,
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        kernel32.GetModuleFileNameW.restype = wintypes.DWORD
        handle = kernel32.GetModuleHandleW("libusb-1.0.dll")
        if not handle:
            raise RuntimeError("libusb-1.0.dll не загружена")
        buffer = ctypes.create_unicode_buffer(32768)
        if not kernel32.GetModuleFileNameW(handle, buffer, len(buffer)):
            raise RuntimeError("путь загруженной libusb-1.0.dll недоступен")
    path = Path(buffer.value).resolve()
    data = path.read_bytes()
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "x64": int.from_bytes(data[pe_offset + 4 : pe_offset + 6], "little") == X64_PE_MACHINE,
    }


def _firmware() -> list[dict[str, str | bool]]:
    root = Path(PyHT6022.__file__).resolve().parent / "Firmware" / "HEX"
    return [
        {
            "name": name,
            "path": str(root / name),
            "present": (root / name).is_file(),
            "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()
            if (root / name).is_file()
            else "",
        }
        for name in FIRMWARE_NAMES
    ]


def _fake_results() -> dict[str, dict[str, bool | str | None]]:
    return {state.value: asdict(diagnose_device(fake_factory(state))) for state in FakeState}


def main() -> int:
    """Write a machine-readable non-invasive diagnostic report."""
    output = Path(os.environ.get("LNT_SPIKE_OUTPUT", "probe-report.json"))
    try:
        firmware = _firmware()
        report = {
            "frozen": bool(getattr(sys, "frozen", False)),
            "executable": str(Path(sys.executable).resolve()),
            "bundle_root": str(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))),
            "libusb": _loaded_libusb(),
            "firmware": firmware,
            "fakes": _fake_results(),
            "real_device": asdict(diagnose_device()),
            "safety": "diagnose_device only; no capture, firmware upload, or driver mutation",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.stdout.write(json.dumps(report, ensure_ascii=True) + "\n")
        return 0 if report["frozen"] and all(item["present"] for item in firmware) else 2
    except (ImportError, OSError, RuntimeError) as exc:
        sys.stderr.write(f"ОШИБКА ЗАВИСИМОСТИ: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
