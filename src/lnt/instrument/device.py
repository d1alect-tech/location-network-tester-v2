"""Настройка тракта прибора для живого режима и масштаб блока raw -> вольты.

Последовательность настройки повторяет ``scope_io._configure_scope``: имя там
приватное и без ``__all__``, поэтому импорт не проходит basedpyright
(``reportPrivateUsage``), а модуль ``scope_io`` эта очередь не правит. Отличие
живой вкладки (директива владельца 2026-10-19): гейн-код CH2 следует за
кодом CH1 — экран развёртки делит одну ось Y между каналами, одно В/дел
на пару. Job-захват (``scope_io``, трансформаторная опора 230:6 на CH2)
остаётся на зафиксированных ±5 В и это расхождение — намеренное.
"""

import math
from typing import Final, cast

import numpy as np

from lnt.adc_calibration import AdcCalibration, apply_adc_calibration
from lnt.errors import DeviceNotFoundError, InputError
from lnt.instrument.frames import Float32Array
from lnt.scope_io import CHANNEL_COUNT, MAX_POLL_TIMEOUT_MS, ScopeProtocol

# Окно ``poll`` драйвера: 1..250 мс (``scope_io`` проверяет те же границы).
MIN_POLL_TIMEOUT_MS: Final = 1
BULK_INTERFACE: Final = 0


def configure_scope(scope: ScopeProtocol, *, rate_code: int, ch1_range_code: int) -> None:
    """Открывает ручку и настраивает тракт; неудача — ``DeviceNotFoundError``."""
    scope.setup()
    if not scope.open_handle():
        raise DeviceNotFoundError("Hantek 6022BE не найден (open_handle не удался)")
    if not scope.is_device_firmware_present:
        scope.flash_firmware()
    scope.set_interface(BULK_INTERFACE)
    scope.set_num_channels(CHANNEL_COUNT)
    scope.set_sample_rate(rate_code)
    scope.set_ch1_voltage_range(ch1_range_code)
    scope.set_ch2_voltage_range(ch1_range_code)


def validated_poll_timeout_ms(poll_timeout_ms: int) -> int:
    """Проверяет окно опроса драйвера на границе входа."""
    if not MIN_POLL_TIMEOUT_MS <= poll_timeout_ms <= MAX_POLL_TIMEOUT_MS:
        window = f"{MIN_POLL_TIMEOUT_MS}..{MAX_POLL_TIMEOUT_MS} мс"
        raise InputError(f"poll_timeout_ms {poll_timeout_ms} вне окна драйвера {window}")
    return poll_timeout_ms


def validated_probe_multiplier(probe_multiplier: float) -> float:
    """Проверяет множитель пробника: конечный и положительный."""
    if not math.isfinite(probe_multiplier) or probe_multiplier <= 0.0:
        raise InputError(f"ch1_probe_multiplier {probe_multiplier} должен быть конечным и > 0")
    return probe_multiplier


def block_to_volts(
    raw: object,
    *,
    range_code: int,
    probe_multiplier: float = 1.0,
    calibration: AdcCalibration | None = None,
) -> Float32Array:
    """Масштабирует raw-блок uint8 в вольты документированной формулой АЦП."""
    counts = np.frombuffer(bytes(cast("bytearray", raw)), dtype=np.uint8)
    return apply_adc_calibration(
        counts,
        range_code=range_code,
        probe_multiplier=probe_multiplier,
        calibration=calibration,
    )
