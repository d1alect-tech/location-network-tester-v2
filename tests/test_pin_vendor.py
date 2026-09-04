"""Золотые вендорные пины сверяются с диском (очередь A4)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

_ROOT = Path(__file__).resolve().parent.parent


def _load_pin_vendor() -> ModuleType:
    path = _ROOT / "scripts" / "pin_vendor.py"
    spec = importlib.util.spec_from_file_location("pin_vendor", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pin_vendor"] = module
    spec.loader.exec_module(module)
    return module


def test_vendor_pins_match_disk() -> None:
    verdict = _load_pin_vendor().verify(_ROOT)
    assert verdict["ok"], verdict["errors"]


def test_pin_vendor_main_exits_zero() -> None:
    assert _load_pin_vendor().main(["--root", str(_ROOT)]) == 0


def test_pin_vendor_rejects_empty_root(tmp_path: Path) -> None:
    module = _load_pin_vendor()
    verdict = module.verify(tmp_path)
    assert not verdict["ok"]
    assert module.main(["--root", str(tmp_path)]) == 2
