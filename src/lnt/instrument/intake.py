"""Приём сырых блоков живого прибора: pending-очередь, вольты и тап риппла.

Один экземпляр на захват. Прогресс/последовательность штампуются в колбэке
драйвера ДО вытеснения старейших блоков из ограниченной очереди, поэтому потеря
блока становится host-разрывом, а не тихой склейкой. Кольцо риппла получает
преобразованный блок ДО ``FrameStream.push`` и не зависит от триггерных кадров.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast, final

import numpy as np

from lnt.errors import InputError
from lnt.instrument.device import block_to_volts
from lnt.instrument.ripple import RippleEngine
from lnt.instrument.ripple_types import RippleConfig

if TYPE_CHECKING:
    from lnt.adc_calibration import AdcCalibration
    from lnt.instrument.stream import FrameStream

_PendingBlock = tuple[int, int, object, object]


@final
class InstrumentIntake:
    """Очередь блоков прибора и единый тракт «raw -> вольты -> кольцо -> кадр»."""

    def __init__(  # noqa: PLR0913 - приборный тракт: каждая ручка kw-only
        self,
        *,
        stream: FrameStream,
        range_code: int,
        probe_multiplier: float,
        calibration: AdcCalibration | None,
        sample_rate_hz: float,
        ch1_range_v: float,
        continuity_basis: str,
        discard_lead_samples: int,
        max_buffered_blocks: int,
    ) -> None:
        """Собирает пустую очередь и пустое кольцо; прибор не трогает."""
        self._stream: Final = stream
        self._range_code: Final = range_code
        self._probe_multiplier: Final = probe_multiplier
        self._calibration: Final = calibration
        self._pending: list[_PendingBlock] = []
        self._pending_cap: Final = 2 * max_buffered_blocks
        self._sequence = 0
        self._sample_progress = 0
        self.dropped_blocks = 0
        self._ripple = RippleEngine(
            config=RippleConfig.for_live(
                sample_rate_hz=sample_rate_hz,
                ch1_range_v=ch1_range_v,
                probe_multiplier=probe_multiplier,
                calibration_used=calibration is not None,
                continuity_basis=continuity_basis,
                startup_discard_samples=discard_lead_samples,
            ),
        )

    @property
    def ripple(self) -> RippleEngine:
        """Кольцо полного тракта этого захвата."""
        return self._ripple

    def restart(self) -> None:
        """Свежий захват: очередь пуста, прогресс с нуля, новая эпоха кольца."""
        self._pending.clear()
        self._sequence = 0
        self._sample_progress = 0
        self.dropped_blocks = 0
        self._ripple.restart()

    def stop(self) -> None:
        """Захват остановлен: кольцо фиксирует ``stopped`` без новых чисел."""
        self._ripple.stop()

    def on_block(self, ch1_raw: object, ch2_raw: object) -> None:
        """Колбэк ``read_async``: штамп прогресса ДО вытеснения старейших."""
        sequence = self._sequence
        sample_start = self._sample_progress
        self._sequence += 1
        self._sample_progress += _raw_count(ch1_raw)
        self._pending.append((sequence, sample_start, ch1_raw, ch2_raw))
        overflow = max(len(self._pending) - self._pending_cap, 0)
        del self._pending[:overflow]
        self.dropped_blocks += overflow

    def absorb(self) -> None:
        """Преобразует очередь в вольты, кормит кольцо и только затем поток."""
        pending, self._pending = self._pending, []
        for sequence, sample_start, ch1_raw, ch2_raw in pending:
            ch1 = block_to_volts(
                ch1_raw,
                range_code=self._range_code,
                probe_multiplier=self._probe_multiplier,
                calibration=self._calibration,
            )
            # Общая ось экрана: вольты CH2 масштабируются тем же кодом, что и
            # CH1 (настройка тракта — device.configure_scope), пробника на CH2 нет.
            ch2 = block_to_volts(
                ch2_raw,
                range_code=self._range_code,
                calibration=self._calibration,
            )
            self._ripple.absorb_block(
                ch1,
                raw=ch1_raw,
                sequence=sequence,
                sample_start=sample_start,
            )
            self._stream.push(ch1, ch2)


def _raw_count(raw: object) -> int:
    """Число отсчётов блока без лишнего копирования bytes-подобного входа."""
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return len(raw)
    try:
        counts = np.frombuffer(bytes(cast("bytearray", raw)), dtype=np.uint8)
    except TypeError as exc:
        raise InputError("живой поток: блок прибора должен быть bytes-подобным") from exc
    return int(counts.size)
