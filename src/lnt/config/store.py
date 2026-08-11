"""Атомарное чтение, запись и восстановление конфигурации LNT."""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import override

from lnt._manifest_json import decode_json_object
from lnt.config.model import Config, config_from_mapping, config_to_payload
from lnt.errors import InputError


class ConfigLoadStatus(StrEnum):
    """Машиночитаемый результат чтения конфигурации."""

    LOADED = "loaded"
    DEFAULTS_MISSING = "defaults_missing"
    RECOVERED_CORRUPT = "recovered_corrupt"


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfigLoadResult:
    """Конфигурация вместе со статусом чтения или восстановления."""

    config: Config
    status: ConfigLoadStatus
    recovered_path: Path | None


@dataclass(frozen=True, slots=True)
class ConfigWriteError(InputError):
    """Ожидаемая ошибка атомарной записи конфигурации."""

    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        """Возвращает локализованное описание ошибки записи."""
        return f"не удалось записать конфигурацию {self.path}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ConfigRecoveryError(InputError):
    """Ошибка сохранения повреждённого файла перед восстановлением."""

    path: Path
    reason: str

    @override
    def __str__(self) -> str:
        """Возвращает локализованное описание ошибки восстановления."""
        return f"не удалось сохранить повреждённую конфигурацию {self.path}: {self.reason}"


def load_config(path: Path, *, default_session_root: Path) -> ConfigLoadResult:
    """Читает config.json; повреждённый файл откладывает и возвращает defaults."""
    if not path.exists():
        return ConfigLoadResult(
            config=Config(session_root=default_session_root),
            status=ConfigLoadStatus.DEFAULTS_MISSING,
            recovered_path=None,
        )
    try:
        text = path.read_text(encoding="utf-8")
        config = config_from_mapping(decode_json_object(text))
    except (InputError, UnicodeDecodeError):
        recovered_path = path.with_name(
            f"{path.name}.corrupt-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}",
        )
        try:
            os.replace(path, recovered_path)  # noqa: PTH105 - единый патчируемый атомарный seam
        except OSError as error:
            raise ConfigRecoveryError(path=path, reason=str(error)) from error
        return ConfigLoadResult(
            config=Config(session_root=default_session_root),
            status=ConfigLoadStatus.RECOVERED_CORRUPT,
            recovered_path=recovered_path,
        )
    except OSError as error:
        raise InputError(f"не удалось прочитать конфигурацию {path}: {error}") from error
    return ConfigLoadResult(
        config=config,
        status=ConfigLoadStatus.LOADED,
        recovered_path=None,
    )


def write_config(path: Path, config: Config) -> None:
    """Атомарно заменяет config.json, не повреждая предыдущую версию."""
    temporary = path.with_name(f".{path.name}.partial-{uuid.uuid4().hex[:8]}")
    payload = (
        json.dumps(
            config_to_payload(config),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)  # noqa: PTH105 - единый патчируемый атомарный seam
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ConfigWriteError(path=path, reason=str(error)) from error
