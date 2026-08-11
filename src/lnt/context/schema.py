"""Строгая доменная модель ``context.json`` schema 1."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Final

from lnt.context.json_codec import JsonValue, decode_object, encode_pretty
from lnt.context.model import (
    CollectionStatus,
    ContextField,
    ContextSnapshot,
    FieldKind,
    FieldSource,
    FieldValue,
    ProfileSnapshot,
)
from lnt.context.parsing import (
    as_mapping,
    enum_value,
    integer,
    json_list,
    mapping,
    optional_number,
    optional_string,
    reject_unknown,
    required,
    string,
    string_item,
)
from lnt.errors import InputError

if TYPE_CHECKING:
    from collections.abc import Mapping

_TIMESTAMP: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$")
_FIELD_KEY: Final = re.compile(r"^[a-z][a-z0-9_.-]*$")
_TOP_FIELDS: Final = frozenset(
    {"schema_version", "session_id", "revision", "fields", "tags", "notes", "profile_snapshots"}
)
_FIELD_FIELDS: Final = frozenset(
    {
        "kind",
        "value",
        "unit",
        "uncertainty",
        "source",
        "collection_status",
        "collection_reason",
        "captured_at",
    }
)
_PROFILE_FIELDS: Final = frozenset({"profile_id", "revision", "captured_at", "fields"})


def context_to_mapping(snapshot: ContextSnapshot) -> dict[str, JsonValue]:
    """Проверяет и переводит snapshot в JSON-mapping schema 1."""
    _validate_snapshot(snapshot)
    return {
        "schema_version": snapshot.schema_version,
        "session_id": snapshot.session_id,
        "revision": snapshot.revision,
        "fields": {key: _field_to_mapping(value) for key, value in snapshot.fields.items()},
        "tags": list(snapshot.tags),
        "notes": snapshot.notes,
        "profile_snapshots": [
            {
                "profile_id": profile.profile_id,
                "revision": profile.revision,
                "captured_at": profile.captured_at,
                "fields": {key: _field_to_mapping(value) for key, value in profile.fields.items()},
            }
            for profile in snapshot.profile_snapshots
        ],
    }


def context_to_json(snapshot: ContextSnapshot) -> str:
    """Сериализует snapshot в строгий context.json."""
    return encode_pretty(context_to_mapping(snapshot), "context.json")


def context_from_json(text: str) -> ContextSnapshot:
    """Строго разбирает context.json."""
    return context_from_mapping(decode_object(text, "context.json"))


def context_from_mapping(raw: Mapping[str, JsonValue]) -> ContextSnapshot:
    """Строго разбирает JSON-mapping schema 1."""
    reject_unknown(raw, _TOP_FIELDS, "context.json")
    version = integer(raw, "schema_version", "context.json")
    if version != 1:
        raise InputError(f"context.json: неподдерживаемая schema_version: {version}")
    fields = _field_map(mapping(raw, "fields", "context.json"), "context.json.fields")
    profiles_raw = json_list(raw, "profile_snapshots", "context.json")
    snapshot = ContextSnapshot(
        schema_version=version,
        session_id=string(raw, "session_id", "context.json"),
        revision=integer(raw, "revision", "context.json"),
        fields=fields,
        tags=tuple(
            string_item(item, "context.json.tags")
            for item in json_list(raw, "tags", "context.json")
        ),
        notes=optional_string(raw, "notes", "context.json"),
        profile_snapshots=tuple(_parse_profile(item) for item in profiles_raw),
    )
    _validate_snapshot(snapshot)
    return snapshot


def _field_to_mapping(field: ContextField) -> dict[str, JsonValue]:
    _validate_field(field)
    return {
        "kind": field.kind.value,
        "value": field.value,
        "unit": field.unit,
        "uncertainty": field.uncertainty,
        "source": field.source.value,
        "collection_status": field.collection_status.value,
        "collection_reason": field.collection_reason,
        "captured_at": field.captured_at,
    }


def _parse_field(raw: Mapping[str, JsonValue], label: str) -> ContextField:
    reject_unknown(raw, _FIELD_FIELDS, label)
    kind = enum_value(raw, "kind", FieldKind, label)
    value = _field_value(raw, kind, label)
    uncertainty = optional_number(raw, "uncertainty", label)
    field = ContextField(
        kind=kind,
        value=value,
        unit=optional_string(raw, "unit", label),
        uncertainty=uncertainty,
        source=enum_value(raw, "source", FieldSource, label),
        collection_status=enum_value(raw, "collection_status", CollectionStatus, label),
        collection_reason=optional_string(raw, "collection_reason", label),
        captured_at=string(raw, "captured_at", label),
    )
    _validate_field(field)
    return field


def _parse_profile(value: JsonValue) -> ProfileSnapshot:
    if not isinstance(value, dict):
        raise InputError("context.json.profile_snapshots: ожидается object")
    reject_unknown(value, _PROFILE_FIELDS, "profile snapshot")
    return ProfileSnapshot(
        profile_id=string(value, "profile_id", "profile snapshot"),
        revision=integer(value, "revision", "profile snapshot"),
        captured_at=string(value, "captured_at", "profile snapshot"),
        fields=_field_map(mapping(value, "fields", "profile snapshot"), "profile snapshot.fields"),
    )


def _validate_snapshot(snapshot: ContextSnapshot) -> None:
    if snapshot.schema_version != 1 or snapshot.revision < 0:
        raise InputError("context.json: неверная версия или revision")
    _validate_id(snapshot.session_id, "session_id")
    for key, field in snapshot.fields.items():
        if _FIELD_KEY.fullmatch(key) is None:
            raise InputError(f"context.json: небезопасный ключ поля {key!r}")
        _validate_field(field)
    for profile in snapshot.profile_snapshots:
        _validate_id(profile.profile_id, "profile_id")
        if profile.revision < 0 or _TIMESTAMP.fullmatch(profile.captured_at) is None:
            raise InputError("context.json: неверный profile snapshot")


def _validate_field(field: ContextField) -> None:
    if _TIMESTAMP.fullmatch(field.captured_at) is None:
        raise InputError("context.json: captured_at должен быть RFC 3339 UTC")
    match field.kind:
        case FieldKind.NUMBER:
            _validate_number_value(field.value)
        case FieldKind.BOOLEAN:
            if not isinstance(field.value, bool):
                raise InputError("context.json: boolean должен быть bool")
        case FieldKind.TIMESTAMP:
            if not isinstance(field.value, str) or _TIMESTAMP.fullmatch(field.value) is None:
                raise InputError("context.json: timestamp должен быть RFC 3339 UTC")
        case FieldKind.STRING | FieldKind.ENUM:
            if not isinstance(field.value, str):
                raise InputError("context.json: строковое поле должно быть строкой")
    _validate_uncertainty(field.uncertainty)
    _validate_metadata(field)


def _validate_number_value(value: FieldValue) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise InputError("context.json: number должен быть конечным числом")


def _validate_uncertainty(value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or value < 0):
        raise InputError("context.json: uncertainty должна быть конечной и неотрицательной")


def _validate_metadata(field: ContextField) -> None:
    if field.kind is not FieldKind.NUMBER and (
        field.unit is not None or field.uncertainty is not None
    ):
        raise InputError("context.json: unit/uncertainty допустимы только для number")
    if (field.collection_status is CollectionStatus.COLLECTED) == (
        field.collection_reason is not None
    ):
        raise InputError(
            "context.json: collection_reason требуется только для неполученного значения"
        )


def _field_map(raw: Mapping[str, JsonValue], label: str) -> dict[str, ContextField]:
    return {
        key: _parse_field(as_mapping(value, f"{label}.{key}"), f"{label}.{key}")
        for key, value in raw.items()
    }


def _field_value(raw: Mapping[str, JsonValue], kind: FieldKind, label: str) -> FieldValue:
    value = required(raw, "value", label)
    numeric_integer = isinstance(value, int) and not isinstance(value, bool)
    if (isinstance(value, (dict, list)) or value is None or numeric_integer) and (
        kind is not FieldKind.NUMBER
    ):
        raise InputError(f"{label}: value не соответствует kind")
    if not isinstance(value, str | int | float | bool):
        raise InputError(f"{label}: неверный value")
    return float(value) if kind is FieldKind.NUMBER and not isinstance(value, bool) else value


def _validate_id(value: str, label: str) -> None:
    if not value or not value.isascii() or not value.isprintable():
        raise InputError(f"context.json: небезопасный {label}")
