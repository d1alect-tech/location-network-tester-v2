"""Готовность экземпляра LNT: health-опрос, фокус второго запуска, браузер."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from typing import Final

from lnt.errors import InputError

PORT_FALLBACK_SPAN: Final = 16
HEALTH_ATTEMPTS: Final = 120
HEALTH_INTERVAL_S: Final = 0.25
FOCUS_PROBE_TIMEOUT_S: Final = 0.5
UI_URL_TEMPLATE: Final = "http://127.0.0.1:{port}/"

BrowserOpener = Callable[[str], object]

__all__ = [
    "FOCUS_PROBE_TIMEOUT_S",
    "HEALTH_ATTEMPTS",
    "HEALTH_INTERVAL_S",
    "PORT_FALLBACK_SPAN",
    "UI_URL_TEMPLATE",
    "BrowserOpener",
    "_focus_running_instance",
    "_health_payload",
    "_open_when_ready",
]


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
