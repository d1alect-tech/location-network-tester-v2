"""Типизированная схема пользовательской конфигурации LNT."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict

from lnt._manifest_json import JsonValue
from lnt.errors import InputError

CONFIG_SCHEMA_VERSION: Final = 1


class ConfigPayload(TypedDict):
    """JSON-представление конфигурации schema v1."""

    schema_version: int
    session_root: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    """Настройки LNT, безопасные для использования внутри приложения."""

    session_root: Path


def config_to_payload(config: Config) -> ConfigPayload:
    """Преобразует типизированную конфигурацию в JSON-представление."""
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "session_root": str(config.session_root),
    }


def config_from_mapping(value: dict[str, JsonValue]) -> Config:
    """Строго разбирает JSON-object конфигурации schema v1."""
    expected = {"schema_version", "session_root"}
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise InputError(f"config: неверный набор полей; отсутствуют={missing}, лишние={unknown}")

    schema_version = value["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise InputError("config: поле 'schema_version' должно быть целым числом")
    if schema_version != CONFIG_SCHEMA_VERSION:
        raise InputError(f"config: версия схемы {schema_version} не поддерживается")

    session_root = value["session_root"]
    if not isinstance(session_root, str) or not session_root.strip():
        raise InputError("config: поле 'session_root' должно быть непустой строкой")
    return Config(session_root=Path(session_root))
