"""Одноэкземплярный запуск локального приложения LNT.

Порядок запуска: блокировка экземпляра (PID + время старта процесса), эксклюзивный
pre-bind слушающего сокета 127.0.0.1 (детерминированный следующий свободный порт),
Uvicorn поверх существующего FastAPI-приложения, ожидание готовности
``/api/health`` с совпадающим build ID, открытие браузера. Второй запуск видит
живую блокировку, находит работающий экземпляр через health и открывает его URL,
не привязывая второй сервер. Аварийное завершение в GUI-режиме (pythonw) пишет
код поддержки в журнал и одну строку в stderr без traceback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

from lnt.analysis_store.identity import CodeIdentity
from lnt.app_paths import resolve_app_paths
from lnt.errors import InputError
from lnt.logging import attach_file_logging
from lnt.runtime.lease import (
    HardwareLease,
    HardwareLeaseHeldError,
    InvalidLeaseError,
    bind_exclusive_loopback,
)

PREFERRED_PORT: Final = 8765
LOCK_FILENAME: Final = "instance.lock"
SUPPORT_CODE_PREFIX: Final = "LNT-SUP-"
PORT_FALLBACK_SPAN: Final = 16
MAX_PORT: Final = 65_535
HEALTH_ATTEMPTS: Final = 120
HEALTH_INTERVAL_S: Final = 0.25
FOCUS_PROBE_TIMEOUT_S: Final = 0.5
UI_URL_TEMPLATE: Final = "http://127.0.0.1:{port}/"
_UI_DEPENDENCIES: Final = frozenset({"fastapi", "uvicorn", "starlette"})
_INSTALL_HINT: Final = "интерфейс не установлен: pip install 'lnt[ui]' (см. README)"

BrowserOpener = Callable[[str], object]

if TYPE_CHECKING:
    import socket

    from fastapi import FastAPI

    from lnt.config.model import LoggingSettings


def acquire_instance_lock(lock_path: Path, *, build_id: str) -> HardwareLease:
    """Берёт межпроцессную блокировку; мёртвый PID вытесняется, живой — отклоняется."""
    try:
        return HardwareLease.acquire(lock_path, build_id=build_id)
    except InvalidLeaseError as error:
        raise InputError(str(error)) from error


def bind_first_free_port(preferred: int) -> tuple[socket.socket, int]:
    """Эксклюзивно занимает первый свободный порт от preferred вправо."""
    if not 1 <= preferred <= MAX_PORT:
        raise InputError(f"порт должен быть в диапазоне 1..{MAX_PORT}")
    last_error: OSError | None = None
    chosen = preferred
    for port in range(preferred, min(preferred + PORT_FALLBACK_SPAN, MAX_PORT + 1)):
        chosen = port
        try:
            return bind_exclusive_loopback(port), port
        except OSError as error:
            last_error = error
    raise InputError(f"нет свободного порта в диапазоне {preferred}..{chosen}: {last_error}")


def support_code(error: BaseException) -> str:
    """Короткий детерминированный код для сопоставления аварии с журналом."""
    raw = f"{type(error).__name__}:{error}".encode(encoding="utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()[:8].upper()
    return f"{SUPPORT_CODE_PREFIX}{digest}"


def launch(
    *,
    root: Path,
    preferred_port: int = PREFERRED_PORT,
    open_browser: bool = True,
    browser_opener: BrowserOpener = webbrowser.open,
) -> int:
    """Запускает единственный экземпляр приложения либо фокусирует уже запущенный."""
    paths = resolve_app_paths()
    build_id = _build_id()
    lock_path = paths.runtime_db.parent / LOCK_FILENAME
    try:
        lease = HardwareLease.acquire(lock_path, build_id=build_id)
    except HardwareLeaseHeldError:
        return _focus_running_instance(
            preferred_port,
            open_browser=open_browser,
            browser_opener=browser_opener,
        )
    except InvalidLeaseError as error:
        raise InputError(str(error)) from error
    try:
        server_socket, port = bind_first_free_port(preferred_port)
    except InputError:
        lease.release()
        raise
    try:
        with lease, server_socket:
            attach_file_logging(paths.log_dir, _logging_settings())
            url = UI_URL_TEMPLATE.format(port=port)
            if open_browser:
                threading.Thread(
                    target=_open_when_ready,
                    args=(url, port, build_id, browser_opener),
                    daemon=True,
                    name="lnt-launcher-browser",
                ).start()
            application = _create_application(root=root)
            _run_uvicorn(application, server_socket=server_socket)
    except KeyboardInterrupt:
        return 0
    return 0


def gui_main(argv: list[str] | None = None) -> int:
    """Точка входа упакованного приложения: без traceback в консоль GUI."""
    parser = argparse.ArgumentParser(prog="lnt-app", description="Локальная панель LNT")
    parser.add_argument("--root", type=Path, default=Path.home() / "lnt-sessions")
    parser.add_argument("--port", type=int, default=PREFERRED_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    try:
        return launch(root=args.root, preferred_port=args.port, open_browser=not args.no_browser)
    except KeyboardInterrupt:
        return 0
    except InputError as error:
        _report_crash(error)
        return 2
    except Exception as error:  # noqa: BLE001 - граница GUI не показывает traceback
        _report_crash(error)
        return 1


def _report_crash(error: BaseException) -> None:
    """Пишет код поддержки в структурный журнал и одной строкой в stderr."""
    code = support_code(error)
    logging.getLogger("lnt.launcher").critical(
        "аварийное завершение; код поддержки=%s; ошибка=%s: %s",
        code,
        type(error).__name__,
        error,
    )
    sys.stderr.write(f"Аварийное завершение LNT. Код поддержки: {code}\n")


def _focus_running_instance(
    preferred_port: int,
    *,
    open_browser: bool,
    browser_opener: BrowserOpener,
) -> int:
    """Находит живой экземпляр по health и открывает его URL без повторной привязки."""
    last_port = preferred_port + PORT_FALLBACK_SPAN - 1
    for port in range(preferred_port, last_port + 1):
        if _health_payload(port) is not None:
            url = UI_URL_TEMPLATE.format(port=port)
            if open_browser:
                browser_opener(url)
            return 0
    ports_range = f"{preferred_port}..{last_port}"
    raise InputError(
        f"экземпляр LNT уже запущен, но не отвечает на health; порты {ports_range}",
    )


def _health_payload(port: int) -> dict[str, object] | None:
    """Возвращает ответ /api/health или None, если экземпляр не отвечает."""
    try:
        with urllib.request.urlopen(  # noqa: S310 -- URL всегда локальный HTTP
            UI_URL_TEMPLATE.format(port=port) + "api/health",
            timeout=FOCUS_PROBE_TIMEOUT_S,
        ) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _open_when_ready(url: str, port: int, build_id: str, opener: BrowserOpener) -> None:
    """Открывает браузер только когда health отвечает и build ID совпадает."""
    for attempt in range(HEALTH_ATTEMPTS):
        payload = _health_payload(port)
        ready = (
            payload is not None
            and payload.get("status") == "ok"
            and payload.get("build_id") == build_id
        )
        if ready:
            try:
                opener(url)
            except (OSError, webbrowser.Error):
                logging.getLogger("lnt.launcher").debug(
                    "не удалось открыть браузер",
                    exc_info=True,
                )
            return
        if attempt < HEALTH_ATTEMPTS - 1:
            time.sleep(HEALTH_INTERVAL_S)
    logging.getLogger("lnt.launcher").debug(
        "интерфейс не подтвердил готовность до истечения ожидания",
    )


def _logging_settings() -> LoggingSettings:
    """Читает секцию журналирования из конфигурации приложения."""
    from lnt.config.store import load_config  # noqa: PLC0415 - тяжёлый импорт по требованию

    resolved = resolve_app_paths()
    result = load_config(resolved.config_path, default_session_root=resolved.session_root)
    return result.config.logging


def _create_application(root: Path) -> FastAPI:
    """Создаёт FastAPI-приложение панели на путях приложения."""
    from lnt.ui.app import create_app  # noqa: PLC0415 - extra ui опциональна

    resolved = resolve_app_paths()
    return create_app(root=root, catalog_db=resolved.catalog_db, runtime_db=resolved.runtime_db)


def _run_uvicorn(application: FastAPI, *, server_socket: socket.socket) -> None:
    """Запускает Uvicorn на заранее привязанном сокете."""
    try:
        import uvicorn  # noqa: PLC0415 - extra ui опциональна
    except ModuleNotFoundError as exc:
        dependency = exc.name.partition(".")[0] if exc.name is not None else None
        if dependency in _UI_DEPENDENCIES:
            raise InputError(_INSTALL_HINT) from exc
        raise
    uvicorn.Server(uvicorn.Config(application, log_level="info")).run(sockets=[server_socket])


def _build_id() -> str:
    identity = CodeIdentity.current().identity_string.encode()
    return hashlib.sha256(identity).hexdigest()[:16]


if __name__ == "__main__":
    raise SystemExit(gui_main())
