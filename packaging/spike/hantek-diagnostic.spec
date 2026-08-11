# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parents[1]
SPIKE = ROOT / "packaging" / "spike"

datas = collect_data_files("PyHT6022", includes=["Firmware/HEX/*"])

analysis = Analysis(
    [str(SPIKE / "probe.py")],
    pathex=[str(ROOT), str(ROOT / "src"), str(SPIKE)],
    binaries=[],
    datas=datas,
    hiddenimports=["PyHT6022.LibUsbScope", "usb1"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="hantek-diagnostic",
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
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="hantek-diagnostic",
)
