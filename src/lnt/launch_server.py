"""Запуск единственного экземпляра LNT: блокировка, порт, Uvicorn."""

from __future__ import annotations

import hashlib
import threading
import webbrowser
from typing import TYPE_CHECKING, Final

from lnt import launch_health
from lnt.analysis_store.identity import CodeIdentity
from lnt.app_paths import resolve_app_paths
from lnt.errors import InputError
from lnt.launch_health import (
    PORT_FALLBACK_SPAN,
    UI_URL_TEMPLATE,
    BrowserOpener,
    _focus_running_instance,
    _open_when_ready,
)
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
MAX_PORT: Final = 65_535
_UI_DEPENDENCIES: Final = frozenset({"fastapi", "uvicorn", "starlette"})
_INSTALL_HINT: Final = "интерфейс не установлен: pip install 'lnt[ui]' (см. README)"

if TYPE_CHECKING:
    import socket
    from pathlib import Path

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
    # Дефект из smoke Todo 48: в windowed-сборке sys.stdout равен None, и
    # дефолтный LOGGING_CONFIG uvicorn падал на DefaultFormatter(use_colors=None)
    # с "'NoneType' object has no attribute 'isatty'". Отключаем его dictConfig:
    # журналы uvicorn идут в root и попадают в наш структурный файл-лог.
    uvicorn.Server(uvicorn.Config(application, log_level="info", log_config=None)).run(
        sockets=[server_socket]
    )


def _build_id() -> str:
    identity = CodeIdentity.current().identity_string.encode()
    return hashlib.sha256(identity).hexdigest()[:16]


__all__ = [
    "LOCK_FILENAME",
    "MAX_PORT",
    "PREFERRED_PORT",
    "SUPPORT_CODE_PREFIX",
    "_INSTALL_HINT",
    "_UI_DEPENDENCIES",
    "BrowserOpener",
    "_build_id",
    "_create_application",
    "_logging_settings",
    "_run_uvicorn",
    "acquire_instance_lock",
    "bind_first_free_port",
    "launch",
    "launch_health",
    "support_code",
]
