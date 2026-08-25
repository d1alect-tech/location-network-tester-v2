"""Типы домена LNT: перечисления и замороженные метаданные сессии."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from lnt.errors import InputError

SCHEMA_VERSION = 1
CH1_MANIFEST_SCHEMA_VERSION = 2

ParameterValue = float | int | str


class SessionSource(StrEnum):
    """Происхождение данных сессии."""

    DEVICE = "device"
    SYNTHETIC = "synthetic"


class SessionType(StrEnum):
    """Назначение сессии в протоколе измерений."""

    MEASUREMENT = "measurement"
    SELF_NOISE = "self_noise"
    LINE_QUALITY = "line_quality"
    CM_DM = "cm_dm"
    CM_DM_CALIBRATION = "cm_dm_calibration"


class ChannelRole(StrEnum):
    """Роль канала в измерительной схеме."""

    HF_PROBE = "hf_probe"
    LF_TRANSFORMER = "lf_transformer"


class ChannelMode(StrEnum):
    """Состав каналов сессии: оба канала или только CH1 (один пробник)."""

    DUAL = "dual"
    CH1_ONLY = "ch1_only"


class ComponentValuesBasis(StrEnum):
    """Происхождение номиналов RC-компонентов в CH1 transfer-модели."""

    NOMINAL = "nominal"
    OPERATOR_MEASURED = "operator_measured"


class ReferenceAssumption(StrEnum):
    """Фиксированная оговорка для плавающего входа относительно host earth."""

    FLOATING_HOST_UNVERIFIED = "floating_host_unverified"


@dataclass(frozen=True, slots=True, kw_only=True)
class TransferCorrection:
    """Локальная амплитудная и PSD-коррекция одной частоты CH1 transfer-модели."""

    equivalent_capacitance_f: float
    amplitude_gain: float

    def input_amplitude(self, *, scope_amplitude_v: float) -> float:
        """Возвращает исходную амплитуду до ослабления transfer-функцией."""
        return scope_amplitude_v / self.amplitude_gain

    def input_psd(self, *, scope_psd_v2_per_hz: float) -> float:
        """Возвращает PSD до ослабления transfer-функцией."""
        return scope_psd_v2_per_hz / self.amplitude_gain**2


@dataclass(frozen=True, slots=True, kw_only=True)
class FloatingDifferentialRcShunt:
    """Явная CH1-модель плавающего дифференциального RC-шунта."""

    resistance_ohm: float
    c1_f: float
    c2_f: float
    component_values_basis: ComponentValuesBasis
    reference_assumption: ReferenceAssumption

    def __post_init__(self) -> None:
        """Отклоняет не физические номиналы RC-модели на границе домена."""
        for name, value in (
            ("resistance_ohm", self.resistance_ohm),
            ("c1_f", self.c1_f),
            ("c2_f", self.c2_f),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise InputError(f"ch1_setup: {name} должен быть конечным и положительным")

    def correction_at(self, *, frequency_hz: float) -> TransferCorrection:
        """Вычисляет локальные |H| и C_eq для одной частоты."""
        equivalent_capacitance_f = (self.c1_f * self.c2_f) / (self.c1_f + self.c2_f)
        angular = 2.0 * math.pi * frequency_hz
        numerator = angular * self.resistance_ohm * equivalent_capacitance_f
        return TransferCorrection(
            equivalent_capacitance_f=equivalent_capacitance_f,
            amplitude_gain=numerator / math.sqrt(1.0 + numerator**2),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ScopeInputTerminated:
    """Явная CH1-модель входа осциллографа с резистивной терминализацией."""

    termination_resistance_ohm: float

    def __post_init__(self) -> None:
        """Отклоняет не физическое сопротивление scope-termination."""
        if (
            not math.isfinite(self.termination_resistance_ohm)
            or self.termination_resistance_ohm <= 0.0
        ):
            raise InputError(
                "ch1_setup: termination_resistance_ohm должен быть конечным и положительным"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformerLineProbe:
    """Явная CH1-модель трансформаторного входа для оценки качества сети 50 Гц.

    ``probe_multiplier`` — коэффициент пробника (10x рекомендован: вторичка
    ~10 В RMS на холостом ходу против диапазона АЦП +-5 В); отсчёты ch1.npy
    хранятся уже в реальных вольтах вторички.
    """

    nominal_primary_v: float
    nominal_secondary_v: float
    probe_multiplier: float

    def __post_init__(self) -> None:
        """Отклоняет не физические номиналы трансформаторной модели."""
        for name, value in (
            ("nominal_primary_v", self.nominal_primary_v),
            ("nominal_secondary_v", self.nominal_secondary_v),
            ("probe_multiplier", self.probe_multiplier),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise InputError(f"ch1_setup: {name} должен быть конечным и положительным")


type Ch1Setup = FloatingDifferentialRcShunt | ScopeInputTerminated | TransformerLineProbe


@dataclass(frozen=True, slots=True, kw_only=True)
class ChannelMeta:
    """Метаданные одного канала осциллографа."""

    filename: str
    role: ChannelRole
    unit: str
    front_end: str
    range_code: int
    probe_multiplier: float


@dataclass(frozen=True, slots=True, kw_only=True)
class AcquisitionTelemetry:
    """Телеметрия захвата: полнота потока, здоровье callback-цепочки и клиппинг.

    Клип-счётчики — число сохранённых отсчётов на рельсах АЦП (raw 0 / raw 255);
    без них хвост гистограммы транзиентов недостоверен.
    """

    requested_samples: int
    captured_samples: int
    callback_count: int
    block_lengths: tuple[int, ...]
    callback_gaps_s: tuple[float, ...]
    expected_block_interval_s: float
    short_block_count: int
    ch1_clip_low_count: int
    ch1_clip_high_count: int
    ch2_clip_low_count: int
    ch2_clip_high_count: int
    calibration_used: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SeriesPosition:
    """Позиция сессии в серии ``--repeat/--interval`` (index 1-based)."""

    index: int
    total: int
    interval_s: float

    def as_parameters(self) -> dict[str, ParameterValue]:
        """Ключи серии для ``parameters`` манифеста."""
        return {
            "series_index": self.index,
            "series_total": self.total,
            "series_interval_s": self.interval_s,
        }

    def id_suffix(self) -> str:
        """Суффикс ``-NNN`` для уникальности session_id внутри серии."""
        return f"-{self.index:03d}"


@dataclass(frozen=True, slots=True, kw_only=True)
class SyntheticTruth:
    """Ground truth синтетической сессии для сквозной проверки анализа."""

    needle_mean_v: float
    needle_sigma_ratio: float
    needle_jitter_us: float
    ring_f0_hz: float
    ring_q: float
    async_rate_hz: float
    lf_envelope_cv: float


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionManifest:
    """Полное описание сессии; schema v1 без модели, schema v2 с ``ch1_setup``."""

    schema_version: int
    session_id: str
    created_utc: str
    completed_utc: str
    source: SessionSource
    session_type: SessionType
    sample_rate_hz: float
    duration_s: float
    sample_count: int
    line_frequency_hz: float
    profile: str | None
    baseline_session: str | None
    parameters: Mapping[str, ParameterValue] = field(default_factory=dict)
    ch1: ChannelMeta
    ch2: ChannelMeta | None
    acquisition_telemetry: AcquisitionTelemetry | None
    synthetic_truth: SyntheticTruth | None
    ch1_setup: Ch1Setup | None = None
