"""Примитивы строгой схемы ``ripple.json`` v1: ошибка, перечисления, проверки.

Лист группы `models_ripple_schema`: числа обязаны быть конечными, целые —
целыми (bool не число), перечисления — из замороженных наборов. Любое
отклонение — ``RippleSchemaError("schema_incompatible")``.
"""

from __future__ import annotations

import math
import re
from typing import Final, NoReturn

SHA256_HEX: Final = re.compile(r"[0-9a-f]{64}")
SESSION_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
AVAILABILITY: Final = frozenset({"available", "unavailable"})
SOURCES: Final = frozenset({"device", "synthetic"})
VOLTAGE_PLANES: Final = frozenset(
    {
        "synthetic_mathematical_volts",
        "recorded_ch1_volts_observed_uncalibrated",
        "recorded_ch1_volts_observed_calibration_identity_unknown",
    }
)
OPERATOR_ATTACHMENTS: Final = frozenset({"preconnected_no_reconnection", "settling_unknown"})
CLIPPING: Final = frozenset(
    {
        "not_applicable_synthetic",
        "no_rail_hits",
        "rail_hits_present_localized",
        "rail_hits_present_unlocalizable",
        "clipping_unknown",
        "clip_census_inconsistent",
    }
)
CLIP_SCOPES: Final = frozenset(
    {"aggregate_saved_record_telemetry", "float32_endpoints_from_manifest_conversion"}
)
SETTLING_BASES: Final = frozenset({"capture_start_assuming_preconnected", "settling_unknown"})
CONTINUITY: Final = frozenset({"synthetic_exact", "host_contiguous_unverified"})
TRANSFER_STATUSES: Final = frozenset(
    {"nominal_transfer_declared", "unavailable_unknown_probe_topology"}
)
COMPONENT_BASES: Final = frozenset({"nominal", "operator_measured"})
REFERENCE_ASSUMPTIONS: Final = frozenset({"floating_host_unverified"})
SESSION_TYPES: Final = frozenset(
    {"measurement", "self_noise", "line_quality", "cm_dm", "cm_dm_calibration"}
)
CHANNEL_ROLES: Final = frozenset({"hf_probe", "lf_transformer"})
ATTACHMENT_BASES: Final = frozenset({None, "same_adapter_tip_shorted_to_return"})
SETUP_KINDS: Final = frozenset(
    {"floating_differential_rc_shunt_v1", "scope_input_terminated_v1", "transformer_line_probe_v1"}
)


class RippleSchemaError(ValueError):
    """Сайдкар не проходит схему v1; ``reason`` — стабильный код причины."""

    def __init__(self, reason: str, message: str) -> None:
        """Код причины схемы и человекочитаемое сообщение."""
        super().__init__(message)
        self.reason: str = reason


def fail(label: str) -> NoReturn:
    """Единый отказ вложенной схемы: причина всегда ``schema_incompatible``."""
    raise RippleSchemaError("schema_incompatible", f"ripple.json: {label}")


def obj(value: object, label: str) -> dict[str, object]:
    """Требует JSON-объект."""
    if not isinstance(value, dict):
        fail(f"{label} должен быть объектом")
    return value


def list_of(value: object, label: str) -> list[object]:
    """Требует JSON-массив."""
    if not isinstance(value, list):
        fail(f"{label} должен быть списком")
    return value


def text(value: object, label: str) -> str:
    """Требует непустую строку."""
    if not isinstance(value, str) or value == "":
        fail(f"{label} должен быть непустой строкой")
    return value


def number(value: object, label: str) -> float:
    """Требует конечное число (bool исключён)."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        fail(f"{label} должен быть конечным числом")
    return float(value)


def integer(value: object, label: str, *, minimum: int = 0) -> int:
    """Требует целое (bool исключён) не меньше границы."""
    if type(value) is not int or value < minimum:
        fail(f"{label} должен быть целым >= {minimum}")
    return value


def boolean(value: object, label: str) -> bool:
    """Требует bool."""
    if type(value) is not bool:
        fail(f"{label} должен быть bool")
    return value


def codes(value: object, label: str) -> list[str]:
    """Требует массив строковых кодов причин."""
    items = list_of(value, label)
    if any(not isinstance(item, str) for item in items):
        fail(f"{label} должен быть списком строк")
    return [item for item in items if isinstance(item, str)]


def enum(value: object, label: str, allowed: frozenset[str]) -> str:
    """Требует значение из замороженного набора."""
    if not isinstance(value, str) or value not in allowed:
        fail(f"{label} имеет недопустимое значение {value!r}")
    return value


def sha256(value: object, label: str) -> str:
    """Требует канонический lowercase SHA-256."""
    if not isinstance(value, str) or SHA256_HEX.fullmatch(value) is None:
        fail(f"{label} должен быть SHA-256")
    return value
