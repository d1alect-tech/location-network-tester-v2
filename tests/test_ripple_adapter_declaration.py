"""Домен декларации адаптера ripple: write-once ключи контекста + приведение.

Истина контрактная: ``declaration_fields`` строит поля USER/COLLECTED,
``declaration_from_snapshot`` восстанавливает декларацию (нет ключей —
None, брак — InputError), ``to_spec`` валидируется только
``AdapterSpec.__post_init__`` (H8: без дублирующих проверок).
"""

from __future__ import annotations

import pytest

from lnt.context.model import (
    CollectionStatus,
    ContextField,
    ContextSnapshot,
    FieldKind,
    FieldSource,
)
from lnt.errors import InputError
from lnt.ripple.adapter import AdapterSpec
from lnt.ripple.adapter_declaration import (
    ADAPTER_CONTEXT_KEYS,
    AdapterDeclaration,
    declaration_fields,
    declaration_from_snapshot,
)
from lnt.types import ComponentValuesBasis

_CAPTURED_AT = "2026-10-23T08:00:00.000Z"
_SESSION_ID = "session-A"


def _declaration(
    *,
    cap_nf: float = 100.0,
    series_r_ohm: float = 470.0,
    preconnected: bool = True,
    component_values_basis: ComponentValuesBasis = ComponentValuesBasis.OPERATOR_MEASURED,
) -> AdapterDeclaration:
    return AdapterDeclaration(
        cap_nf=cap_nf,
        series_r_ohm=series_r_ohm,
        preconnected=preconnected,
        component_values_basis=component_values_basis,
    )


def _snapshot(fields: dict[str, ContextField]) -> ContextSnapshot:
    return ContextSnapshot(
        schema_version=1,
        session_id=_SESSION_ID,
        revision=1,
        fields=fields,
        tags=(),
        notes=None,
        profile_snapshots=(),
    )


def _valid_snapshot(declaration: AdapterDeclaration) -> ContextSnapshot:
    return _snapshot(declaration_fields(declaration, _CAPTURED_AT))


def _alien_field(
    kind: FieldKind,
    value: str | float | bool,
    status: CollectionStatus = CollectionStatus.COLLECTED,
) -> ContextField:
    return ContextField(
        kind=kind,
        value=value,
        unit=None,
        uncertainty=None,
        source=FieldSource.USER,
        collection_status=status,
        collection_reason=None if status is CollectionStatus.COLLECTED else "не собран",
        captured_at=_CAPTURED_AT,
    )


def test_adapter_context_keys_are_the_exact_write_once_set() -> None:
    expected = {
        "adapter.cap_nf",
        "adapter.series_r_ohm",
        "adapter.preconnected",
        "adapter.component_values_basis",
    }

    assert isinstance(ADAPTER_CONTEXT_KEYS, frozenset)
    assert expected == ADAPTER_CONTEXT_KEYS


def test_declaration_fields_carry_typed_user_collected_shape() -> None:
    fields = declaration_fields(_declaration(), _CAPTURED_AT)

    assert set(fields) == ADAPTER_CONTEXT_KEYS
    for field in fields.values():
        assert field.source is FieldSource.USER
        assert field.collection_status is CollectionStatus.COLLECTED
        assert field.collection_reason is None
        assert field.uncertainty is None
        assert field.captured_at == _CAPTURED_AT
    assert fields["adapter.cap_nf"].kind is FieldKind.NUMBER
    assert fields["adapter.cap_nf"].value == 100.0
    assert fields["adapter.cap_nf"].unit == "nF"
    assert fields["adapter.series_r_ohm"].kind is FieldKind.NUMBER
    assert fields["adapter.series_r_ohm"].value == 470.0
    assert fields["adapter.series_r_ohm"].unit == "ohm"
    assert fields["adapter.preconnected"].kind is FieldKind.BOOLEAN
    assert fields["adapter.preconnected"].value is True
    assert fields["adapter.preconnected"].unit is None
    assert fields["adapter.component_values_basis"].kind is FieldKind.ENUM
    assert fields["adapter.component_values_basis"].value == "operator_measured"
    assert fields["adapter.component_values_basis"].unit is None


