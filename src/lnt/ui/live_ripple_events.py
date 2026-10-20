"""SSE-событие ``ripple``: отдельный именованный поток полных метрик.

Темп обновления — свой, независимый от кадров триггера: переход статуса уходит
немедленно (settling/unavailable/ready/stopped), обновление чисел — не чаще
``RIPPLE_INTERVAL_S``. Клиент подписывается на то же соединение, но не владеет
захватом: кольцо живёт в сервисе и переживает переподключение.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from fastapi.sse import ServerSentEvent

from lnt.instrument.ripple_types import RippleStatus
from lnt.ui.live_events import RETRY_MS
from lnt.ui.models_ripple_live import ripple_payload

if TYPE_CHECKING:
    from lnt.instrument.ripple import RippleEngine
    from lnt.instrument.ripple_types import RippleSnapshot

RIPPLE_INTERVAL_S: Final = 0.25


@dataclass(slots=True)
class RippleEmitter:
    """Темп события ``ripple``: статус — сразу, числа — по интервалу."""

    interval_s: float = RIPPLE_INTERVAL_S
    last_status: RippleStatus | None = None
    last_emit_s: float = field(default_factory=time.monotonic)

    def event_if_due(
        self,
        engine: RippleEngine,
        *,
        force: bool = False,
    ) -> ServerSentEvent | None:
        """Событие, если интервал истёк, это первый снимок или ``force``.

        Снимок кольца (метрики по полному участку) считается только тогда,
        когда событие действительно уходит: темп SSE не должен превращаться
        в пересчёт на каждый блок прибора на высокой частоте.
        """
        now_s = time.monotonic()
        if not (force or self.last_status is None or now_s - self.last_emit_s >= self.interval_s):
            return None
        snapshot = engine.snapshot()
        duplicate_stopped = (
            snapshot.status is RippleStatus.STOPPED and self.last_status is RippleStatus.STOPPED
        )
        if force and duplicate_stopped:
            return None
        self.last_status = snapshot.status
        self.last_emit_s = now_s
        return ripple_event(snapshot)


def ripple_event(snapshot: RippleSnapshot) -> ServerSentEvent:
    """Строгое событие ``ripple``: адаптер и подпись вольт в каждом событии."""
    return ServerSentEvent(
        event="ripple",
        retry=RETRY_MS,
        data=ripple_payload(snapshot),
    )
