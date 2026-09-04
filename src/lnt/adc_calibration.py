"""Документированная поправка АЦП из per-device таблиц config dir (очередь C3).

Без таблицы тракт бит-идентичен legacy-масштабу (``calibration_used=False``).
Честное правило: некалиброванное напряжение никогда не выдаётся за
калиброванное; отсутствие таблицы — ``unavailable, never fabricated``.
Таблицы живут в config dir (рядом с ``config.json``), НЕ в манифесте сессии.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError

if TYPE_CHECKING:
    from pathlib import Path

Float32Array = NDArray[np.float32]
ADC_CENTER = 128.0
VOLTS_SCALE = 5.12


@dataclass(frozen=True, slots=True, kw_only=True)
class AdcCalibration:
    """Линейная поправка АЦП: (raw − center − offset) × scale × gain."""

    offset_lsb: float = 0.0
    gain: float = 1.0
    device_serial: str | None = None
    basis: str = "operator_measured"

    def __post_init__(self) -> None:
        """Отклоняет нефизичную поправку на границе домена."""
        if not math.isfinite(self.offset_lsb) or not math.isfinite(self.gain):
            raise InputError("adc_calibration: offset_lsb и gain должны быть конечными")
        if self.gain <= 0.0:
            raise InputError("adc_calibration: gain должен быть положительным")

    @property
    def is_effective(self) -> bool:
        """Флаг provenance: поправка реально меняет отсчёты."""
        return self.offset_lsb != 0.0 or self.gain != 1.0


def table_path_for_device(config_dir: Path, device_serial: str | None) -> Path:
    """Путь per-device таблицы; без серийника — общая ``adc_calibration.json``."""
    serial = (device_serial or "").strip().lower()
    name = f"adc_calibration_{serial}.json" if serial else "adc_calibration.json"
    return config_dir / name


def load_adc_calibration(path: Path) -> AdcCalibration:
    """Читает таблицу; битый файл — ``InputError``, отсутствие — проверяйте сами."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputError(f"adc_calibration: не читается {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise InputError(f"adc_calibration: корень {path} должен быть объектом")
    offset = payload.get("offset_lsb", 0.0)
    gain = payload.get("gain", 1.0)
    serial = payload.get("device_serial")
    if not isinstance(offset, (int, float)) or not isinstance(gain, (int, float)):
        raise InputError(f"adc_calibration: offset_lsb/gain в {path} должны быть числами")
    if serial is not None and not isinstance(serial, str):
        raise InputError(f"adc_calibration: device_serial в {path} должен быть строкой")
    return AdcCalibration(offset_lsb=float(offset), gain=float(gain), device_serial=serial)


def try_load_adc_calibration(config_dir: Path, device_serial: str | None) -> AdcCalibration | None:
    """Возвращает таблицу или ``None`` (некалиброванный путь, без фабрикации)."""
    path = table_path_for_device(config_dir, device_serial)
    if not path.is_file():
        return None
    return load_adc_calibration(path)


def apply_adc_calibration(
    raw: NDArray[np.uint8],
    *,
    range_code: int,
    probe_multiplier: float = 1.0,
    calibration: AdcCalibration | None = None,
) -> Float32Array:
    """Масштабирует raw в вольты; ``None`` — legacy-формула бит-в-бит."""
    offset = calibration.offset_lsb if calibration is not None else 0.0
    gain = calibration.gain if calibration is not None else 1.0
    scale = VOLTS_SCALE * probe_multiplier / float(range_code << 7)
    return ((raw.astype(np.float32) - ADC_CENTER - offset) * (scale * gain)).astype(np.float32)
