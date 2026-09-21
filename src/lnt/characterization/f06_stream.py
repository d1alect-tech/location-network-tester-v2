"""F06 streaming trajectory accumulator over shared analytic band chunks."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final, final

import numpy as np
from scipy import signal

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from lnt.characterization.local_transform import TransformChunk

type Float64Array = NDArray[np.float64]
type Int64Array = NDArray[np.int64]
type ComplexArray = NDArray[np.complex128]

GATE_SEGMENT_SAMPLES: Final = 4096
_PAIR_SAMPLES: Final = 2
_TWO_PI: Final = 2.0 * math.pi

__all__ = ["GATE_SEGMENT_SAMPLES", "Trajectory"]


@final
class Trajectory:
    """Однократный потоковый накопитель траектории F06.

    Память ограничена числом хранимых отсчётов: накапливаются только выбранные позиции,
    сумма спектра сегментов и текущий чанк. Хранимые позиции известны заранее
    (объявленное правило ``even_floor_index``), поэтому спан не нужно знать до конца
    прохода.
    """

    __slots__ = (
        "amplitudes",
        "candidates",
        "closed",
        "count",
        "floor_rad",
        "frequencies",
        "max_increment",
        "pending",
        "phases",
        "prev_phi",
        "sample_rate_hz",
        "segments",
        "signal_sum",
        "span_start",
        "span_stop",
        "stored",
    )

    def __init__(
        self, sample_rate_hz: float, stored_limit: int, record_samples: int, floor_rad: float
    ) -> None:
        """Разложить объявленные пределы по преаллоцированным буферам."""
        self.sample_rate_hz = sample_rate_hz
        self.floor_rad = floor_rad
        self.candidates = np.floor(np.arange(stored_limit) * record_samples / stored_limit).astype(
            np.int64
        )
        self.stored = np.zeros(stored_limit, dtype=np.int64)
        self.amplitudes = np.zeros(stored_limit, dtype=np.float64)
        self.phases = np.zeros(stored_limit, dtype=np.float64)
        self.frequencies = np.zeros(stored_limit, dtype=np.float64)
        self.count = 0
        self.signal_sum = np.zeros(GATE_SEGMENT_SAMPLES // 2 + 1, dtype=np.float64)
        self.segments = 0
        self.max_increment = 0.0
        self.span_start: int | None = None
        self.span_stop = 0
        self.prev_phi: float | None = None
        self.pending: tuple[int, float] | None = None
        self.closed = False

    def feed(self, chunk: TransformChunk) -> None:
        """Принять один чанк общего потокового преобразования."""
        values = None if chunk.values is None else np.asarray(chunk.values, dtype=np.complex128)
        if values is None or values.size == 0:
            self.break_span()
            return
        if self.closed:
            return
        if self.span_start is not None and int(chunk.start_sample) != self.span_stop:
            self.break_span()
            return
        raw = np.angle(values)
        phi = np.asarray(np.unwrap(raw), dtype=np.float64)
        if self.prev_phi is not None:
            phi += _TWO_PI * np.round((self.prev_phi - float(phi[0])) / _TWO_PI)
        self._increments(phi)
        if self.span_start is None:
            self.span_start = int(chunk.start_sample)
        self._resolve_pending(float(phi[0]))
        self._segments(values)
        self._store(chunk, values, phi)
        self.prev_phi = float(phi[-1])
        self.span_stop = int(chunk.stop_sample)

    def break_span(self) -> None:
        """Прервать спан: за разрывом непрерывность фазы и частоты не определены."""
        self.flush_pending()
        self.prev_phi = None
        if self.span_start is not None:
            self.closed = True

    def flush_pending(self) -> None:
        """Дозаполнить частоту отложенного отсчёта односторонней разностью."""
        if self.pending is None:
            return
        slot, left = self.pending
        self.frequencies[slot] = (self.phases[slot] - left) * self.sample_rate_hz / _TWO_PI
        self.pending = None

    def _increments(self, phi: Float64Array) -> None:
        """Гейт Ито по РАЗВЁРНУТОЙ фазе.

        Сырой ``numpy.angle`` даёт на каждом завороте ветви скачок почти 2 pi и объявил бы
        алиасинг там, где его нет: замерено 5.906 рад против истинных 0.377 рад.
        """
        if phi.size > 1:
            self.max_increment = max(self.max_increment, float(np.max(np.abs(np.diff(phi)))))
        if self.prev_phi is not None:
            self.max_increment = max(self.max_increment, abs(float(phi[0]) - self.prev_phi))

    def _resolve_pending(self, right: float) -> None:
        """Правый сосед отложенного отсчёта: центральная разность через границу чанка."""
        if self.pending is None:
            return
        slot, left = self.pending
        self.frequencies[slot] = (right - left) * self.sample_rate_hz / (2.0 * _TWO_PI)
        self.pending = None

    def _segments(self, values: ComplexArray) -> None:
        """Спектр сигнала по сегментам фиксированной длины: сетка частот общая."""
        if values.size != GATE_SEGMENT_SAMPLES:
            return
        _, signal_psd = signal.welch(
            values.real, fs=self.sample_rate_hz, nperseg=GATE_SEGMENT_SAMPLES, detrend="constant"
        )
        self.signal_sum += signal_psd
        self.segments += 1

    def _store(self, chunk: TransformChunk, values: ComplexArray, phi: Float64Array) -> None:
        """Разложить хранимые кандидаты чанка по объявленным позициям."""
        if phi.size < _PAIR_SAMPLES:
            return
        start, stop = int(chunk.start_sample), int(chunk.stop_sample)
        low = int(np.searchsorted(self.candidates, start, side="left"))
        high = int(np.searchsorted(self.candidates, stop, side="left"))
        if high <= low:
            return
        chosen = self.candidates[low:high]
        local = chosen - start
        tail = int(local[-1]) == phi.size - 1
        size = int(chosen.size) - int(tail)
        if size > 0:
            slots = slice(self.count, self.count + size)
            self.stored[slots] = chosen[:size]
            self.amplitudes[slots] = np.abs(values[local[:size]])
            self.phases[slots] = phi[local[:size]]
            self.frequencies[slots] = self._central_rates(local[:size], phi)
            self.count += size
        if tail:
            slot = self.count
            self.stored[slot] = int(chosen[-1])
            self.amplitudes[slot] = float(np.abs(values[local[-1]]))
            self.phases[slot] = float(phi[local[-1]])
            self.count += 1
            self.pending = (slot, float(phi[local[-1] - 1]))

    def _central_rates(self, local: Int64Array, phi: Float64Array) -> Float64Array:
        """Центральная разность на мелкой сетке; край спана — односторонняя.

        Левый сосед берётся из предыдущего чанка, поэтому граница чанка не портит
        оценку: разность остаётся точной всюду, кроме первого отсчёта спана.
        """
        left = phi[np.maximum(local - 1, 0)].astype(np.float64, copy=True)
        if self.prev_phi is None and int(local[0]) == 0:
            left[0] = 2.0 * float(phi[0]) - float(phi[1])
        elif self.prev_phi is not None:
            left = np.where(local >= 1, left, self.prev_phi)
        right = phi[np.minimum(local + 1, phi.size - 1)]
        return (right - left) * self.sample_rate_hz / (2.0 * _TWO_PI)
