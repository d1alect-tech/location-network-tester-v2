"""Публичный API типизированной конфигурации LNT."""

from lnt.config.model import CONFIG_SCHEMA_VERSION, Config
from lnt.config.store import (
    ConfigLoadResult,
    ConfigLoadStatus,
    ConfigRecoveryError,
    ConfigWriteError,
    load_config,
    write_config,
)

__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "Config",
    "ConfigLoadResult",
    "ConfigLoadStatus",
    "ConfigRecoveryError",
    "ConfigWriteError",
    "load_config",
    "write_config",
]
