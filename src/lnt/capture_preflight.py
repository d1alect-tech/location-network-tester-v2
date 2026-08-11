"""Чистая проверка безопасности параметров до аппаратного захвата."""

import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from lnt._input_reference_baseline import CompatibleBaseline, IncompatibleBaseline
from lnt.device_diagnostics import DeviceState
from lnt.types import (
    Ch1Setup,
    ChannelMode,
    FloatingDifferentialRcShunt,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)

MAX_CAPTURE_SAMPLES: Final = 2_147_483_647
FLOAT32_BYTES: Final = 4
DISK_SAFETY_FACTOR: Final = 1.2
WIDEST_RANGE_V: Final = 5.0
TEN_X_PROBE: Final = 10.0
MODE_RECOVERY_START: Final = "Выберите RC для measurement, termination для self-noise"
MODE_RECOVERY_END: Final = "или transformer для line-quality."
WEAK_RECOVERY_START: Final = "Если ожидаемый пик безопасен, выберите диапазон 0,5 В вручную"
WEAK_RECOVERY_END: Final = "после пробной оценки."


class FindingSeverity(StrEnum):
    """Влияние finding на возможность продолжить захват."""

    BLOCK = "block"
    WARN = "warn"


class BaselineCompatibility(StrEnum):
    """Результат существующей baseline qualification."""

    NOT_REQUESTED = "not_requested"
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True, kw_only=True)
class CapturePreflightRequest:
    """Все параметры, влияющие на безопасный старт захвата."""

    session_root: Path
    session_type: SessionType
    channel_mode: ChannelMode
    ch1_setup: Ch1Setup
    sample_rate_hz: float
    duration_s: float
    range_v: float
    probe_multiplier: float
    baseline_requested: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureEnvironment:
    """Внедряемые результаты I/O-проб без скрытых системных обращений."""

    device_state: DeviceState
    free_bytes: int
    root_writable: bool
    baseline_compatibility: BaselineCompatibility
    baseline_reason_code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PreflightFinding:
    """Стабильный код, русское сообщение и ручное восстановление."""

    severity: FindingSeverity
    code: str
    message_ru: str
    recovery_action_ru: str


def baseline_compatibility_from_resolution(
    resolution: CompatibleBaseline | IncompatibleBaseline,
) -> tuple[BaselineCompatibility, str | None]:
    """Адаптирует существующий resolve_compatible_baseline без дублирования правил."""
    match resolution:
        case CompatibleBaseline():
            return BaselineCompatibility.COMPATIBLE, None
        case IncompatibleBaseline(reason_code=reason):
            return BaselineCompatibility.INCOMPATIBLE, reason


def run_capture_preflight(
    request: CapturePreflightRequest,
    environment: CaptureEnvironment,
) -> tuple[PreflightFinding, ...]:
    """Возвращает все blockers/warnings, ничего не меняя в запросе или железе."""
    findings: list[PreflightFinding] = []
    findings.extend(_device_findings(environment.device_state))
    findings.extend(_mode_findings(request))
    findings.extend(_capacity_findings(request, environment))
    findings.extend(_baseline_findings(request, environment))
    findings.extend(_range_findings(request))
    return tuple(findings)


def _finding(
    severity: FindingSeverity,
    code: str,
    message: str,
    recovery: str,
) -> PreflightFinding:
    return PreflightFinding(
        severity=severity,
        code=code,
        message_ru=message,
        recovery_action_ru=recovery,
    )


def _device_findings(state: DeviceState) -> tuple[PreflightFinding, ...]:
    if state is DeviceState.READY:
        return ()
    code = f"device_{state.value}"
    return (
        _finding(
            FindingSeverity.BLOCK,
            code,
            f"Устройство не готово: {state.value}.",
            "Выполните указанное диагностикой устройства действие и повторите preflight.",
        ),
    )


