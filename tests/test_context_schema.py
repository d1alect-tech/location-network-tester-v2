from __future__ import annotations

import math

import pytest

from lnt.context.model import (
    CollectionStatus,
    ContextField,
    ContextSnapshot,
    FieldKind,
    FieldSource,
    ProfileSnapshot,
)
from lnt.context.schema import (
    context_from_json,
    context_to_json,
)
from lnt.errors import InputError


def _field(kind: FieldKind, value: str | float | bool) -> ContextField:
    return ContextField(
        kind=kind,
        value=value,
        unit="V" if kind is FieldKind.NUMBER else None,
        uncertainty=0.1 if kind is FieldKind.NUMBER else None,
        source=FieldSource.USER,
        collection_status=CollectionStatus.COLLECTED,
        collection_reason=None,
        captured_at="2026-08-11T10:00:00.000Z",
    )


def _snapshot() -> ContextSnapshot:
    fields = {
        "site.name": _field(FieldKind.STRING, "лаборатория"),
        "supply.voltage_v": _field(FieldKind.NUMBER, 229.5),
        "operator.present": _field(FieldKind.BOOLEAN, True),
        "weather.state": _field(FieldKind.ENUM, "dry"),
        "observed_at": _field(FieldKind.TIMESTAMP, "2026-08-11T09:59:00.000Z"),
    }
    return ContextSnapshot(
        schema_version=1,
        session_id="session-A",
        revision=3,
        fields=fields,
        tags=("baseline", "lab"),
        notes="Контрольный замер",
        profile_snapshots=(
            ProfileSnapshot(
                profile_id="lab-default",
                revision=2,
                captured_at="2026-08-11T09:58:00.000Z",
                fields={"site.name": fields["site.name"]},
            ),
        ),
    )


def test_context_round_trip_when_all_typed_fields_are_valid() -> None:
    given = _snapshot()

    encoded = context_to_json(given)
    actual = context_from_json(encoded)

    assert actual == given


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (FieldKind.STRING, "text"),
        (FieldKind.NUMBER, 12.25),
        (FieldKind.BOOLEAN, False),
        (FieldKind.ENUM, "choice-a"),
        (FieldKind.TIMESTAMP, "2026-08-11T10:00:00.123Z"),
    ],
)
def test_context_round_trip_preserves_each_field_kind(
    kind: FieldKind,
    value: str | float | bool,
) -> None:
    given = ContextSnapshot.empty("session-A").with_field("test.value", _field(kind, value))

    actual = context_from_json(context_to_json(given))

    assert actual.fields["test.value"] == given.fields["test.value"]


@pytest.mark.parametrize(
    "mutation",
    [
        '"unknown": 1,',
        '"revision": true,',
        '"schema_version": 2,',
    ],
)
def test_context_parser_rejects_unknown_wrong_or_unsupported_data(mutation: str) -> None:
    given = context_to_json(ContextSnapshot.empty("session-A"))
    if mutation.startswith('"unknown"'):
        malformed = given.replace("{", "{" + mutation, 1)
    elif mutation.startswith('"revision"'):
        malformed = given.replace('"revision": 0,', mutation, 1)
    else:
        malformed = given.replace('"schema_version": 1,', mutation, 1)

    with pytest.raises(InputError):
        context_from_json(malformed)


@pytest.mark.parametrize("number", [math.nan, math.inf, -math.inf])
def test_context_serializer_rejects_nonfinite_numbers(number: float) -> None:
    given = ContextSnapshot.empty("session-A").with_field(
        "bad.number",
        _field(FieldKind.NUMBER, number),
    )

    with pytest.raises(InputError):
        context_to_json(given)
