"""Строгая schema-v2 сериализация/разбор дискриминированных CH1 setup-моделей."""

from collections.abc import Mapping
from typing import Final

from lnt._manifest_json import JsonValue
from lnt.errors import InputError
from lnt.types import (
    Ch1Setup,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)

FLOATING_KIND: Final = "floating_differential_rc_shunt_v1"
TERMINATED_KIND: Final = "scope_input_terminated_v1"
FLOATING_FIELDS: Final = frozenset(
    {
        "kind",
        "resistance_ohm",
        "c1_f",
        "c2_f",
        "component_values_basis",
        "reference_assumption",
    },
)
TERMINATED_FIELDS: Final = frozenset({"kind", "termination_resistance_ohm"})
TRANSFORMER_KIND: Final = "transformer_line_probe_v1"
TRANSFORMER_FIELDS: Final = frozenset(
    {
        "kind",
        "nominal_primary_v",
        "nominal_secondary_v",
        "probe_multiplier",
    },
)


def parse_ch1_setup(value: Mapping[str, object]) -> Ch1Setup:
    """Разбирает единственный разрешённый дискриминированный CH1 setup."""
    kind = _req_str(value, "kind")
    if kind == FLOATING_KIND:
        _reject_unknown(value, FLOATING_FIELDS)
        return FloatingDifferentialRcShunt(
            resistance_ohm=_req_float(value, "resistance_ohm"),
            c1_f=_req_float(value, "c1_f"),
            c2_f=_req_float(value, "c2_f"),
            component_values_basis=_req_enum(value, "component_values_basis", ComponentValuesBasis),
            reference_assumption=_req_enum(value, "reference_assumption", ReferenceAssumption),
        )
    if kind == TERMINATED_KIND:
        _reject_unknown(value, TERMINATED_FIELDS)
        return ScopeInputTerminated(
            termination_resistance_ohm=_req_float(value, "termination_resistance_ohm"),
        )
    if kind == TRANSFORMER_KIND:
        _reject_unknown(value, TRANSFORMER_FIELDS)
        return TransformerLineProbe(
            nominal_primary_v=_req_float(value, "nominal_primary_v"),
            nominal_secondary_v=_req_float(value, "nominal_secondary_v"),
            probe_multiplier=_req_float(value, "probe_multiplier"),
        )
    raise InputError(f"ch1_setup: неизвестный kind {kind!r}")


def serialize_ch1_setup(setup: Ch1Setup) -> dict[str, JsonValue]:
    """Сериализует setup с явным дискриминатором без dataclass-эвристик."""
    match setup:
        case FloatingDifferentialRcShunt():
            return {
                "kind": FLOATING_KIND,
                "resistance_ohm": setup.resistance_ohm,
                "c1_f": setup.c1_f,
                "c2_f": setup.c2_f,
                "component_values_basis": setup.component_values_basis.value,
                "reference_assumption": setup.reference_assumption.value,
            }
        case ScopeInputTerminated():
            return {
                "kind": TERMINATED_KIND,
                "termination_resistance_ohm": setup.termination_resistance_ohm,
            }
        case TransformerLineProbe():
            return {
                "kind": TRANSFORMER_KIND,
                "nominal_primary_v": setup.nominal_primary_v,
                "nominal_secondary_v": setup.nominal_secondary_v,
                "probe_multiplier": setup.probe_multiplier,
            }


def validate_session_setup_pairing(session_type: SessionType, setup: Ch1Setup | None) -> None:
    """Отклоняет schema-v2 setup, противоречащий назначению CH1-сессии."""
    match session_type, setup:
        case SessionType.MEASUREMENT, FloatingDifferentialRcShunt():
            pass
        case SessionType.SELF_NOISE, ScopeInputTerminated():
            pass
        case SessionType.LINE_QUALITY, TransformerLineProbe():
            pass
        case _:
            raise InputError("manifest: schema v2 session_type не соответствует ch1_setup")


def model_kind(setup: Ch1Setup | None) -> str | None:
    """Возвращает стабильный kind для provenance-полей анализа."""
    match setup:
        case FloatingDifferentialRcShunt():
            return FLOATING_KIND
        case ScopeInputTerminated():
            return TERMINATED_KIND
        case TransformerLineProbe():
            return TRANSFORMER_KIND
        case None:
            return None


def _reject_unknown(value: Mapping[str, object], allowed: frozenset[str]) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise InputError(f"ch1_setup: неизвестные поля {', '.join(repr(name) for name in unknown)}")


def _req(value: Mapping[str, object], key: str) -> object:
    if key not in value:
        raise InputError(f"ch1_setup: отсутствует поле {key!r}")
    return value[key]


def _req_str(value: Mapping[str, object], key: str) -> str:
    item = _req(value, key)
    if not isinstance(item, str):
        raise InputError(f"ch1_setup: поле {key!r} должно быть строкой")
    return item


def _req_float(value: Mapping[str, object], key: str) -> float:
    item = _req(value, key)
    if isinstance(item, bool) or not isinstance(item, int | float):
        raise InputError(f"ch1_setup: поле {key!r} должно быть числом")
    return float(item)


def _req_enum[E: ComponentValuesBasis | ReferenceAssumption](
    value: Mapping[str, object],
    key: str,
    enum_type: type[E],
) -> E:
    raw = _req_str(value, key)
    try:
        return enum_type(raw)
    except ValueError as error:
        raise InputError(f"ch1_setup: недопустимое значение поля {key!r}: {raw!r}") from error
