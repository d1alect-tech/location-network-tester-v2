"""Раскладка потока отсчётов на окна кадра: курсор, фронт, развёртка AUTO.

Курсор — индекс первого ещё не выданного отсчёта; он же начало окна кадра.
Приоритет у фронта (окно начинается НА фронте, предтриггера нет), поэтому
отсчёты между курсором и фронтом в кадры не попадают — как на DSO. Когда
фронтов нет, а владельцу нужен кадр, ``sweep`` разрешает развёртку AUTO по
таймауту (решение принимает сервис по своим часам).
"""

from typing import Final

from lnt.instrument.frames import (
    DEFAULT_FRAME_SAMPLES,
    DEFAULT_MAX_BUFFERED_BLOCKS,
    UNSTABLE_LEAD_SAMPLES,
    Float32Array,
    FrameAssembler,
    LiveFrame,
)
from lnt.instrument.trigger import TriggerConfig, TriggerMode, find_edge


class FrameStream:
    """Курсор потока: приём блоков, раскладка на окна, счётчики кадров и потерь."""

    def __init__(
        self,
        *,
        sample_rate_hz: float,
        frame_samples: int = DEFAULT_FRAME_SAMPLES,
        max_buffered_blocks: int = DEFAULT_MAX_BUFFERED_BLOCKS,
        discard_lead_samples: int = UNSTABLE_LEAD_SAMPLES,
    ) -> None:
        """Строит буфер геометрии кадра; курсор встаёт за отсчёт шва."""
        self._buffer: Final = FrameAssembler(
            frame_samples=frame_samples,
            max_buffered_blocks=max_buffered_blocks,
            discard_lead_samples=discard_lead_samples,
        )
        self._sample_rate_hz: Final = sample_rate_hz
        self._cursor: int = 1
        self._frame_index: int = 0
        self._dropped: int = 0

    @property
    def frame_samples(self) -> int:
        """Длина окна кадра в отсчётах на канал."""
        return self._buffer.frame_samples

    def reset(self) -> None:
        """Свежий старт: буфер пуст, прогрев взведён, счётчики кадров обнулены."""
        self._buffer.reset()
        self._cursor = 1
        self._frame_index = 0
        self._dropped = 0

    def push(self, ch1: Float32Array, ch2: Float32Array) -> None:
        """Принимает блок вольт-отсчётов; потери переполнения уезжают в кадр."""
        dropped = self._buffer.push(ch1, ch2)
        self._dropped += dropped
        self._cursor = max(1, self._cursor - dropped)

    def emit(self, trigger: TriggerConfig, *, now_s: float, sweep: bool) -> list[LiveFrame]:
        """Разбирает буфер: фронты, затем (при ``sweep``) развёртка AUTO по курсору."""
        frames: list[LiveFrame] = []
        single = trigger.mode is TriggerMode.SINGLE
        while True:
            edge = find_edge(
                self._buffer.channel(trigger.source),
                level_v=trigger.level_v,
                slope=trigger.slope,
                start=self._cursor,
            )
            if edge is not None:
                if self._leftover(edge) < self.frame_samples:
                    break  # окно не достроено: кадр останется триггерным
                frames.append(self._take(edge, self.frame_samples, now_s, triggered=True))
                if single:
                    break  # SINGLE: один триггерный кадр, прибор отпускает владелец
            elif sweep and self._leftover(self._cursor) >= self.frame_samples:
                frames.append(self._take(self._cursor, self.frame_samples, now_s, triggered=False))
            else:
                break
        return frames

    def flush(self, *, now_s: float) -> LiveFrame | None:
        """Финальный кадр остановки: остаток буфера либо ``None``, если остатка нет."""
        leftover = self._leftover(self._cursor)
        if leftover <= 0:
            return None
        return self._take(self._cursor, min(leftover, self.frame_samples), now_s, triggered=False)

    def _leftover(self, start: int) -> int:
        return self._buffer.available - start

    def _take(self, start: int, count: int, now_s: float, *, triggered: bool) -> LiveFrame:
        ch1, ch2 = self._buffer.take(start, count)
        frame = LiveFrame(
            ch1=ch1,
            ch2=ch2,
            sample_rate_hz=self._sample_rate_hz,
            frame_index=self._frame_index,
            triggered=triggered,
            emitted_at_s=now_s,
            dropped_samples=self._dropped,
        )
        self._frame_index += 1
        self._dropped = 0
        # Сжатие с сохранением одного отсчёта шва: он нужен, чтобы фронт ровно
        # на границе следующего кадра не потерялся.
        self._buffer.compact(start + count - 1)
        self._cursor = 1
        return frame
