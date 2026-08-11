"""Pydantic-модели запросов панели и перечисления жизненного цикла задач."""

# ПРИМЕЧАНИЕ О ВОССТАНОВЛЕНИИ: первые ~4 КБ файла утрачены при сбое диска;
# голова реконструирована по тестам и модулям-потребителям, хвост оригинальный.

import re
from enum import StrEnum
from typing import Annotated, ClassVar, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from lnt.signals import PROFILES


class JobKind(StrEnum):
    """Вид фоновой задачи панели."""

    SIMULATE = "simulate"
    CAPTURE = "capture"
    ANALYZE = "analyze"
    COMPARE = "compare"
    SELFTEST = "selftest"
    DEVICE_CHECK = "device_check"


class JobStatus(StrEnum):
    """Статус жизненного цикла задачи."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class JobStage(StrEnum):
    """Текущий этап выполнения задачи."""

    QUEUED = "queued"
    SIMULATING = "simulating"
    CAPTURING = "capturing"
    ANALYZING = "analyzing"
    COMPARING = "comparing"
    SELFTEST = "selftest"
    CHECKING_DEVICE = "checking_device"
    DONE = "done"


_RANGES_V: Final = frozenset({5.0, 1.0, 0.5})
_CHILD_NAME_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

type _PositiveFiniteFloat = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]


def _validated_child_name(value: str) -> str:
    """Принимает только безопасные имена дочерних каталогов сессий."""
    unsafe = (
        value in {".", ".."}
        or "/" in value
        or "\\" in value
        or _CHILD_NAME_PATTERN.fullmatch(value) is None
    )
    if unsafe:
        raise PydanticCustomError(
            "unsafe_session_name",
            "небезопасное имя каталога сессии: {name}",
            {"name": value},
        )
    return value


class _SeriesRequest(BaseModel):
    """Общие поля запросов, порождающих серию сессий."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    output_name: str | None = None
    label: str | None = None
    repeat: Annotated[int, Field(ge=1)] = 1
    interval_s: Annotated[float, Field(ge=0.0, allow_inf_nan=False)] = 0.0

    @field_validator("output_name")
    @classmethod
    def validate_output_name(cls, value: str | None) -> str | None:
        """Проверяет запрошенное имя выходного каталога."""
        if value is None:
            return None
        return _validated_child_name(value)


class SimulateRequest(_SeriesRequest):
    """Запрос на синтетическую сессию по именованному профилю."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["simulate"]
    profile: str
    duration_s: _PositiveFiniteFloat = 2.4
    sample_rate_hz: _PositiveFiniteFloat = 500_000.0
    seed: Annotated[int, Field(ge=0)] = 6022
    channels: Literal[1, 2] = 2

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str) -> str:
        """Принимает только известные профили симуляции."""
        if value not in PROFILES:
            known = ", ".join(sorted(PROFILES))
            raise PydanticCustomError(
                "unknown_profile",
                "неизвестный профиль {profile}; доступны: {known}",
                {"profile": value, "known": known},
            )
        return value


class CaptureRequest(_SeriesRequest):
    """Запрос на захват сессии с осциллографа."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["capture"]
    duration_s: _PositiveFiniteFloat = 2.4
    sample_rate_hz: _PositiveFiniteFloat = 8_000_000.0
    range_v: float = 5.0
    self_noise: bool = False
    baseline_session: str | None = None
    channels: Literal[1, 2] = 2
    input: Literal["rc", "transformer"] = "rc"

    @field_validator("baseline_session")
    @classmethod
    def validate_baseline_session(cls, value: str | None) -> str | None:
        """Проверяет имя базовой сессии самошума (имя соседнего каталога)."""
        if value is None:
            return None
        return _validated_child_name(value)

    @model_validator(mode="after")
    def validate_baseline_pairing(self) -> "CaptureRequest":
        """Отклоняет базовую сессию у записи самошума."""
        if self.self_noise and self.baseline_session is not None:
            raise PydanticCustomError(
                "baseline_with_self_noise",
                "самошум не принимает базовую сессию",
            )
        return self

    @model_validator(mode="after")
    def validate_transformer_input(self) -> "CaptureRequest":
        """Трансформаторный вход — одноканальный и без самошума/базовой сессии."""
        if self.input != "transformer":
            return self
        if self.channels != 1:
            raise PydanticCustomError(
                "transformer_requires_single_channel",
                "трансформаторный вход занимает единственный пробник — выберите 1 канал",
            )
        if self.self_noise:
            raise PydanticCustomError(
                "transformer_with_self_noise",
                "запись качества сети несовместима с режимом самошума",
            )
        if self.baseline_session is not None:
            raise PydanticCustomError(
                "transformer_with_baseline",
                "запись качества сети не принимает базовую сессию",
            )
        return self

    @field_validator("range_v")
    @classmethod
    def validate_range_v(cls, value: float) -> float:
        """Принимает только поддерживаемые диапазоны осциллографа."""
        if value not in _RANGES_V:
            raise PydanticCustomError(
                "unsupported_voltage_range",
                "диапазон должен быть одним из: 5.0, 1.0, 0.5 В",
            )
        return value


class AnalyzeRequest(BaseModel):
    """Запрос на анализ сохранённой сессии."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["analyze"]
    session_name: str

    @field_validator("session_name")
    @classmethod
    def validate_session_name(cls, value: str) -> str:
        """Проверяет имя анализируемой сессии."""
        return _validated_child_name(value)


class CompareRequest(BaseModel):
    """Запрос на сравнение двух сохранённых сессий."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["compare"]
    session_a: str
    session_b: str

    @field_validator("session_a", "session_b")
    @classmethod
    def validate_session_name(cls, value: str) -> str:
        """Проверяет имя одной из сравниваемых сессий."""
        return _validated_child_name(value)


class SelftestRequest(BaseModel):
    """Запрос на сквозную самопроверку LNT."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["selftest"]


class DeviceCheckRequest(BaseModel):
    """Запрос на проверку доступности осциллографа."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["device_check"]


JobRequest = Annotated[
    SimulateRequest
    | CaptureRequest
    | AnalyzeRequest
    | CompareRequest
    | SelftestRequest
    | DeviceCheckRequest,
    Field(discriminator="kind"),
]

_JOB_REQUEST_ADAPTER: Final[TypeAdapter[JobRequest]] = TypeAdapter(JobRequest)


def parse_job_request(data: object) -> JobRequest:
    """Разбирает недоверенные данные в конкретный тип запроса по ``kind``."""
    return _JOB_REQUEST_ADAPTER.validate_python(data)
