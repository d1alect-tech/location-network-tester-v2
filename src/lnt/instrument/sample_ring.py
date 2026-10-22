"""Кольцо последних отсчётов CH1: общая механика живого SA и риппла.

Публичный модуль вместо приватного класса из ``sa``: оба контура кормят кольцо
преобразованными вольтами и читают непрерывный участок. Запись — по кругу,
переполнение выбывает старейшими; границы ёмкости проверяет владелец.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Float32Array = NDArray[np.float32]


class SampleRing:
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
