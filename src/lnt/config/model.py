"""Типизированная схема пользовательской конфигурации LNT."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, TypedDict

from lnt._manifest_json import JsonValue
from lnt.errors import InputError

CONFIG_SCHEMA_VERSION: Final = 1
DEFAULT_LOG_MAX_BYTES: Final = 1_048_576
DEFAULT_LOG_BACKUP_COUNT: Final = 5


class LoggingPayload(TypedDict):
    """JSON-представление секции журналирования."""

    max_bytes: int
    backup_count: int
    redact_private_metadata: bool


class ConfigPayload(TypedDict):
    """JSON-представление конфигурации schema v1."""

    schema_version: int
    session_root: str
    logging: LoggingPayload


@dataclass(frozen=True, slots=True, kw_only=True)
class LoggingSettings:
    """Настройки локального структурного журнала (ротация и редакция)."""

    max_bytes: int = DEFAULT_LOG_MAX_BYTES
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT
    redact_private_metadata: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    """Настройки LNT, безопасные для использования внутри приложения."""

    session_root: Path
    logging: LoggingSettings = field(default_factory=LoggingSettings)


def config_to_payload(config: Config) -> ConfigPayload:
    """Преобразует типизированную конфигурацию в JSON-представление."""
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "session_root": str(config.session_root),
        "logging": {
            "max_bytes": config.logging.max_bytes,
            "backup_count": config.logging.backup_count,
            "redact_private_metadata": config.logging.redact_private_metadata,
        },
    }


def config_from_mapping(value: dict[str, JsonValue]) -> Config:
    """Строго разбирает JSON-object конфигурации schema v1."""
    required = {"schema_version", "session_root"}
    optional = {"logging"}
    actual = set(value)
    if not actual <= required | optional or not required <= actual:
        missing = sorted(required - actual)
        unknown = sorted(actual - required - optional)
        raise InputError(f"config: неверный набор полей; отсутствуют={missing}, лишние={unknown}")

    schema_version = value["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise InputError("config: поле 'schema_version' должно быть целым числом")
    if schema_version != CONFIG_SCHEMA_VERSION:
        raise InputError(f"config: версия схемы {schema_version} не поддерживается")

    session_root = value["session_root"]
    if not isinstance(session_root, str) or not session_root.strip():
        raise InputError("config: поле 'session_root' должно быть непустой строкой")
    logging_section = value.get("logging")
    settings = (
        _logging_from_mapping(logging_section) if logging_section is not None else LoggingSettings()
    )
    return Config(session_root=Path(session_root), logging=settings)


def _logging_from_mapping(value: JsonValue) -> LoggingSettings:
    """Строго разбирает необязательную секцию 'logging' со значениями по умолчанию."""
    if not isinstance(value, dict):
        raise InputError("config: секция 'logging' должна быть JSON-object")
    allowed = {"max_bytes", "backup_count", "redact_private_metadata"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise InputError(f"config: лишние поля в 'logging': {unknown}")

    def positive_int(key: str, default: int) -> int:
        raw = value.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            raise InputError(f"config: поле 'logging.{key}' должно быть положительным целым")
        return raw

    redact = value.get("redact_private_metadata", True)
    if not isinstance(redact, bool):
        raise InputError("config: поле 'logging.redact_private_metadata' должно быть bool")
    return LoggingSettings(
        max_bytes=positive_int("max_bytes", DEFAULT_LOG_MAX_BYTES),
        backup_count=positive_int("backup_count", DEFAULT_LOG_BACKUP_COUNT),
        redact_private_metadata=redact,
    )
