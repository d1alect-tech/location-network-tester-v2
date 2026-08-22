"""Структурированные локальные журналы LNT: JSON-lines, ротация, корреляция, редакция.

Приватность по умолчанию: сырые отсчёты захвата, сетевые/пользовательские
идентичности и пользовательские метаданные (алиасы локаций, метки, заметки)
никогда не попадают в журнал. Каждое правило редакции несёт машиночитаемую
причину; правило приватных метаданных можно ослабить только явной настройкой
``LoggingSettings.redact_private_metadata = False``.
"""

from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Final, final, override

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from lnt.config.model import LoggingSettings

LOG_FILENAME: Final = "lnt.log.jsonl"
LOG_LOGGER_NAME: Final = "lnt"
_NUMERIC_ARRAY_LIMIT: Final = 16
_MAX_REDACTION_DEPTH: Final = 8

job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("lnt_job_id", default=None)
session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lnt_session_id",
    default=None,
)
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lnt_request_id",
    default=None,
)


@contextmanager
def correlation_scope(
    *,
    job_id: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
) -> Generator[None]:
    """Привязывает корреляционные ID задачи/сессии/запроса к текущему контексту."""
    job_token = job_id_var.set(job_id)
    session_token = session_id_var.set(session_id)
    request_token = request_id_var.set(request_id)
    try:
        yield
    finally:
        job_id_var.reset(job_token)
        session_id_var.reset(session_token)
        request_id_var.reset(request_token)


class RedactionRule(StrEnum):
    """Машиночитаемые причины редакции полей журнала."""

    RAW_SAMPLES = "raw_capture_samples"
    HOST_IDENTITY = "host_or_user_identity"
    PRIVATE_METADATA = "private_user_metadata"
    SMUGGLED_ARRAY = "numeric_array_as_samples"


# Ключи разбиваются на токены по не-буквоцифрам: 'ch1_samples' -> {'ch1', 'samples'}.
_SAMPLE_TOKENS: Final[frozenset[str]] = frozenset(
    {"sample", "samples", "waveform", "waveforms", "trace", "traces", "readings"},
)
_HOST_TOKENS: Final[frozenset[str]] = frozenset(
    {"hostname", "host", "computer", "machine", "username", "user", "account"},
)
_PRIVATE_TOKENS: Final[frozenset[str]] = frozenset(
    {"location", "alias", "label", "note", "notes", "comment", "remarks"},
)

_STANDARD_RECORD_ATTRS: Final[frozenset[str]] = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__,
) | {
    "taskName",
    "message",
}


def _rule_for_key(key: str) -> RedactionRule | None:
    """Определяет правило редакции по токенам имени поля."""
    tokens = set(_split_tokens(key))
    if tokens & _SAMPLE_TOKENS:
        return RedactionRule.RAW_SAMPLES
    if tokens & _HOST_TOKENS:
        return RedactionRule.HOST_IDENTITY
    if tokens & _PRIVATE_TOKENS:
        return RedactionRule.PRIVATE_METADATA
    return None


def _split_tokens(key: str) -> Generator[str]:
    token: list[str] = []
    for char in key.casefold():
        if char.isalnum():
            token.append(char)
        elif token:
            yield "".join(token)
            token = []
    if token:
        yield "".join(token)


def _redacted(rule: RedactionRule) -> dict[str, str | bool]:
    """Возвращает стабильную машинную пометку редакции с причиной."""
    return {"redacted": True, "reason": rule.value}


def redact_value(value: object, *, redact_private_metadata: bool, depth: int = 0) -> object:
    """Рекурсивно редактирует значение перед записью в журнал.

    Числовой массив длиной >= ``_NUMERIC_ARRAY_LIMIT`` считается попыткой
    пронести сырые отсчёты под безобидным ключом и редактируется независимо
    от имени ключа (защита от smuggling).
    """
    if depth > _MAX_REDACTION_DEPTH:
        return _redacted(RedactionRule.SMUGGLED_ARRAY)
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            rule = _rule_for_key(key)
            if rule is RedactionRule.PRIVATE_METADATA and not redact_private_metadata:
                rule = None
            if rule is not None:
                result[key] = _redacted(rule)
            else:
                result[key] = redact_value(
                    item,
                    redact_private_metadata=redact_private_metadata,
                    depth=depth + 1,
                )
        return result
    if isinstance(value, (list, tuple)):
        if len(value) >= _NUMERIC_ARRAY_LIMIT and all(_is_number(item) for item in value):
            return _redacted(RedactionRule.SMUGGLED_ARRAY)
        return [
            redact_value(item, redact_private_metadata=redact_private_metadata, depth=depth + 1)
            for item in value
        ]
    return value


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@final
class JsonLinesFormatter(logging.Formatter):
    """Форматирует записи в одну JSON-строку с корреляцией и редакцией."""

    def __init__(self, *, redact_private_metadata: bool = True) -> None:
        """Фиксирует режим редакции приватных метаданных."""
        super().__init__()
        self._redact_private_metadata: bool = redact_private_metadata

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Возвращает валидную JSON-строку даже для враждебных полей."""
        try:
            payload = self._payload(record)
            return json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except Exception:  # noqa: BLE001 - журнал не имеет права падать на данных
            return self._fallback(record)

    def _payload(self, record: logging.LogRecord) -> dict[str, object]:
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS
        }
        return {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "job_id": job_id_var.get(),
            "session_id": session_id_var.get(),
            "request_id": request_id_var.get(),
            "fields": redact_value(
                extra,
                redact_private_metadata=self._redact_private_metadata,
            ),
        }

    def _fallback(self, record: logging.LogRecord) -> str:
        """Минимальная запись-заменитель: сам факт события без непечатаемых данных."""
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": "log_record_unserializable",
            "job_id": job_id_var.get(),
            "session_id": session_id_var.get(),
            "request_id": request_id_var.get(),
            "fields": {},
        }
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def attach_file_logging(
    log_dir: Path,
    settings: LoggingSettings,
    *,
    logger: logging.Logger | None = None,
) -> logging.Handler:
    """Подключает ротируемый JSON-lines обработчик к журналу проекта."""
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / LOG_FILENAME,
        maxBytes=settings.max_bytes,
        backupCount=settings.backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        JsonLinesFormatter(redact_private_metadata=settings.redact_private_metadata)
    )
    target = logger if logger is not None else logging.getLogger(LOG_LOGGER_NAME)
    target.addHandler(handler)
    return handler
