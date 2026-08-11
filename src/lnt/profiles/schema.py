"""Строгий JSON-контракт профилей schema 1."""

import re
from collections.abc import Mapping
from typing import Final

from lnt._manifest_json import JsonValue, decode_json_object, encode_json
from lnt.errors import InputError
from lnt.profiles.model import (
    ConditionsProfile,
    DamperState,
    EquipmentProfile,
    FrontEndProfile,
    LocationProfile,
    ProfileData,
    ProfileId,
    ProfileKind,
    ProfileSnapshot,
    Quantity,
    TransformerProfile,
)

_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOP: Final = frozenset({"schema_version", "profile_id", "kind", "revision", "captured_at", "data"})
_DATA_FIELDS: Final[dict[ProfileKind, frozenset[str]]] = {
    ProfileKind.LOCATION: frozenset({"alias", "outlet", "circuit"}),
    ProfileKind.EQUIPMENT: frozenset({"alias", "model"}),
    ProfileKind.FRONT_END: frozenset({"resistance", "c1", "c2"}),
    ProfileKind.TRANSFORMER: frozenset({"nominal_primary", "nominal_secondary"}),
    ProfileKind.CONDITIONS: frozenset({"damper_state", "nearby_load_states"}),
}


def parse_profile_id(raw: str) -> ProfileId:
    """Преобразует безопасный файловый идентификатор в доменный тип."""
    if _ID.fullmatch(raw) is None:
        raise InputError("профиль: небезопасный profile_id")
    return ProfileId(raw)


def profile_to_json(snapshot: ProfileSnapshot) -> str:
    """Сериализует проверенную неизменяемую ревизию."""
    if snapshot.schema_version != 1 or snapshot.revision < 1:
        raise InputError("профиль: неверная версия или revision")
    parse_profile_id(snapshot.profile_id)
    return encode_json(
        {
            "schema_version": 1,
            "profile_id": snapshot.profile_id,
            "kind": snapshot.kind.value,
            "revision": snapshot.revision,
            "captured_at": snapshot.captured_at,
            "data": _data_to_mapping(snapshot.data),
        }
    )


def profile_from_json(text: str) -> ProfileSnapshot:
    """Строго разбирает одну ревизию профиля."""
    raw = decode_json_object(text)
    _reject_unknown(raw, _TOP, "профиль")
    version = _integer(raw, "schema_version")
    if version != 1:
        raise InputError(f"профиль: неподдерживаемая schema_version: {version}")
    kind = _kind(_string(raw, "kind"))
    data = _mapping(raw, "data")
    _reject_unknown(data, _DATA_FIELDS[kind], f"профиль {kind.value}")
    revision = _integer(raw, "revision")
    if revision < 1:
        raise InputError("профиль: revision должна быть положительной")
    return ProfileSnapshot(
        schema_version=version,
        profile_id=parse_profile_id(_string(raw, "profile_id")),
        kind=kind,
        revision=revision,
        captured_at=_string(raw, "captured_at"),
        data=_parse_data(kind, data),
    )


def profile_kind(data: ProfileData) -> ProfileKind:
    """Возвращает дискриминатор конкретного типа профиля."""
    match data:
        case LocationProfile():
            return ProfileKind.LOCATION
        case EquipmentProfile():
            return ProfileKind.EQUIPMENT
        case FrontEndProfile():
            return ProfileKind.FRONT_END
        case TransformerProfile():
            return ProfileKind.TRANSFORMER
        case ConditionsProfile():
            return ProfileKind.CONDITIONS


def _data_to_mapping(data: ProfileData) -> dict[str, JsonValue]:
    match data:
        case LocationProfile(alias=alias, outlet=outlet, circuit=circuit):
            return {"alias": alias, "outlet": outlet, "circuit": circuit}
        case EquipmentProfile(alias=alias, model=model):
            return {"alias": alias, "model": model}
        case FrontEndProfile(resistance=resistance, c1=c1, c2=c2):
            return {"resistance": _quantity(resistance), "c1": _quantity(c1), "c2": _quantity(c2)}
        case TransformerProfile(nominal_primary=primary, nominal_secondary=secondary):
            return {
                "nominal_primary": _quantity(primary),
                "nominal_secondary": _quantity(secondary),
            }
        case ConditionsProfile(damper_state=state, nearby_load_states=loads):
            return {"damper_state": state.value, "nearby_load_states": list(loads)}


