"""Чистая пост-диагностика качества захвата по raw-статистике и telemetry."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

from lnt.types import AcquisitionTelemetry, ChannelMode, SessionType

ADC_LEVELS: Final = 256.0
SUPPORTED_RANGES_V: Final = (0.5, 1.0, 5.0)


class QualityCode(StrEnum):
    """Стабильные коды дефектов качества записи."""

    CLIPPING = "clipping"
    UNDER_RANGE = "under_range"
    CALLBACK_GAP = "callback_gap"
    SHORT_BLOCK = "short_block"
    INCOMPLETE_CAPTURE = "incomplete_capture"


@dataclass(frozen=True, slots=True, kw_only=True)
class QualityThresholds:
    """Версионированные пороги интерпретации качества."""

    quality_thresholds_version: int
    clipping_ratio: float
    under_range_ratio: float
    callback_gap_factor: float
    minimum_effective_lsb_count: float


QUALITY_THRESHOLDS_V1: Final = QualityThresholds(
    quality_thresholds_version=1,
    clipping_ratio=0.98,
    under_range_ratio=0.1,
    callback_gap_factor=2.0,
    minimum_effective_lsb_count=8.0,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChannelQualityInput:
    """Сохранённые вольты канала и применённые аппаратные масштабы."""

    samples_v: NDArray[np.float32]
    range_v: float
    probe_multiplier: float = 1.0


@dataclass(frozen=True, slots=True, kw_only=True)
class AcquisitionQualityInput:
    """Телеметрия и каналы одной завершённой записи."""

    telemetry: AcquisitionTelemetry
    session_type: SessionType
    channel_mode: ChannelMode
    ch1: ChannelQualityInput
    ch2: ChannelQualityInput | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ChannelQuality:
    """Персистентный набор численных признаков одного канала."""

    channel: Literal["ch1", "ch2"]
    peak_v: float
    full_scale_v: float
    peak_range_ratio: float
    effective_lsb_count: float
    clip_count: int
    suggested_range_v: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class QualityFinding:
    """Машиночитаемое наблюдение с русской ручной рекомендацией."""

    code: QualityCode
    channel: Literal["ch1", "ch2"] | None
    message_ru: str
    recovery_action_ru: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AcquisitionQuality:
    """Готовый к последующей persistence итог без raw-модификаций."""

    quality_thresholds_version: int
    channels: tuple[ChannelQuality, ...]
    findings: tuple[QualityFinding, ...]
    maximum_callback_gap_s: float
    short_block_count: int


def assess_acquisition_quality(
    source: AcquisitionQualityInput,
    thresholds: QualityThresholds = QUALITY_THRESHOLDS_V1,
) -> AcquisitionQuality:
    """Диагностирует clipping, LSB usage и callback completeness без действий."""
    # Масштаб задан ChannelQualityInput; probe применяется ровно один раз.
    ch1_quality = _channel_quality(
        "ch1",
        source.ch1,
        source.telemetry.ch1_clip_low_count + source.telemetry.ch1_clip_high_count,
        thresholds,
    )
    channels = [ch1_quality]
    if source.channel_mode is ChannelMode.DUAL and source.ch2 is not None:
        channels.append(
            _channel_quality(
                "ch2",
                source.ch2,
                source.telemetry.ch2_clip_low_count + source.telemetry.ch2_clip_high_count,
                thresholds,
            )
        )
    findings = [
        finding for quality in channels for finding in _channel_findings(quality, thresholds)
    ]
    findings.extend(_stream_findings(source.telemetry, thresholds))
    return AcquisitionQuality(
        quality_thresholds_version=thresholds.quality_thresholds_version,
        channels=tuple(channels),
        findings=tuple(findings),
        maximum_callback_gap_s=max(source.telemetry.callback_gaps_s, default=0.0),
        short_block_count=source.telemetry.short_block_count,
    )


def _channel_quality(
    channel: Literal["ch1", "ch2"],
    source: ChannelQualityInput,
    clip_count: int,
    thresholds: QualityThresholds,
) -> ChannelQuality:
    peak = float(np.max(np.abs(source.samples_v))) if source.samples_v.size else 0.0
    full_scale = source.range_v * 1.024 * source.probe_multiplier
    ratio = peak / full_scale if full_scale > 0.0 else 0.0
    lsb_count = ratio * (ADC_LEVELS / 2.0)
    suggested = _suggested_range(source, ratio, clip_count, thresholds)
    return ChannelQuality(
        channel=channel,
        peak_v=peak,
        full_scale_v=full_scale,
        peak_range_ratio=ratio,
        effective_lsb_count=lsb_count,
        clip_count=clip_count,
        suggested_range_v=suggested,
    )


def _suggested_range(
    source: ChannelQualityInput,
    ratio: float,
    clip_count: int,
    thresholds: QualityThresholds,
) -> float | None:
    if clip_count > 0 or ratio >= thresholds.clipping_ratio:
        larger = tuple(value for value in SUPPORTED_RANGES_V if value > source.range_v)
        return min(larger, default=None)
    if ratio < thresholds.under_range_ratio:
        smaller = tuple(value for value in SUPPORTED_RANGES_V if value < source.range_v)
        return min(smaller, default=None)
    return None


def _channel_findings(
    quality: ChannelQuality,
    thresholds: QualityThresholds,
) -> tuple[QualityFinding, ...]:
    if quality.clip_count > 0 or quality.peak_range_ratio >= thresholds.clipping_ratio:
        return (
            QualityFinding(
                code=QualityCode.CLIPPING,
                channel=quality.channel,
                message_ru=f"{quality.channel}: обнаружено касание рельсов АЦП.",
                recovery_action_ru=(
                    "Рассмотрите больший диапазон вручную; исходные данные сохранены."
                ),
            ),
        )
    if (
        quality.peak_range_ratio < thresholds.under_range_ratio
        or quality.effective_lsb_count < thresholds.minimum_effective_lsb_count
    ):
        return (
            QualityFinding(
                code=QualityCode.UNDER_RANGE,
                channel=quality.channel,
                message_ru=f"{quality.channel}: сигнал использует слишком мало диапазона/LSB.",
                recovery_action_ru=(
                    "Рассмотрите более узкий диапазон вручную; автоматический перезахват запрещён."
                ),
            ),
        )
    return ()


def _stream_findings(
    telemetry: AcquisitionTelemetry,
    thresholds: QualityThresholds,
) -> tuple[QualityFinding, ...]:
    findings: list[QualityFinding] = []
    maximum_gap = max(telemetry.callback_gaps_s, default=0.0)
    if maximum_gap > telemetry.expected_block_interval_s * thresholds.callback_gap_factor:
        findings.append(
            QualityFinding(
                code=QualityCode.CALLBACK_GAP,
                channel=None,
                message_ru="Между callback обнаружен чрезмерный временной разрыв.",
                recovery_action_ru=(
                    "Проверьте USB-нагрузку и фоновые процессы перед следующим ручным захватом."
                ),
            )
        )
    if telemetry.short_block_count > 0:
        findings.append(
            QualityFinding(
                code=QualityCode.SHORT_BLOCK,
                channel=None,
                message_ru="Поток содержит короткие callback-блоки.",
                recovery_action_ru="Проверьте USB-стабильность; текущие raw-данные не скрываются.",
            )
        )
    if telemetry.captured_samples < telemetry.requested_samples:
        findings.append(
            QualityFinding(
                code=QualityCode.INCOMPLETE_CAPTURE,
                channel=None,
                message_ru="Получено меньше отсчётов, чем было запрошено.",
                recovery_action_ru="Устраните причину разрыва и решите о новом захвате вручную.",
            )
        )
    return tuple(findings)
