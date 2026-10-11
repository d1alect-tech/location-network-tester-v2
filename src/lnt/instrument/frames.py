"""Кадр живого потока и ограниченный буфер отсчётов для окон кадра.

Блок прибора — 65 536 отсчётов (2 × 32 768 на канал, ``scope_io``): кадр меньше
блока и собирается из нескольких блоков. Окно кадра начинается на фронте, а для
поиска фронта нужен предыдущий отсчёт, поэтому после выдачи кадра в буфере
остаётся один отсчёт шва.

Первые отсчёты свежего старта нестабильны: OpenHantek ``docs/limitations.md``
фиксирует «the first few samples are dropped due to unstable/unusual reading»,
а пример вендорного драйвера (Hantek6022API ``examples/capture_6022.py``)
пропускает первый нестабильный блок целиком — прогрев по умолчанию равен блоку.
Буфер ограничен: при переполнении выбывают самые старые отсчёты, а счётчик
потерь уезжает в ближайший кадр (потери не замалчиваются).
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from lnt.errors import InputError
from lnt.instrument.trigger import TriggerSource
from lnt.scope_io import BLOCK_SAMPLES_PER_CHANNEL

Float32Array = NDArray[np.float32]

UNSTABLE_LEAD_SAMPLES: Final = BLOCK_SAMPLES_PER_CHANNEL
DEFAULT_FRAME_SAMPLES: Final = 4096
DEFAULT_MAX_BUFFERED_BLOCKS: Final = 4
MIN_FRAME_SAMPLES: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class LiveFrame:
    """Один кадр живого потока: вольты обоих каналов и метаданные выдачи."""

    ch1: Float32Array
    ch2: Float32Array
    sample_rate_hz: float
    frame_index: int
    triggered: bool
    emitted_at_s: float
    dropped_samples: int = 0


class FrameAssembler:
    """Ограниченный буфер вольт-отсчётов: прогрев, приём блоков, окна кадра."""

    def __init__(
        self,
        *,
        frame_samples: int,
        max_buffered_blocks: int,
        discard_lead_samples: int,
    ) -> None:
        """Проверяет геометрию кадра и буфера, начинает с пустых каналов."""
        if not MIN_FRAME_SAMPLES <= frame_samples <= BLOCK_SAMPLES_PER_CHANNEL:
            bounds = f"{MIN_FRAME_SAMPLES}..{BLOCK_SAMPLES_PER_CHANNEL}"
            raise InputError(f"frame_samples {frame_samples} вне окна кадра {bounds}")
        if max_buffered_blocks < 1:
            raise InputError(f"max_buffered_blocks {max_buffered_blocks} должен быть >= 1")
        if discard_lead_samples < 0:
            raise InputError(f"discard_lead_samples {discard_lead_samples} должен быть >= 0")
        self._frame_samples: Final = frame_samples
        self._capacity: Final = max_buffered_blocks * BLOCK_SAMPLES_PER_CHANNEL
        self._lead_total: Final = discard_lead_samples
        self._lead_left: int = discard_lead_samples
        self._ch1: Float32Array = np.empty(0, dtype=np.float32)
        self._ch2: Float32Array = np.empty(0, dtype=np.float32)

    @property
    def frame_samples(self) -> int:
        """Длина окна кадра в отсчётах на канал."""
        return self._frame_samples

    @property
    def available(self) -> int:
        """Число отсчётов в буфере (на канал)."""
        return int(self._ch1.size)

    def reset(self) -> None:
        """Обнуляет буфер и снова взводит отбрасывание прогрева (свежий старт)."""
        self._lead_left = self._lead_total
        self._ch1 = np.empty(0, dtype=np.float32)
        self._ch2 = np.empty(0, dtype=np.float32)

    def push(self, ch1: Float32Array, ch2: Float32Array) -> int:
        """Добавляет блок; возвращает число отсчётов, выбывших при переполнении."""
        if self._lead_left > 0:
            skipped = min(self._lead_left, int(ch1.size))
            ch1 = ch1[skipped:]
            ch2 = ch2[skipped:]
            self._lead_left -= skipped
        if ch1.size == 0:
            return 0
        self._ch1 = np.concatenate((self._ch1, ch1))
        self._ch2 = np.concatenate((self._ch2, ch2))
        overflow = int(self._ch1.size) - self._capacity
        if overflow <= 0:
            return 0
        self._ch1 = self._ch1[overflow:]
        self._ch2 = self._ch2[overflow:]
        return overflow

    def take(self, start: int, count: int) -> tuple[Float32Array, Float32Array]:
        """Копирует окно ``[start, start + count)`` обоих каналов (обрезка по хвосту)."""
        stop = min(start + count, int(self._ch1.size))
        return (self._ch1[start:stop].copy(), self._ch2[start:stop].copy())

    def compact(self, keep_from: int) -> None:
        """Отбрасывает первые ``keep_from`` отсчётов — сжатие буфера после кадра."""
        drop = max(0, min(keep_from, int(self._ch1.size)))
        self._ch1 = self._ch1[drop:]
        self._ch2 = self._ch2[drop:]

    def channel(self, source: TriggerSource) -> Float32Array:
        """Отсчёты канала-источника триггера (без копии)."""
        return self._ch1 if source is TriggerSource.CH1 else self._ch2
