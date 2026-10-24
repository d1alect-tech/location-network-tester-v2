"""Домен декларации адаптера ripple: write-once ключи контекста сессии.

Декларация — операторский ввод (``source=USER``, ``COLLECTED``). Приведение
к ``AdapterSpec`` валидируется только ``AdapterSpec.__post_init__`` (H8);
этот модуль физических проверок не дублирует. Частичное присутствие ключей,
неверный ``kind`` или не-COLLECTED статус — fail closed одним ``InputError``.
``preconnected`` остаётся bool: его отображение в SettlingDeclaration —
задача N6, не этого модуля.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from lnt.context.model import (
    CollectionStatus,
    ContextField,
    ContextSnapshot,
    FieldKind,
    FieldSource,
    FieldValue,
)
from lnt.errors import InputError
from lnt.ripple.adapter import AdapterSpec
from lnt.types import ComponentValuesBasis

__all__ = [
    "ADAPTER_CONTEXT_KEYS",
    "AdapterDeclaration",
    "declaration_fields",
    "declaration_from_snapshot",
]

_KEY_CAP_NF: Final = "adapter.cap_nf"
_KEY_SERIES_R_OHM: Final = "adapter.series_r_ohm"
_KEY_PRECONNECTED: Final = "adapter.preconnected"
_KEY_BASIS: Final = "adapter.component_values_basis"

ADAPTER_CONTEXT_KEYS: Final[frozenset[str]] = frozenset(
    (_KEY_CAP_NF, _KEY_SERIES_R_OHM, _KEY_PRECONNECTED, _KEY_BASIS)
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterDeclaration:
    """Операторская декларация адаптера, восстановимая из контекста."""

    cap_nf: float
    series_r_ohm: float
    preconnected: bool
    component_values_basis: ComponentValuesBasis

    def to_spec(self) -> AdapterSpec:
        """Приводит декларацию к номинальной модели x1 через единый валидатор."""
        return AdapterSpec(
            cap_nf=self.cap_nf,
            series_r_ohm=self.series_r_ohm,
            probe_multiplier=1,
            component_values_basis=self.component_values_basis,
        )


def declaration_fields(
    declaration: AdapterDeclaration, captured_at: str
) -> dict[str, ContextField]:
    """Строит write-once поля контекста: все USER/COLLECTED, единицы у number."""
    return {
        _KEY_CAP_NF: _field(FieldKind.NUMBER, declaration.cap_nf, "nF", captured_at),
        _KEY_SERIES_R_OHM: _field(FieldKind.NUMBER, declaration.series_r_ohm, "ohm", captured_at),
        _KEY_PRECONNECTED: _field(FieldKind.BOOLEAN, declaration.preconnected, None, captured_at),
        _KEY_BASIS: _field(
            FieldKind.ENUM, declaration.component_values_basis.value, None, captured_at
        ),
    }


def declaration_from_snapshot(snapshot: ContextSnapshot) -> AdapterDeclaration | None:
    """Восстанавливает декларацию: нет ключей — None, брак — InputError."""
    present = ADAPTER_CONTEXT_KEYS & snapshot.fields.keys()
    if not present:
        return None
    missing = ADAPTER_CONTEXT_KEYS - present
    if missing:
        keys = ", ".join(sorted(missing))
        raise InputError(f"ripple: adapter declaration: неполный набор ключей: {keys}")
    return AdapterDeclaration(
        cap_nf=_number(snapshot, _KEY_CAP_NF),
        series_r_ohm=_number(snapshot, _KEY_SERIES_R_OHM),
        preconnected=_boolean(snapshot, _KEY_PRECONNECTED),
        component_values_basis=_basis(snapshot),
    )


def _field(kind: FieldKind, value: FieldValue, unit: str | None, captured_at: str) -> ContextField:
    return ContextField(
        kind=kind,
        value=value,
        unit=unit,
        uncertainty=None,
        source=FieldSource.USER,
        collection_status=CollectionStatus.COLLECTED,
        collection_reason=None,
        captured_at=captured_at,
    )


def _collected(snapshot: ContextSnapshot, key: str) -> ContextField:
    field = snapshot.fields[key]
    if field.collection_status is not CollectionStatus.COLLECTED:
        status = field.collection_status.value
        raise InputError(f"ripple: adapter declaration: {key} не собран ({status})")
    return field


def _number(snapshot: ContextSnapshot, key: str) -> float:
    field = _collected(snapshot, key)
    value = field.value
    if (
        field.kind is not FieldKind.NUMBER
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise InputError(f"ripple: adapter declaration: {key} должен быть number")
    return float(value)


def _boolean(snapshot: ContextSnapshot, key: str) -> bool:
    field = _collected(snapshot, key)
    if field.kind is not FieldKind.BOOLEAN or not isinstance(field.value, bool):
        raise InputError(f"ripple: adapter declaration: {key} должен быть boolean")
    return field.value


def _basis(snapshot: ContextSnapshot) -> ComponentValuesBasis:
    field = _collected(snapshot, _KEY_BASIS)
    if field.kind is not FieldKind.ENUM or not isinstance(field.value, str):
        raise InputError(f"ripple: adapter declaration: {_KEY_BASIS} должен быть enum")
    try:
        return ComponentValuesBasis(field.value)
    except ValueError:
        message = "ripple: adapter declaration: component_values_basis "
        raise InputError(message + "должен быть nominal или operator_measured") from None