def _mode_findings(request: CapturePreflightRequest) -> tuple[PreflightFinding, ...]:
    expected_setup = (
        (
            request.session_type is SessionType.MEASUREMENT
            and isinstance(request.ch1_setup, FloatingDifferentialRcShunt)
        )
        or (
            request.session_type is SessionType.SELF_NOISE
            and isinstance(request.ch1_setup, ScopeInputTerminated)
        )
        or (
            request.session_type is SessionType.LINE_QUALITY
            and isinstance(request.ch1_setup, TransformerLineProbe)
        )
    )
    findings: list[PreflightFinding] = []
    if not expected_setup:
        findings.append(
            _finding(
                FindingSeverity.BLOCK,
                "mode_setup_mismatch",
                "Тип сессии не соответствует модели входа CH1.",
                f"{MODE_RECOVERY_START} {MODE_RECOVERY_END}",
            )
        )
    if (
        request.session_type is SessionType.LINE_QUALITY
        and request.channel_mode is not ChannelMode.CH1_ONLY
    ):
        findings.append(
            _finding(
                FindingSeverity.BLOCK,
                "line_quality_requires_single_channel",
                "Line-quality использует один трансформаторный канал CH1.",
                "Выберите одноканальный режим; preflight не меняет его автоматически.",
            )
        )
    return tuple(findings)


def _capacity_findings(
    request: CapturePreflightRequest,
    environment: CaptureEnvironment,
) -> tuple[PreflightFinding, ...]:
    findings: list[PreflightFinding] = []
    sample_count = request.sample_rate_hz * request.duration_s
    if not math.isfinite(sample_count) or sample_count < 1 or sample_count > MAX_CAPTURE_SAMPLES:
        findings.append(
            _finding(
                FindingSeverity.BLOCK,
                "sample_count_overflow",
                "Частота и длительность дают недопустимое число отсчётов.",
                f"Уменьшите rate или duration до не более {MAX_CAPTURE_SAMPLES} отсчётов.",
            )
        )
        return tuple(findings)
    channel_count = 1 if request.channel_mode is ChannelMode.CH1_ONLY else 2
    required = math.ceil(sample_count * channel_count * FLOAT32_BYTES * DISK_SAFETY_FACTOR)
    if environment.free_bytes < required:
        findings.append(
            _finding(
                FindingSeverity.BLOCK,
                "insufficient_disk_space",
                f"Свободно {environment.free_bytes} байт, требуется не менее {required} байт.",
                "Освободите место или выберите другой корень сессий.",
            )
        )
    if not environment.root_writable:
        findings.append(
            _finding(
                FindingSeverity.BLOCK,
                "session_root_not_writable",
                "Корень сессий недоступен для записи.",
                "Выберите существующий доступный каталог или исправьте права записи.",
            )
        )
    return tuple(findings)


def _baseline_findings(
    request: CapturePreflightRequest,
    environment: CaptureEnvironment,
) -> tuple[PreflightFinding, ...]:
    if not request.baseline_requested:
        return ()
    if environment.baseline_compatibility is BaselineCompatibility.COMPATIBLE:
        return ()
    reason = environment.baseline_reason_code or environment.baseline_compatibility.value
    return (
        _finding(
            FindingSeverity.BLOCK,
            "baseline_incompatible",
            f"Baseline не прошёл существующую проверку совместимости: {reason}.",
            "Выберите baseline с теми же source/rate/range/probe/setup и telemetry без clipping.",
        ),
    )


def _range_findings(request: CapturePreflightRequest) -> tuple[PreflightFinding, ...]:
    if request.session_type is SessionType.LINE_QUALITY and request.range_v < WIDEST_RANGE_V:
        return (
            _finding(
                FindingSeverity.WARN,
                "line_quality_clipping_likely",
                "Пик вторички около 16 В при пробнике 10x может перегрузить выбранный диапазон.",
                "Выберите диапазон 5 В вручную; preflight не меняет настройку.",
            ),
        )
    if (
        request.session_type is SessionType.MEASUREMENT
        and request.range_v == WIDEST_RANGE_V
        and request.probe_multiplier >= TEN_X_PROBE
    ):
        return (
            _finding(
                FindingSeverity.WARN,
                "weak_signal_resolution",
                "Слабый RC-сигнал может использовать лишь несколько LSB на диапазоне 5 В.",
                f"{WEAK_RECOVERY_START} {WEAK_RECOVERY_END}",
            ),
        )
    return ()