def _parse_data(kind: ProfileKind, raw: Mapping[str, JsonValue]) -> ProfileData:
    match kind:
        case ProfileKind.LOCATION:
            return LocationProfile(
                alias=_label(raw, "alias"),
                outlet=_label(raw, "outlet"),
                circuit=_label(raw, "circuit"),
            )
        case ProfileKind.EQUIPMENT:
            return EquipmentProfile(alias=_label(raw, "alias"), model=_label(raw, "model"))
        case ProfileKind.FRONT_END:
            return FrontEndProfile(
                resistance=_parse_quantity(raw, "resistance", "ohm"),
                c1=_parse_quantity(raw, "c1", "F"),
                c2=_parse_quantity(raw, "c2", "F"),
            )
        case ProfileKind.TRANSFORMER:
            return TransformerProfile(
                nominal_primary=_parse_quantity(raw, "nominal_primary", "V"),
                nominal_secondary=_parse_quantity(raw, "nominal_secondary", "V"),
            )
        case ProfileKind.CONDITIONS:
            loads = _list(raw, "nearby_load_states")
            return ConditionsProfile(
                damper_state=_damper(_string(raw, "damper_state")),
                nearby_load_states=tuple(_label_item(item) for item in loads),
            )


def _quantity(value: Quantity) -> dict[str, JsonValue]:
    return {"value": value.value, "unit": value.unit}


def _parse_quantity(raw: Mapping[str, JsonValue], key: str, expected_unit: str) -> Quantity:
    value = _mapping(raw, key)
    _reject_unknown(value, frozenset({"value", "unit"}), f"профиль.{key}")
    unit = _string(value, "unit")
    if unit != expected_unit:
        raise InputError(f"профиль.{key}: неизвестная единица {unit!r}")
    number = value.get("value")
    if isinstance(number, bool) or not isinstance(number, int | float):
        raise InputError(f"профиль.{key}: value должно быть числом")
    return Quantity(value=float(number), unit=unit)


def _reject_unknown(raw: Mapping[str, JsonValue], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise InputError(f"{label}: неизвестные поля {', '.join(repr(item) for item in unknown)}")


def _required(raw: Mapping[str, JsonValue], key: str) -> JsonValue:
    if key not in raw:
        raise InputError(f"профиль: отсутствует поле {key!r}")
    return raw[key]


def _string(raw: Mapping[str, JsonValue], key: str) -> str:
    value = _required(raw, key)
    if not isinstance(value, str):
        raise InputError(f"профиль: поле {key!r} должно быть строкой")
    return value


def _label(raw: Mapping[str, JsonValue], key: str) -> str:
    return _label_item(_required(raw, key))


def _label_item(value: JsonValue) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or not value.isprintable():
        raise InputError("профиль: текстовое значение должно быть непустым и печатным")
    return value


def _integer(raw: Mapping[str, JsonValue], key: str) -> int:
    value = _required(raw, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"профиль: поле {key!r} должно быть целым")
    return value


def _mapping(raw: Mapping[str, JsonValue], key: str) -> dict[str, JsonValue]:
    value = _required(raw, key)
    if not isinstance(value, dict):
        raise InputError(f"профиль: поле {key!r} должно быть object")
    return value


def _list(raw: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    value = _required(raw, key)
    if not isinstance(value, list):
        raise InputError(f"профиль: поле {key!r} должно быть array")
    return value


def _kind(value: str) -> ProfileKind:
    try:
        return ProfileKind(value)
    except ValueError as error:
        raise InputError(f"профиль: неизвестный kind {value!r}") from error


def _damper(value: str) -> DamperState:
    try:
        return DamperState(value)
    except ValueError as error:
        raise InputError(f"профиль: неизвестное состояние демпфера {value!r}") from error
