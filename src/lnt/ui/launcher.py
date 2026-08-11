"""Запуск локального веб-интерфейса LNT."""

import hashlib
import logging
import threading
import time
import urllib.request
import webbrowser
from functools import partial
from http import HTTPStatus
from pathlib import Path
from typing import Final

from lnt.analysis_store.identity import CodeIdentity
from lnt.errors import InputError
from lnt.runtime.lease import HardwareLease, HardwareLeaseHeldError, bind_exclusive_loopback

UI_URL_TEMPLATE: Final = "http://127.0.0.1:{port}/"
_HEALTH_PATH: Final = "api/health"
_HEALTH_ATTEMPTS: Final = 120
_HEALTH_INTERVAL_S: Final = 0.25
_HEALTH_TIMEOUT_S: Final = 1.0
_MAX_PORT: Final = 65_535
_BROWSER_THREAD_NAME: Final = "lnt-ui-browser"
_UI_DEPENDENCIES: Final = frozenset(
    {"fastapi", "uvicorn", "starlette", "multipart", "python_multipart", "pydantic"},
)
_INSTALL_HINT: Final = "интерфейс не установлен: pip install 'lnt[ui]' (см. README)"


def _open_browser_when_ready(url: str) -> None:
    """Открывает браузер после готовности API либо молча прекращает ожидание."""
    health_url = f"{url}{_HEALTH_PATH}"
    for attempt in range(_HEALTH_ATTEMPTS):
        response_ready = False
        try:
            with urllib.request.urlopen(  # noqa: S310 -- URL всегда локальный HTTP
                health_url,
                timeout=_HEALTH_TIMEOUT_S,
            ) as response:
                response_ready = response.status == HTTPStatus.OK
        except OSError:
            response_ready = False

        if response_ready:
            try:
                webbrowser.open(url)
            except (OSError, webbrowser.Error):
                logging.getLogger(__name__).debug("не удалось открыть браузер", exc_info=True)
            return
        if attempt < _HEALTH_ATTEMPTS - 1:
            time.sleep(_HEALTH_INTERVAL_S)

    logging.getLogger(__name__).debug("интерфейс не ответил до истечения ожидания")


def run_ui(*, root: Path, port: int, open_browser: bool) -> int:
    """Запускает UI одним процессом и завершает его без traceback по Ctrl+C.

    Один процесс обязателен: приложение разделяет единый JobManager/executor и
    допускает только одного владельца USB-устройства.
    """
    if not 1 <= port <= _MAX_PORT:
        raise InputError("--port: порт должен быть в диапазоне 1..65535")

    root.mkdir(parents=True, exist_ok=True)
    try:
        import uvicorn  # noqa: PLC0415

        from lnt.app_paths import resolve_app_paths  # noqa: PLC0415
        from lnt.ui.app import create_app  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        dependency = exc.name.partition(".")[0] if exc.name is not None else None
        if dependency in _UI_DEPENDENCIES:
            raise InputError(_INSTALL_HINT) from exc
        raise

    paths = resolve_app_paths()
    try:
        lease = HardwareLease.acquire(
            paths.runtime_db.parent / "hardware.lease",
            build_id=_build_id(),
        )
    except HardwareLeaseHeldError as error:
        raise InputError(str(error)) from error
    try:
        with lease, bind_exclusive_loopback(port) as server_socket:
            application = create_app(
                root=root,
                catalog_db=paths.catalog_db,
                runtime_db=paths.runtime_db,
            )
            url = UI_URL_TEMPLATE.format(port=port)
            print(f"LNT UI: {url}", flush=True)  # noqa: T201
            if open_browser:
                threading.Thread(
                    target=partial(_open_browser_when_ready, url),
                    daemon=True,
                    name=_BROWSER_THREAD_NAME,
                ).start()
            config = uvicorn.Config(application, log_level="info")
            uvicorn.Server(config).run(sockets=[server_socket])
    except KeyboardInterrupt:
        return 0
    except OSError as error:
        raise InputError(f"порт 127.0.0.1:{port} уже занят другим сервером") from error
    return 0


def _build_id() -> str:
    identity = CodeIdentity.current().identity_string.encode()
    return hashlib.sha256(identity).hexdigest()[:16]
