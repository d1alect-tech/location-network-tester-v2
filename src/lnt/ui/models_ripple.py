"""Строгая граница схемы сайдкара ripple.json v1 для HTTP-раздачи.

GET-маршрут (план todo 5 + поправки исполнения №6) никогда не пересчитывает:
артефакт проверяется по форме замороженной v1 — строгий JSON-кодек, набор
ключей, идентичность алгоритма, SHA-256 входов — и лишь затем отдаётся.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from lnt.context.json_codec import JsonValue, decode_object
from lnt.errors import InputError
from lnt.ui.models_ripple_primitives import RippleSchemaError
from lnt.ui.models_ripple_schema import validate_ripple_payload

__all__ = [
    "ALGORITHM_ID_RIPPLE",
    "CHANNEL_RIPPLE",
    "RIPPLE_SCHEMA_VERSION",
    "RippleArtifact",
    "RippleBaselineIdentity",
    "RippleSchemaError",
    "parse_ripple_artifact",
]

RIPPLE_SCHEMA_VERSION: Final = 1
ALGORITHM_ID_RIPPLE: Final = "ripple_observed_v1"
CHANNEL_RIPPLE: Final = "ch1"
_SHA256_HEX: Final = re.compile(r"[0-9a-f]{64}")
_TOP_LEVEL_KEYS: Final = (
    "schema_version",
    "algorithm",
    "options",
    "session",
    "provenance",
    "adapter",
    "selection",
    "qc",
    "time_domain",
    "intervals",
    "spectrum",
    "bands",
    "baseline",
)
_OBJECT_KEYS: Final = (
    "options",
    "provenance",
    "adapter",
    "selection",
    "qc",
    "time_domain",
    "spectrum",
)
_LIST_KEYS: Final = ("intervals", "bands")


@dataclass(frozen=True, slots=True)
class RippleBaselineIdentity:
    """Идентичность фона для повторной сверки хэшей на GET."""

    session_id: str
    session_dir: str | None
    manifest_sha256: str
    ch1_sha256: str


@dataclass(frozen=True, slots=True)
class RippleArtifact:
    """Проверенный сайдкар: payload v1 и хэши входов для сверки свежести."""

    payload: dict[str, JsonValue]
    manifest_sha256: str
    ch1_sha256: str
    baseline: RippleBaselineIdentity | None


def parse_ripple_artifact(text: str) -> RippleArtifact:
    """Разбирает сохранённый ripple.json и строго проверяет схему v1."""
    try:
        payload = decode_object(text, "ripple.json")
    except InputError as error:
        raise RippleSchemaError("corrupt", str(error)) from error
    _check_top_level(payload)
    session = _mapping(payload["session"], "session")
    if session.get("channel") != CHANNEL_RIPPLE:
        raise RippleSchemaError(
            "schema_incompatible", "ripple.json: session.channel должен быть ch1"
        )
    baseline_session = validate_ripple_payload(payload)
    return RippleArtifact(
        payload=payload,
        manifest_sha256=_sha256(session, "manifest_sha256"),
        ch1_sha256=_sha256(session, "ch1_sha256"),
        baseline=None if baseline_session is None else _baseline_identity(baseline_session),
    )


def _baseline_identity(session: dict[str, object]) -> RippleBaselineIdentity:
    """Собирает идентичность фона из уже проверенного блока session."""
    return RippleBaselineIdentity(
        session_id=str(session["session_id"]),
        session_dir=(None if session.get("session_dir") is None else str(session["session_dir"])),
        manifest_sha256=str(session["manifest_sha256"]),
        ch1_sha256=str(session["ch1_sha256"]),
    )


def _check_top_level(payload: dict[str, JsonValue]) -> None:
    """Набор ключей и типы контейнеров замороженной v1 без дрейфа."""
    if frozenset(payload) != frozenset(_TOP_LEVEL_KEYS):
        raise RippleSchemaError(
            "schema_incompatible",
            f"ripple.json: набор ключей v1 нарушен: {sorted(frozenset(payload))}",
        )
    version = payload["schema_version"]
    if type(version) is not int or version != RIPPLE_SCHEMA_VERSION:
        raise RippleSchemaError("schema_incompatible", "ripple.json: schema_version должен быть 1")
    algorithm = _mapping(payload["algorithm"], "algorithm")
    if algorithm.get("id") != ALGORITHM_ID_RIPPLE:
        raise RippleSchemaError(
            "schema_incompatible",
            f"ripple.json: algorithm.id должен быть {ALGORITHM_ID_RIPPLE}",
        )
    for key in _OBJECT_KEYS:
        _mapping(payload[key], key)
    for key in _LIST_KEYS:
        value = payload[key]
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise RippleSchemaError(
                "schema_incompatible", f"ripple.json: {key} должен быть списком объектов"
            )
    baseline = payload["baseline"]
    if baseline is not None and not isinstance(baseline, dict):
        raise RippleSchemaError(
            "schema_incompatible", "ripple.json: baseline должен быть объектом или null"
        )


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    """Сужает значение до JSON-объекта или отказывает по схеме."""
    if not isinstance(value, dict):
        raise RippleSchemaError("schema_incompatible", f"ripple.json: {label} должен быть объектом")
    return value


def _sha256(session: dict[str, JsonValue], key: str) -> str:
    """Требует канонический lowercase SHA-256 из блока session."""
    value = session.get(key)
    if not isinstance(value, str) or _SHA256_HEX.fullmatch(value) is None:
        raise RippleSchemaError(
            "schema_incompatible", f"ripple.json: session.{key} должен быть SHA-256"
        )
    return value
