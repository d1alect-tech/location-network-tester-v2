"""Pydantic-контракты версионированных профилей."""

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from lnt.profiles import DamperState, ProfileKind


class LocationData(BaseModel):
    """Данные профиля локации."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    alias: str
    outlet: str
    circuit: str


class EquipmentData(BaseModel):
    """Данные профиля оборудования."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    alias: str
    model: str


class QuantityData(BaseModel):
    """Положительная величина с единицей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    value: float = Field(gt=0)
    unit: str


class FrontEndData(BaseModel):
    """Данные входного тракта."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    resistance: QuantityData
    c1: QuantityData
    c2: QuantityData


class TransformerData(BaseModel):
    """Данные трансформатора."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    nominal_primary: QuantityData
    nominal_secondary: QuantityData


class ConditionsData(BaseModel):
    """Данные условий измерения."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    damper_state: DamperState
    nearby_load_states: tuple[str, ...]


class LocationRequest(BaseModel):
    """Команда записи location profile."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    kind: Literal[ProfileKind.LOCATION]
    data: LocationData


class EquipmentRequest(BaseModel):
    """Команда записи equipment profile."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    kind: Literal[ProfileKind.EQUIPMENT]
    data: EquipmentData


class FrontEndRequest(BaseModel):
    """Команда записи front-end profile."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    kind: Literal[ProfileKind.FRONT_END]
    data: FrontEndData


class TransformerRequest(BaseModel):
    """Команда записи transformer profile."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    kind: Literal[ProfileKind.TRANSFORMER]
    data: TransformerData


class ConditionsRequest(BaseModel):
    """Команда записи conditions profile."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    kind: Literal[ProfileKind.CONDITIONS]
    data: ConditionsData


ProfileRequest = Annotated[
    LocationRequest | EquipmentRequest | FrontEndRequest | TransformerRequest | ConditionsRequest,
    Field(discriminator="kind"),
]
ProfileDataResponse = LocationData | EquipmentData | FrontEndData | TransformerData | ConditionsData


class ProfileResponse(BaseModel):
    """Одна неизменяемая revision профиля."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    profile_id: str
    kind: ProfileKind
    revision: int
    captured_at: str
    data: ProfileDataResponse


class ProfileListResponse(BaseModel):
    """Список revisions профилей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    items: tuple[ProfileResponse, ...]
