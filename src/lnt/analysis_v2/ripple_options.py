"""Валидированные входы ripple-среза: полоса, окно, объявление установления.

Коррекция контракта 2026-10-20: захват не чувствует подключение; квалификация
окна установления существует только через явное операторское объявление.
``--probe`` (и ``probe_multiplier`` адаптера) — это проверка равенства против
масштаба записи, а не пересчёт вольтов.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from typing import TYPE_CHECKING, Final

from lnt.errors import InputError
from lnt.psd.models import DEFAULT_MAX_CHUNK_SAMPLES, FrequencyBand, PsdSettings

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.ripple.adapter import AdapterSpec
    from lnt.session_store import LoadedSession

#: Диагностический дефолт: сегмент = round(fs / 1 Гц), без молчаливого укорачивания.
NPERSEG_POLICY_HZ: Final = 1.0
WINDOW_HANN: Final = "hann"
OVERLAP_FRACTION: Final = 0.5
DETECTOR_MEAN: Final = "mean"
DEFAULT_INTERVAL_WINDOW_S: Final = 1.0
MIN_NPERSEG: Final = 2


class SettlingDeclaration(StrEnum):
    """Явное операторское объявление состояния подключения в эпоху записи."""

    PRECONNECTED = "preconnected_no_reconnection"
    UNKNOWN = "settling_unknown"


class BaselineAttachment(StrEnum):
    """Объявленное условие подключения фона (короткое замыкание на возврат)."""

    SAME_ADAPTER_TIP_SHORTED = "same_adapter_tip_shorted_to_return"


@dataclass(frozen=True, slots=True, kw_only=True)
class RippleRequest:
    """Один запрос ripple-среза: сессия, адаптер, полоса и объявления оператора."""

    session: LoadedSession
    adapter: AdapterSpec
    band_low_hz: float
    band_high_hz: float
    settling: SettlingDeclaration
    window_s: float = DEFAULT_INTERVAL_WINDOW_S
    baseline_path: Path | None = None
    baseline_attachment: BaselineAttachment | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RippleOptions:
    """Проверенные опции оценки: явный Welch и интервалы по окну."""

    welch: PsdSettings
    nperseg: int
    interval_window_s: float


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputError(f"ripple: {name} должно быть числом")
    number = float(value)
    if not math.isfinite(number):
        raise InputError(f"ripple: {name} должно быть конечным")
    return number


def validated_options(request: RippleRequest) -> RippleOptions:
    """Проверяет полосу, окно, согласованность пробника; строит явный Welch."""
    manifest = request.session.manifest
    sample_rate_hz = _finite(manifest.sample_rate_hz, "sample_rate_hz")
    if sample_rate_hz <= 0.0:
        raise InputError("ripple: sample_rate_hz должен быть > 0")
    band_low_hz, band_high_hz = _validate_band(
        low_hz=request.band_low_hz,
        high_hz=request.band_high_hz,
        sample_rate_hz=sample_rate_hz,
    )
    _validate_probe_assertion(request)
    nperseg = _nperseg_for(sample_rate_hz)
    band = FrequencyBand(
        name="ripple",
        low_hz=band_low_hz,
        high_hz=band_high_hz,
    )
    welch = PsdSettings(
        sample_rate_hz=sample_rate_hz,
        nperseg=nperseg,
        max_chunk_samples=max(DEFAULT_MAX_CHUNK_SAMPLES, nperseg),
        bands=(band,),
        window=WINDOW_HANN,
        overlap_fraction=OVERLAP_FRACTION,
        detector=DETECTOR_MEAN,
    )
    return RippleOptions(welch=welch, nperseg=nperseg, interval_window_s=_window_s(request))


def _validate_band(
    *, low_hz: object, high_hz: object, sample_rate_hz: float
) -> tuple[float, float]:
    low = _finite(low_hz, "band_low_hz")
    high = _finite(high_hz, "band_high_hz")
    # DC-бин не входит в публичную полосу: нижняя граница может быть 0, но
    # маска полосы всегда пересекается с f > 0 (см. ripple_blocks._band).
    if low < 0.0:
        raise InputError("ripple: band_low_hz должен быть >= 0 (DC-бин исключён)")
    if high <= low:
        raise InputError("ripple: band_high_hz должен быть > band_low_hz")
    if high > sample_rate_hz / 2.0:
        raise InputError(f"ripple: band_high_hz должен быть <= fs/2 = {sample_rate_hz / 2.0:g} Гц")
    nperseg = _nperseg_for(sample_rate_hz)
    resolution = sample_rate_hz / nperseg
    first_center = max(math.ceil(low / resolution), 1) * resolution
    if first_center > high:
        raise InputError(f"ripple: нет положительного центра бина в полосе (шаг {resolution:g} Гц)")
    return low, high


def _validate_probe_assertion(request: RippleRequest) -> None:
    manifest_probe = request.session.manifest.ch1.probe_multiplier
    adapter_probe = request.adapter.probe_multiplier
    if manifest_probe != adapter_probe:
        message = "".join(
            (
                "ripple: probe_metadata_mismatch: манифест=",
                str(manifest_probe),
                ", адаптер=",
                str(adapter_probe),
                "; ",
            )
        )
        raise InputError(message + "требуется корректно записанная сессия, а не пересчёт вольтов")


def _nperseg_for(sample_rate_hz: float) -> int:
    nperseg = round(sample_rate_hz / NPERSEG_POLICY_HZ)
    if nperseg < MIN_NPERSEG:
        message = "ripple: sample_rate_hz слишком мала для nperseg=round(fs/1 Гц); "
        raise InputError(message + "разрешение не укорачивается молча")
    return nperseg


def _window_s(request: RippleRequest) -> float:
    window_s = _finite(request.window_s, "window_s")
    if window_s <= 0.0:
        raise InputError("ripple: window_s должен быть > 0")
    return window_s
