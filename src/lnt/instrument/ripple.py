"""Кольцо полных отсчётов CH1 и rolling-метрики живого риппла.

Тап вызывается из ``InstrumentService`` ДО ``FrameStream.push``: кольцо видит
каждый преобразованный блок, а не выбранные триггером кадры. Кольцо ограничено
(``RIPPLE_BUFFER_SAMPLES``); метрики считаются только по непрерывному участку
после окна установления и последнего host-разрыва. Сырые рельсы АЦП хранятся
рядом с вольтами: клиппинг не удаляет отсчёты, а делает публичный участок
недоступным (``unavailable, never fabricated``).
"""

from __future__ import annotations

import itertools
import threading
from typing import Final, final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from lnt.errors import InputError
from lnt.instrument.ripple_snapshot import RippleState, build_snapshot, rail_codes
from lnt.instrument.ripple_types import (
    MIN_METRIC_SAMPLES,
    RIPPLE_BUFFER_SAMPLES,
    RippleConfig,
    RippleSnapshot,
)
from lnt.instrument.sa import (
    _SampleRing,  # pyright: ignore[reportPrivateUsage] — механика кольца SA, не математика
)

Float32Array = NDArray[np.float32]
_EPOCH_COUNTER: Final = itertools.count(1)


@final
class RippleEngine:
    """Одно кольцо на захват: приём блоков, непрерывность, settle-гейт, снимок."""

    def __init__(
        self,
        *,
        config: RippleConfig,
        capacity_samples: int = RIPPLE_BUFFER_SAMPLES,
    ) -> None:
        """Готовит пустое кольцо; прибор не трогает и метрик не фабрикует."""
        if capacity_samples < max(MIN_METRIC_SAMPLES, config.min_metric_samples):
            raise InputError(f"риппл: capacity_samples {capacity_samples} меньше минимума")
        self._lock: Final = threading.RLock()
        self._config = config
        self._capacity = capacity_samples
        self._samples: Final = _SampleRing(capacity_samples)
        self._rails: Final = _SampleRing(capacity_samples)
        self._epoch_id = 0
        self._continuity_id = 0
        self._capture_samples = 0
        self._observed_total = 0
        self._span_start_abs = 0
        self._last_sequence: int | None = None
        self._last_sample_end = 0
        self._block_count = 0
        self._gap_count = 0
        self._dropped_blocks = 0
        self._dropped_samples = 0
        self._span_from_gap = False
        self._stopped = False
        self._cache: RippleSnapshot | None = None

    @property
    def capacity_samples(self) -> int:
        """Ёмкость кольца в отсчётах CH1."""
        return self._capacity

    @property
    def config(self) -> RippleConfig:
        """Действующая конфигурация кольца."""
        return self._config

    def restart(self) -> None:
        """Новый захват: новая эпоха процесса, новая непрерывность, пустое кольцо."""
        with self._lock:
            self._epoch_id = next(_EPOCH_COUNTER)
            self._continuity_id += 1
            self._stopped = False
            self._reset_capture()

    def configure(self, config: RippleConfig) -> None:
        """Меняет конфигурацию; смена геометрии открывает новую эпоху измерения."""
        with self._lock:
            if config.config_id == self._config.config_id:
                return
            self._config = config
            self._epoch_id = next(_EPOCH_COUNTER)
            self._continuity_id += 1
            self._reset_capture()

    def absorb_block(
        self,
        samples: ArrayLike,
        *,
        raw: object,
        sequence: int,
        sample_start: int,
    ) -> None:
        """Принимает блок до FrameStream: вольты + сырые рельсы + прогресс."""
        values = np.asarray(samples, dtype=np.float32)
        if values.ndim != 1:
            raise InputError("риппл: блок должен быть 1-D")
        count = int(values.size)
        if count == 0:
            return
        if not np.isfinite(values).all():
            raise InputError("риппл: блок содержит нечисловые вольты")
        rails = rail_codes(raw)
        if rails.size != count:
            raise InputError("риппл: рельсы и вольты блока разной длины")
        with self._lock:
            self._accept_sequence(
                sequence=sequence,
                sample_start=sample_start,
            )
            self._samples.push(values)
            self._rails.push(rails)
            self._observed_total += count
            self._capture_samples = sample_start + count
            self._last_sequence = sequence
            self._last_sample_end = sample_start + count
            self._block_count += 1
            self._cache = None

    def stop(self) -> None:
        """Захват остановлен: снимок переходит в ``stopped`` без чисел."""
        with self._lock:
            self._stopped = True
            self._cache = None

    def snapshot(self) -> RippleSnapshot:
        """Согласованный снимок; метрики кэшируются до следующего блока."""
        with self._lock:
            if self._cache is None:
                self._cache = self._build_snapshot()
            return self._cache

    def _accept_sequence(self, *, sequence: int, sample_start: int) -> None:
        if sequence < 0 or sample_start < 0:
            raise InputError("риппл: sequence/sample_start не могут быть отрицательными")
        if self._last_sequence is None:
            if sequence != 0 or sample_start != 0:
                self._record_gap(
                    missing_blocks=sequence,
                    missing_samples=sample_start,
                    sample_start=sample_start,
                )
            return
        if sample_start < self._last_sample_end:
            raise InputError("риппл: блок пришёл с неположительным прогрессом отсчётов")
        if sequence != self._last_sequence + 1 or sample_start != self._last_sample_end:
            missing_blocks = max(sequence - self._last_sequence - 1, 0)
            missing_samples = max(sample_start - self._last_sample_end, 0)
            if missing_blocks == 0 and missing_samples == 0:
                raise InputError("риппл: скачок последовательности без прогресса")
            self._record_gap(
                missing_blocks=missing_blocks,
                missing_samples=missing_samples,
                sample_start=sample_start,
            )

    def _record_gap(self, *, missing_blocks: int, missing_samples: int, sample_start: int) -> None:
        self._gap_count += 1
        self._dropped_blocks += missing_blocks
        self._dropped_samples += missing_samples
        self._continuity_id += 1
        self._samples.clear()
        self._rails.clear()
        self._span_start_abs = sample_start
        self._span_from_gap = True
        self._cache = None

    def _reset_capture(self) -> None:
        self._samples.clear()
        self._rails.clear()
        self._capture_samples = 0
        self._observed_total = 0
        self._span_start_abs = 0
        self._last_sequence = None
        self._last_sample_end = 0
        self._block_count = 0
        self._gap_count = 0
        self._dropped_blocks = 0
        self._dropped_samples = 0
        self._span_from_gap = False
        self._cache = None

    def _build_snapshot(self) -> RippleSnapshot:
        return build_snapshot(
            RippleState(
                config=self._config,
                capacity_samples=self._capacity,
                samples=self._samples.snapshot(),
                rails=self._rails.snapshot(),
                epoch_id=self._epoch_id,
                continuity_id=self._continuity_id,
                capture_samples=self._capture_samples,
                observed_total=self._observed_total,
                span_start_abs=self._span_start_abs,
                block_count=self._block_count,
                gap_count=self._gap_count,
                dropped_blocks=self._dropped_blocks,
                dropped_samples=self._dropped_samples,
                span_from_gap=self._span_from_gap,
                stopped=self._stopped,
            ),
        )
