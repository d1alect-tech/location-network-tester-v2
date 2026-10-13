"""Живой SA: конфигурация, кольцо потока и пересчёт спектра на свип.

Спектроанализатор живой вкладки не считает Welch сам: на каждый опубликованный
свип он вызывает v1-движок ``lnt.spectrum.compute_band_spectrum`` поверх кольца
последних отсчётов CH1 (математика не дублируется — граница очереди C4).
Кольцо питается кадрами живого потока из подписки гейта: буфер всегда свеж, а
число доложенных отсчётов не зависит от числа открытых SSE-стримов. Пики
находятся в полосе ДО прореживания: прореживание серии — display-only
(``ui/decimation``), трассы SA — по одной на свип.

Конфигурация проверяется дважды: селекторы (RBW/окно/детектор) и геометрия
полосы — при строительстве ``SaConfig``; полоса против Найквиста потока — при
применении к работающему захвату (``configure``), чтобы отказ ушёл в 422 ДО
того, как неверная полоса дойдёт до SSE-контура. Пересчёт ждёт готовности
тихо: пока кольцо короче минимального окна или полоса уже текущего разрешения,
трассы нет — данные не фабрикуются.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.psd.models import DEFAULT_DETECTOR, KNOWN_DETECTORS
from lnt.psd.windows import DEFAULT_RBW_HZ, DEFAULT_WINDOW, canonical_window_name, validate_rbw_hz
from lnt.spectrum import (
    MIN_BAND_BINS,
    MIN_NPERSEG,
    NYQUIST_FRACTION,
    BandSpectrum,
    _choose_nperseg,  # pyright: ignore[reportPrivateUsage] — v1-движок не правим (граница C4), правило переиспользуем
    compute_band_spectrum,
)

if TYPE_CHECKING:
    from lnt.instrument.frames import LiveFrame

Float32Array = NDArray[np.float32]

# Кольцо SA: 2^19 отсчётов (2 МиБ float32) вмещает nperseg самого тонкого RBW
# (10 Гц) на максимальной dual-частоте 8 МГц; заполнение — 65 мс живого потока.
SA_BUFFER_SAMPLES: Final = 2**19


@dataclass(frozen=True, slots=True, kw_only=True)
class SaConfig:
    """Конфигурация живого SA: селекторы v1-тракта и полоса анализа."""

    rbw_hz: float = DEFAULT_RBW_HZ
    window: str = DEFAULT_WINDOW
    band_low_hz: float = 0.0
    band_high_hz: float
    detector: str = DEFAULT_DETECTOR

    def __post_init__(self) -> None:
        """Проверяет селекторы и геометрию полосы; Найквист — в ``SaEngine.configure``."""
        validate_rbw_hz(self.rbw_hz)
        canonical_window_name(self.window)
        if self.detector not in KNOWN_DETECTORS:
            raise InputError(f"SA: неизвестный детектор {self.detector!r}")
        edges = (("band_low_hz", self.band_low_hz), ("band_high_hz", self.band_high_hz))
        for name, edge_hz in edges:
            if not math.isfinite(edge_hz) or edge_hz < 0.0:
                raise InputError(f"SA: {name} {edge_hz!r} должна быть конечной и неотрицательной")
        if self.band_high_hz <= self.band_low_hz:
            raise InputError(f"SA: полоса {self.band_low_hz:.0f}..{self.band_high_hz:.0f} Гц пуста")


@dataclass(frozen=True, slots=True, kw_only=True)
class SaTrace:
    """Трасс SA одного свипа: спектр полосы и конфигурация, по которой он считан."""

    spectrum: BandSpectrum
    config: SaConfig


class _SampleRing:
    """Кольцо последних отсчётов CH1: запись по кругу, срез — по порядку."""

    def __init__(self, capacity: int) -> None:
        """Выделяет буфер ровно ``capacity`` отсчётов; границы проверяет владелец."""
        self._data: Float32Array = np.empty(capacity, dtype=np.float32)
        self._start: int = 0
        self._size: int = 0

    def clear(self) -> None:
        """Обнуляет кольцо без перевыделения буфера."""
        self._start = 0
        self._size = 0

    def push(self, samples: Float32Array) -> None:
        """Дописывает отсчёты; переполнение выбывает старейшими (по кругу)."""
        capacity = int(self._data.size)
        count = int(samples.size)
        if count == 0:
            return
        if count >= capacity:
            self._data[:] = samples[count - capacity :]
            self._start = 0
            self._size = capacity
            return
        tail = (self._start + self._size) % capacity
        first = min(count, capacity - tail)
        self._data[tail : tail + first] = samples[:first]
        second = count - first
        if second > 0:
            self._data[:second] = samples[first:]
        overflow = self._size + count - capacity
        if overflow > 0:
            self._start = (self._start + overflow) % capacity
            self._size = capacity
        else:
            self._size += count

    def snapshot(self) -> Float32Array:
        """Копия кольца по порядку «старейшие → новейшие»."""
        capacity = int(self._data.size)
        if self._size == 0:
            return np.empty(0, dtype=np.float32)
        if self._start + self._size <= capacity:
            return self._data[self._start : self._start + self._size].copy()
        head = self._data[self._start :]
        tail_count = self._start + self._size - capacity
        return np.concatenate((head, self._data[:tail_count]))


class SaEngine:
    """Живой SA-контур: конфигурация, кольцо CH1 и пересчёт на свип.

    Кадры кладёт подписка гейта (``offer``) из потока владельца — по одному
    разу на свип; пересчёт (``sweep_spectrum``) вызывает тот, кто публикует
    свип (SSE-контур панели), поэтому тяжёлый Welch не гоняется чаще
    display-темпа. Блокировка — вокруг конфигурации и кольца: сам расчёт идёт
    вне замка.
    """

    def __init__(self, *, capacity_samples: int = SA_BUFFER_SAMPLES) -> None:
        """Готовит пустое кольцо и выключенный контур; прибор не трогает."""
        if capacity_samples < MIN_NPERSEG:
            raise InputError(
                f"SA: кольцо {capacity_samples} отсчётов меньше минимального окна {MIN_NPERSEG}"
            )
        self._lock: Final = threading.RLock()
        self._ring: Final = _SampleRing(capacity_samples)
        self._config: SaConfig | None = None
        self._sample_rate_hz: float = 0.0

    @property
    def config(self) -> SaConfig | None:
        """Действующая конфигурация SA: ``None`` — контур выключен."""
        with self._lock:
            return self._config

    def reset(self) -> None:
        """Свежий захват: контур выключен, кольцо пусто (как триггер — заново)."""
        with self._lock:
            self._config = None
            self._sample_rate_hz = 0.0
            self._ring.clear()

    def configure(self, config: SaConfig | None, *, sample_rate_hz: float) -> None:
        """Применяет конфигурацию к потоку частоты ``sample_rate_hz``.

        ``None`` выключает контур. Полоса проверяется против Найквиста здесь —
        typed ``InputError`` уходит в 422 до SSE-контура, а не роняет стрим
        посреди пересчёта.
        """
        with self._lock:
            if config is None:
                self._config = None
                return
            nyquist_hz = sample_rate_hz / 2.0
            if config.band_high_hz > nyquist_hz:
                raise InputError(
                    f"SA: полоса {config.band_high_hz:.0f} Гц выше Найквиста {nyquist_hz:.0f} Гц"
                )
            effective_high_hz = min(config.band_high_hz, NYQUIST_FRACTION * sample_rate_hz)
            if config.band_low_hz >= effective_high_hz:
                raise InputError(
                    f"SA: пустая полоса {config.band_low_hz:.0f}..{effective_high_hz:.0f} Гц"
                )
            self._config = config
            self._sample_rate_hz = sample_rate_hz

    def offer(self, frame: LiveFrame) -> None:
        """Кладёт кадр потока в кольцо CH1: каждый свип ровно один раз."""
        with self._lock:
            self._ring.push(frame.ch1)

    def sweep_spectrum(self) -> SaTrace | None:
        """Пересчитывает спектр над кольцом; ``None`` — контур не готов (не ошибка).

        Готовность зеркалит условия ``compute_band_spectrum`` на той же сетке —
        ``InputError`` движка сюда не доходит и SSE-контур не роняется.
        """
        with self._lock:
            config = self._config
            sample_rate_hz = self._sample_rate_hz
            samples = self._ring.snapshot()
        if config is None or samples.size < MIN_NPERSEG:
            return None
        nperseg = _choose_nperseg(int(samples.size), sample_rate_hz, config.rbw_hz)
        if self._band_too_narrow(config, sample_rate_hz, nperseg):
            return None
        spectrum = compute_band_spectrum(
            samples,
            sample_rate_hz=sample_rate_hz,
            band_low_hz=config.band_low_hz,
            band_high_hz=config.band_high_hz,
            rbw_hz=config.rbw_hz,
            window=config.window,
            detector=config.detector,
        )
        return SaTrace(spectrum=spectrum, config=config)

    def _band_too_narrow(
        self,
        config: SaConfig,
        sample_rate_hz: float,
        nperseg: int,
    ) -> bool:
        """Проверяет полосу на 8+ бинов текущего разрешения (маска движка)."""
        frequency_hz = np.fft.rfftfreq(nperseg, d=1.0 / sample_rate_hz)
        effective_high_hz = min(config.band_high_hz, NYQUIST_FRACTION * sample_rate_hz)
        mask = (frequency_hz >= config.band_low_hz) & (frequency_hz <= effective_high_hz)
        return int(mask.sum()) < MIN_BAND_BINS
