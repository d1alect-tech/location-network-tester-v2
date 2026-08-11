"""Inventory recursive PE dependency closure for the PowerShell policy gate."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

import pefile


def _imports(path: Path) -> list[str]:
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        return sorted(
            entry.dll.decode("ascii", errors="replace")
            for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", ())
        )
    except pefile.PEFormatError:
        return []


def _system_module(name: str, system32: Path) -> Path | None:
    direct = system32 / name
    if direct.is_file():
        return direct.resolve()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    kernel32.LoadLibraryExW.restype = wintypes.HMODULE
    kernel32.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel32.GetModuleFileNameW.restype = wintypes.DWORD
    kernel32.FreeLibrary.argtypes = [wintypes.HMODULE]
    kernel32.FreeLibrary.restype = wintypes.BOOL
    handle = kernel32.LoadLibraryExW(name, None, 0x00000800)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        if not kernel32.GetModuleFileNameW(handle, buffer, len(buffer)):
            return None
        resolved = Path(buffer.value).resolve()
        return resolved if resolved.parent == system32 else None
    finally:
        kernel32.FreeLibrary(handle)


def main() -> int:
    """Write the recursive PE import inventory and report unresolved imports."""
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    system32 = (Path(os.environ["SYSTEMROOT"]) / "System32").resolve()
    binaries = sorted(
        path for path in bundle.rglob("*") if path.suffix.lower() in {".exe", ".dll", ".pyd"}
    )
    by_name: dict[str, list[Path]] = {}
    for path in binaries:
        by_name.setdefault(path.name.lower(), []).append(path)
    records = []
    unresolved = set()
    for binary in binaries:
        for dependency in _imports(binary):
            local = by_name.get(dependency.lower(), [])
            system = _system_module(dependency, system32)
            if local:
                resolved = local[0]
                location = "bundle"
            elif system is not None:
                resolved = system
                location = "system32"
            else:
                unresolved.add(dependency)
                resolved = Path(dependency)
                location = "unresolved"
            records.append(
                {
                    "source": str(binary.relative_to(bundle)),
                    "dependency": dependency,
                    "location": location,
                    "resolved_path": str(resolved),
                }
            )
    payload = {
        "bundle": str(bundle),
        "binary_count": len(binaries),
        "imports": records,
        "unresolved": sorted(unresolved),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0 if not unresolved else 2


if __name__ == "__main__":
    raise SystemExit(main())
