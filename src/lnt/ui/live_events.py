"""SSE-события живого потока: кадр, heartbeat, трасса SA и display-темп.

События собираются здесь, а маршруты (``routes_live``) только крутят контур.
``Pacer`` держит display-темп: кадры не чаще ``min_interval_s`` (блок прибора
даёт несколько окон сразу), пропуски уезжают в ``skipped_frames`` ближайшего
кадра, heartbeat — свой интервал (подписчик отличает «нет данных» от «поток
умер»). Трасса SA публикуется сразу ЗА кадром того же свипа: пересчёт — на
каждый ОПУБЛИКОВАННЫЙ свип, пропущенные темпом кадры питают кольцо, но трасс
не рождают (см. ``instrument/sa``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from fastapi.sse import ServerSentEvent

from lnt.ui.models_live import (
    MAX_SPECTRUM_POINTS,
    frame_payload,
    spectrum_payload,
    state_payload,
)

if TYPE_CHECKING:
    from lnt.instrument.frames import LiveFrame
    from lnt.instrument.live_gate import LiveCaptureGate
    from lnt.instrument.sa import SaEngine

# Heartbeat без кадров: подписчик отличает «нет данных» от «поток умер».
HEARTBEAT_INTERVAL_S: Final = 15.0
RETRY_MS: Final = 1000


@dataclass(slots=True)
class Pacer:
    """Display-темп потока: кадры не чаще ``min_interval_s``, heartbeat — свой.

    Часы — монотонные часы панели, не часы прибора: темп защищает браузер от
    лавины кадров (блок прибора даёт несколько окон сразу), а пропуски уезжают
    в ``skipped_frames`` ближайшего кадра.
    """

    gate: LiveCaptureGate
    min_interval_s: float
    last_event_s: float = field(default_factory=time.monotonic)
    skipped: int = 0

    def paced_frame(
        self,
        frame: LiveFrame,
        *,
        max_points: int,
        calibration_used: bool,
    ) -> ServerSentEvent | None:
        """Кадр в темпе панели; вне темпа — ``None`` и счётчик пропуска."""
        now_s = time.monotonic()
        if now_s - self.last_event_s < self.min_interval_s:
            self.skipped += 1
            return None
        return self._taken(
            frame_event(
                frame,
                max_points=max_points,
                calibration_used=calibration_used,
                skipped_frames=self.take_skipped(),
            ),
            now_s,
        )

    def heartbeat_due(self) -> ServerSentEvent | None:
        """Heartbeat, если событий не было дольше ``HEARTBEAT_INTERVAL_S``."""
        now_s = time.monotonic()
        if now_s - self.last_event_s < HEARTBEAT_INTERVAL_S:
            return None
        return self._taken(heartbeat_event(self.gate), now_s)

    def take_skipped(self) -> int:
        """Счётчик display-пропусков с обнулением: пропуски не замалчиваются."""
        skipped, self.skipped = self.skipped, 0
        return skipped

    def _taken(self, event: ServerSentEvent, now_s: float) -> ServerSentEvent:
        self.last_event_s = now_s
        self.skipped = 0
        return event


def frame_event(
    frame: LiveFrame,
    *,
    max_points: int,
    calibration_used: bool,
    skipped_frames: int,
) -> ServerSentEvent:
    """Событие ``frame``: кадр целиком, id — индекс кадра, retry — как у задач."""
    return ServerSentEvent(
        event="frame",
        id=str(frame.frame_index),
        retry=RETRY_MS,
        data=frame_payload(
            frame,
            max_points=max_points,
            calibration_used=calibration_used,
            skipped_frames=skipped_frames,
        ),
    )


def heartbeat_event(gate: LiveCaptureGate) -> ServerSentEvent:
    """Событие ``heartbeat``: текущий статус владения, а не пустой кадр."""
    return ServerSentEvent(
        event="heartbeat",
        retry=RETRY_MS,
        data=state_payload(gate.service, mode=gate.mode),
    )


def spectrum_event(engine: SaEngine, frame: LiveFrame) -> ServerSentEvent | None:
    """Событие ``spectrum``: одна трасса SA свипа ``frame``; ``None`` — не готова.

    id — тот же индекс свипа, что и у события ``frame``. Серия прорежена до
    бюджета панели, пики — из полного разрешения (до прореживания).
    """
    trace = engine.sweep_spectrum()
    if trace is None:
        return None
    return ServerSentEvent(
        event="spectrum",
        id=str(frame.frame_index),
        retry=RETRY_MS,
        data=spectrum_payload(
            trace.spectrum,
            config=trace.config,
            frame_index=frame.frame_index,
            max_points=MAX_SPECTRUM_POINTS,
        ),
    )
