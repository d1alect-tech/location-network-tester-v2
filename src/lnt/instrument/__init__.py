"""Живой режим прибора: фейк-прибор, софт edge-триггер, кадры, сервис владения.

Публичная поверхность — ``InstrumentService`` (единственный владелец ручки
прибора между ``start`` и ``stop``, issue #26), ``TriggerConfig``/``find_edge``
(софтверный edge-триггер без предтриггера), ``LiveFrame``/``FrameAssembler``
(сборка кадров из блоков прибора) и фейки ``FakeHantekScope``/``ManualClock``
для работы без железа и без ``sleep`` в тестах, а ``LiveCaptureGate`` —
preflight-гейт live-старта и владение прибором для job-захвата (409, пока
вкладка держит ручку).
"""

from .fake_scope import FakeHantekScope, ManualClock
from .frames import UNSTABLE_LEAD_SAMPLES, FrameAssembler, LiveFrame
from .live_gate import (
    LIVE_BUSY_MESSAGE_RU,
    DeviceBusyError,
    LiveCaptureGate,
    LiveOwnership,
    LivePreflightBlockedError,
    LiveStartConfig,
)
from .service import InstrumentService, InstrumentState
from .trigger import (
    DEFAULT_AUTO_TIMEOUT_S,
    TriggerConfig,
    TriggerMode,
    TriggerSlope,
    TriggerSource,
    find_edge,
)

__all__ = [
    "DEFAULT_AUTO_TIMEOUT_S",
    "LIVE_BUSY_MESSAGE_RU",
    "UNSTABLE_LEAD_SAMPLES",
    "DeviceBusyError",
    "FakeHantekScope",
    "FrameAssembler",
    "InstrumentService",
    "InstrumentState",
    "LiveCaptureGate",
    "LiveFrame",
    "LiveOwnership",
    "LivePreflightBlockedError",
    "LiveStartConfig",
    "ManualClock",
    "TriggerConfig",
    "TriggerMode",
    "TriggerSlope",
    "TriggerSource",
    "find_edge",
]