@pytest.mark.parametrize(
    ("basis", "preconnected"),
    [
        (ComponentValuesBasis.NOMINAL, True),
        (ComponentValuesBasis.NOMINAL, False),
        (ComponentValuesBasis.OPERATOR_MEASURED, True),
        (ComponentValuesBasis.OPERATOR_MEASURED, False),
    ],
)
def test_declaration_round_trip_fields_snapshot_declaration_spec(
    basis: ComponentValuesBasis,
    preconnected: bool,
) -> None:
    declaration = _declaration(preconnected=preconnected, component_values_basis=basis)

    snapshot = _valid_snapshot(declaration)
    restored = declaration_from_snapshot(snapshot)
    spec = restored.to_spec() if restored is not None else None

    assert restored == declaration
    assert spec == AdapterSpec(
        cap_nf=declaration.cap_nf,
        series_r_ohm=declaration.series_r_ohm,
        probe_multiplier=1,
        component_values_basis=basis,
    )
    assert spec is not None
    assert spec.rail_nominal_v is None


def test_declaration_from_snapshot_without_adapter_keys_returns_none() -> None:
    unrelated = _snapshot({"session.label": _alien_field(FieldKind.STRING, "лаборатория")})
    empty = _snapshot({})

    assert declaration_from_snapshot(unrelated) is None
    assert declaration_from_snapshot(empty) is None


@pytest.mark.parametrize("missing", sorted(ADAPTER_CONTEXT_KEYS))
def test_fail_closed_partial_key_presence_is_rejected(missing: str) -> None:
    fields = declaration_fields(_declaration(), _CAPTURED_AT)
    del fields[missing]

    with pytest.raises(InputError, match="неполный набор ключей"):
        declaration_from_snapshot(_snapshot(fields))


@pytest.mark.parametrize(
    ("key", "kind", "value"),
    [
        ("adapter.cap_nf", FieldKind.STRING, "100"),
        ("adapter.cap_nf", FieldKind.NUMBER, "100"),
        ("adapter.series_r_ohm", FieldKind.BOOLEAN, False),
        ("adapter.preconnected", FieldKind.ENUM, "true"),
        ("adapter.component_values_basis", FieldKind.NUMBER, 1.0),
    ],
)
def test_fail_closed_wrong_kind_is_rejected(key: str, kind: FieldKind, value: str | float) -> None:
    fields = declaration_fields(_declaration(), _CAPTURED_AT)
    fields[key] = _alien_field(kind, value)

    with pytest.raises(InputError, match="должен быть"):
        declaration_from_snapshot(_snapshot(fields))


@pytest.mark.parametrize("status", [CollectionStatus.UNAVAILABLE, CollectionStatus.NOT_COLLECTED])
@pytest.mark.parametrize("key", ["adapter.cap_nf", "adapter.component_values_basis"])
def test_fail_closed_uncollected_status_is_rejected(key: str, status: CollectionStatus) -> None:
    fields = declaration_fields(_declaration(), _CAPTURED_AT)
    kind = fields[key].kind
    fields[key] = _alien_field(kind, "", status)

    with pytest.raises(InputError, match="не собран"):
        declaration_from_snapshot(_snapshot(fields))


def test_fail_closed_unknown_enum_value_is_rejected() -> None:
    fields = declaration_fields(_declaration(), _CAPTURED_AT)
    fields["adapter.component_values_basis"] = _alien_field(FieldKind.ENUM, "bogus")

    with pytest.raises(InputError, match="nominal или operator_measured"):
        declaration_from_snapshot(_snapshot(fields))


@pytest.mark.parametrize(
    ("cap_nf", "series_r_ohm"),
    [(-5.0, 470.0), (100.0, -1.0), (float("nan"), 470.0)],
)
def test_fail_closed_nonphysical_values_rejected_only_by_adapter_spec(
    cap_nf: float, series_r_ohm: float
) -> None:
    """Читатель не дублирует физику: отсеивает только сам ``AdapterSpec``."""
    declaration = _declaration(cap_nf=cap_nf, series_r_ohm=series_r_ohm)
    snapshot = _valid_snapshot(declaration)

    restored = declaration_from_snapshot(snapshot)

    assert restored is not None
    assert restored == declaration
    with pytest.raises(InputError):
        restored.to_spec()
