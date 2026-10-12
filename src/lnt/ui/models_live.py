"""Проводной контракт живого режима: управление, статус владения, кадр потока.

Статус — ДВА независимых поля: ``state`` (idle|running|stopped, единственная
правда — ``InstrumentService.state``) и ``mode`` (real|sim, объявленное
происхождение отсчётов). Панель не смешивает их и не выводит режим из
состояния. ``busy_reason`` несёт каноническую причину занятости прибора
(``LIVE_BUSY_MESSAGE_RU``) — тот же текст, который получает job-захват в 409.

Кадр уходит в SSE ЦЕЛИКОМ, одним событием: вольты float32 после масштаба АЦП
(``adc_calibration``: raw uint8 -> В пересчитывает ``InstrumentService``, панель
вольты не пересчитывает и не фабрикаует) и после display-only прореживания
``decimate_waveform`` (<= 4000 точек на канал) — без повторного бакетинга и без
склейки кадров. ``time_s`` канала — секунды от начала окна кадра (t0 = 0):
абсолютное время потока сервис не ведёт. ``calibration_used`` — провенанс вольт:
True только при per-device таблице АЦП. ``skipped_frames`` — display-пропуски
кадров темпом панели (не потери прибора: те в ``dropped_samples``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field

from lnt.instrument.live_gate import LIVE_BUSY_MESSAGE_RU, LiveMode, LiveStartConfig
from lnt.instrument.service import (
    DEFAULT_CH1_RANGE_V,
    DEFAULT_SAMPLE_RATE_HZ,
    InstrumentState,
)
from lnt.instrument.trigger import (
    DEFAULT_AUTO_TIMEOUT_S,
    TriggerConfig,
    TriggerMode,
    TriggerSlope,
    TriggerSource,
)
from lnt.ui.decimation import decimate_waveform

if TYPE_CHECKING:
    from lnt.instrument.frames import LiveFrame
    from lnt.instrument.service import InstrumentService

# Причины отказа живого режима на языке панели (деталь HTTP-ответа).
LIVE_ALREADY_RUNNING_RU: Final = "живой режим уже запущен: сначала stop"
LIVE_NOT_RUNNING_RU: Final = "живой режим не запущен: сначала start"
LIVE_UNAVAILABLE_RU: Final = "живой режим не инициализирован"
# Display-бюджет формы волны панели (ui/AGENTS.md): не больше 4000 точек.
MAX_FRAME_POINTS: Final = 4_000

type _PositiveFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
type _FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class _StrictModel(BaseModel):
    """Неизвестные поля отклоняются, значение неизменяемо: контракт стабилен."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class LiveTriggerModel(_StrictModel):
    """Триггер живого потока: зеркало ``TriggerConfig``, правда — в сервисе."""

    level_v: _FiniteFloat = 0.0
    slope: TriggerSlope = TriggerSlope.RISING
    source: TriggerSource = TriggerSource.CH1
    mode: TriggerMode = TriggerMode.AUTO
    auto_timeout_s: _PositiveFloat = DEFAULT_AUTO_TIMEOUT_S

    def to_config(self) -> TriggerConfig:
        """Собирает доменную конфигурацию; границы проверяет ``TriggerConfig``."""
        return TriggerConfig(
            level_v=self.level_v,
            slope=self.slope,
            source=self.source,
            mode=self.mode,
            auto_timeout_s=self.auto_timeout_s,
        )

    @classmethod
    def of(cls, config: TriggerConfig) -> LiveTriggerModel:
        """Проводное зеркало конфигурации сервиса (ответ и статус)."""
        return cls(
            level_v=config.level_v,
            slope=config.slope,
            source=config.source,
            mode=config.mode,
            auto_timeout_s=config.auto_timeout_s,
        )


class LiveStartRequest(_StrictModel):
    """Тело ``POST /api/live/start``: каденс, диапазон CH1, пробник, триггер."""

    sample_rate_hz: _PositiveFloat = DEFAULT_SAMPLE_RATE_HZ
    ch1_range_v: _PositiveFloat = DEFAULT_CH1_RANGE_V
    ch1_probe_multiplier: _PositiveFloat = 1.0
    trigger: LiveTriggerModel = Field(default_factory=LiveTriggerModel)

    def to_start_config(self) -> LiveStartConfig:
        """Доменная конфигурация старта; границы проверяют гейт и сервис."""
        return LiveStartConfig(
            trigger=self.trigger.to_config(),
            sample_rate_hz=self.sample_rate_hz,
            ch1_range_v=self.ch1_range_v,
            ch1_probe_multiplier=self.ch1_probe_multiplier,
        )


class LiveStatePayload(_StrictModel):
    """Статус владения прибором: ``state`` и ``mode`` — два явных поля."""

    state: InstrumentState
    mode: LiveMode
    busy_reason: str | None = None
    trigger: LiveTriggerModel | None = None


class LiveChannelSeries(_StrictModel):
    """Прореженный ряд канала: секунды от начала кадра и вольты."""

    time_s: tuple[float, ...]
    voltage_v: tuple[float, ...]
    point_count: int


class LiveFramePayload(_StrictModel):
    """Кадр живого потока: одно SSE-событие, каналы прорежены после вольт."""

    frame_index: int
    triggered: bool
    emitted_at_s: float
    dropped_samples: int
    skipped_frames: int
    sample_rate_hz: float
    frame_samples: int
    decimated: bool
    calibration_used: bool
    ch1: LiveChannelSeries
    ch2: LiveChannelSeries


def state_payload(service: InstrumentService | None, *, mode: LiveMode) -> LiveStatePayload:
    """Снимает статус с сервиса на каждый запрос: кэша состояния в панели нет."""
    if service is None:
        return LiveStatePayload(state=InstrumentState.IDLE, mode=mode)
    return LiveStatePayload(
        state=service.state,
        mode=mode,
        busy_reason=LIVE_BUSY_MESSAGE_RU if service.is_running else None,
        trigger=LiveTriggerModel.of(service.trigger),
    )


def frame_payload(
    frame: LiveFrame,
    *,
    max_points: int,
    calibration_used: bool,
    skipped_frames: int,
) -> LiveFramePayload:
    """Кадр -> провод: прореживание уже готовых вольт, кадр целиком."""
    sample_count = int(frame.ch1.size)
    ch1 = decimate_waveform(frame.ch1, sample_rate_hz=frame.sample_rate_hz, max_points=max_points)
    ch2 = decimate_waveform(frame.ch2, sample_rate_hz=frame.sample_rate_hz, max_points=max_points)
    return LiveFramePayload(
        frame_index=frame.frame_index,
        triggered=frame.triggered,
        emitted_at_s=frame.emitted_at_s,
        dropped_samples=frame.dropped_samples,
        skipped_frames=skipped_frames,
        sample_rate_hz=frame.sample_rate_hz,
        frame_samples=sample_count,
        decimated=sample_count > max_points,
        calibration_used=calibration_used,
        ch1=LiveChannelSeries(time_s=ch1.x, voltage_v=ch1.y, point_count=ch1.point_count),
        ch2=LiveChannelSeries(time_s=ch2.x, voltage_v=ch2.y, point_count=ch2.point_count),
    )
