# -*- mode: python ; coding: utf-8 -*-
"""Спецификация PyInstaller для частной one-folder сборки LNT (Todo 47).

Решения зафиксированы спайком Todo 13 (packaging/spike, вердикт `go`):
one-folder COLLECT, без UPX, без one-file, без копирования системных DLL.
Точка входа — GUI-лаунчер ``lnt.launcher`` (Todo 46): блокировка экземпляра,
pre-bind 127.0.0.1:8765 с детерминированным фолбэком, health/build-id,
второй запуск фокусирует существующий, авария в windowed-режиме пишет код
поддержки без traceback. Иконки в репозитории нет — ``icon`` не задаётся
осознанно; version-ресурс собирается из версии pyproject.toml.

Состав сверх рантайма Python и залоченных зависимостей:
- данные NumPy/SciPy и их DLL (собираются анализом импортов + хуки);
- прошивки Hantek (PyHT6022/Firmware/HEX) и libusb-1.0.dll из пакета usb1;
- вендоренные ассеты UI v1+v2 с шрифтами IBM Plex (обслуживаются из
  ``lnt/ui/static``, см. ``_STATIC`` в lnt/ui/app.py); dev-метаданные Vite
  (каталог ``.vite``) в комплект не входят — рантаймом не читаются;
- лицензии/уведомления: LICENSES/, THIRD_PARTY_NOTICES.md,
  dependency-manifest.json, политика частного использования;
- dist-info залоченных пакетов, читаемых через importlib.metadata
  (lnt/numpy/scipy/fastapi/uvicorn), чтобы CodeIdentity работал в frozen-режиме.

Запрещено осознанно: UPX, one-file, Zadig, системные DLL, Node/dev/test/Plotly.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    copy_metadata,
)
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).resolve().parents[0]
SRC = ROOT / "src"
PROJECT_VERSION = tomllib.loads(
    (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
)["project"]["version"]

# --- Данные: вендоренные ассеты UI (обслуживаются из пакета lnt.ui.static). ---
static_root = SRC / "lnt" / "ui" / "static"
static_dest = Path("lnt") / "ui" / "static"
datas = [
    (str(path), str(static_dest / path.relative_to(static_root).parent))
    for path in sorted(static_root.rglob("*"))
    if path.is_file() and ".vite" not in path.parts
]

# --- Данные: прошивки Hantek (7 файлов HEX) и libusb из usb1. ---
datas += collect_data_files("PyHT6022", includes=["Firmware/HEX/*"])
datas += collect_dynamic_libs("usb1")

# --- Метаданные пакетов для importlib.metadata в frozen-режиме. ---
for package_name in ("lnt", "numpy", "scipy", "fastapi", "uvicorn"):
    datas += copy_metadata(package_name)

# --- Лицензии, уведомления и политика частного использования. ---
for license_path in sorted((ROOT / "LICENSES").iterdir()):
    if license_path.is_file():
        datas.append((str(license_path), "licenses"))
datas += [
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "dependency-manifest.json"), "."),
    (str(ROOT / "docs" / "distribution-policy.md"), "."),
    (str(ROOT / "packaging" / "PRIVATE-USE.txt"), "."),
]


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    """Первые три числовых компонента версии + 0 для Windows FILEVERSION."""
    parts = [int(part) for part in version.split(".")[:3] if part.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2], 0


_file_version = _version_tuple(PROJECT_VERSION)


def _version_info(original_name: str, description: str) -> VSVersionInfo:
    """Version-ресурс для одного из двух exe одной сборки."""
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_file_version,
            prodvers=_file_version,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "LNT owner-internal build"),
                            StringStruct("FileDescription", description),
                            StringStruct("FileVersion", PROJECT_VERSION),
                            StringStruct("InternalName", original_name.removesuffix(".exe")),
                            StringStruct("OriginalFilename", original_name),
                            StringStruct("ProductName", "LNT"),
                            StringStruct("ProductVersion", PROJECT_VERSION),
                            StringStruct("PrivateBuild", "owner-internal; no conveyance"),
                        ],
                    ),
                ],
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


version_resource = _version_info(
    "LNT.exe",
    "LNT local measurement panel",
)
# Todo 48 smoke: windowed LNT.exe не имеет консольных потоков, поэтому CLI-
# самопроверка и archive-вербы неотслеживаемы (stdout/exit-диагностика). Консольный
# сиблинг разделяет тот же _internal и тот же скрипт запуска; GUI-поведение
# LNT.exe не меняется.
version_resource_cli = _version_info(
    "LNT-cli.exe",
    "LNT command-line interface (console)"
)

analysis = Analysis(
    [str(SRC / "lnt" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Hantek/libusb: динамические импорты драйвера (см. спайк Todo 13).
        "PyHT6022.LibUsbScope",
        "usb1",
        # Uvicorn выбирает реализации по строке "auto"/конфигу во время работы.
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        # anyio подгружает бэкенд по строковой конфигурации.
        "anyio._backends._asyncio",
        # Starlette/FastAPI импортируют multipart лениво и под двумя именами.
        "multipart",
        "python_multipart",
        # Todo 48 smoke нашёл ленивые импорты, которые не собираются статическим
        # анализом и ломали запуск замороженного приложения (ImportError на первом
        # же расширении scipy): чистый stdlib heapq, Cython-модуль scipy и два
        # ленивых submodule array_api_compat (импортируются через importlib).
    "heapq",
    "scipy._cyutility",
    "scipy._external.array_api_compat.numpy.fft",
    "scipy._external.array_api_compat.common._fft",
    # uvicorn разрешает Config/Server через модульный __getattr__ и применяет
    # собственный dictConfig с форматтерами uvicorn.logging - статический
    # анализ их не видит (Todo 48: "Unable to configure formatter 'default'").
    "uvicorn.config",
    "uvicorn.logging",
    "uvicorn.server",
    ],
    hookspath=[],
    hooksconfig={},
    excludes=[
        "tkinter",
        # Dev/сборочный инструментарий и недостижимые из lnt.launcher модули
        # (проверено: import lnt.launcher не тянет ни один из них; в src/lnt нет
        # ни одного импорта matplotlib/PIL/pygments). Статический анализ тянет
        # их по опциональным путям зависимостей — в frozen-сборке им не место.
        "setuptools",
        "pkg_resources",
        "matplotlib",
        "PIL",
        "pygments",
        "contourpy",
        "kiwisolver",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="LNT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_resource,
)

# Консольный сиблинг: тот же pyz/scripts, общий _internal (см. COLLECT ниже).
# Даёт наблюдаемые stdout/exit-коды для selftest/archive в smoke Todo 48.
exe_cli = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="LNT-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_resource_cli,
)

coll = COLLECT(
    exe,
    exe_cli,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LNT",
)
