"""Неизменяемые типы пользовательских профилей LNT."""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from lnt.errors import InputError

ProfileId = NewType("ProfileId", str)


class ProfileKind(StrEnum):
    """Поддерживаемые виды профилей."""

    LOCATION = "location"
    EQUIPMENT = "equipment"
    FRONT_END = "front_end"
    TRANSFORMER = "transformer"
    CONDITIONS = "conditions"


class DamperState(StrEnum):
    """Наблюдаемое состояние демпфера."""

    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, kw_only=True)
class Quantity:
    """Конечная положительная величина с канонической единицей."""

    value: float
    unit: str

    def __post_init__(self) -> None:
        """Отклоняет не физические значения величин."""
        if not math.isfinite(self.value) or self.value <= 0.0:
            raise InputError("профиль: значение величины должно быть конечным и положительным")


@dataclass(frozen=True, slots=True, kw_only=True)
class LocationProfile:
    """Псевдоним места и электрическая точка подключения."""

    alias: str
    outlet: str
    circuit: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EquipmentProfile:
    """Пользовательское имя и модель измерительного оборудования."""

    alias: str
    model: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FrontEndProfile:
    """Параметры плавающего RC-шунта входного тракта."""

    resistance: Quantity
    c1: Quantity
    c2: Quantity

    @classmethod
    def from_si(cls, *, resistance_ohm: float, c1_f: float, c2_f: float) -> "FrontEndProfile":
        """Создаёт профиль из величин в системе SI."""
        return cls(
            resistance=Quantity(value=resistance_ohm, unit="ohm"),
            c1=Quantity(value=c1_f, unit="F"),
            c2=Quantity(value=c2_f, unit="F"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformerProfile:
    """Номиналы трансформатора измерительного тракта."""

    nominal_primary: Quantity
    nominal_secondary: Quantity

    @classmethod
    def from_si(
        cls, *, nominal_primary_v: float, nominal_secondary_v: float
    ) -> "TransformerProfile":
        """Создаёт профиль из номинальных напряжений в вольтах."""
        return cls(
            nominal_primary=Quantity(value=nominal_primary_v, unit="V"),
            nominal_secondary=Quantity(value=nominal_secondary_v, unit="V"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ConditionsProfile:
    """Состояния демпфера и ближайших нагрузок."""

    damper_state: DamperState
    nearby_load_states: tuple[str, ...]


type ProfileData = (
    LocationProfile | EquipmentProfile | FrontEndProfile | TransformerProfile | ConditionsProfile
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileSnapshot:
    """Зафиксированная ревизия профиля, пригодная для session context."""

    schema_version: int
    profile_id: ProfileId
    kind: ProfileKind
    revision: int
    captured_at: str
    data: ProfileData
