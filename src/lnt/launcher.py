"""Точка входа локального приложения LNT: GUI-поверхность и диспетч подкоманд.

Порядок запуска: блокировка экземпляра (PID + время старта процесса), эксклюзивный
pre-bind слушающего сокета 127.0.0.1 (детерминированный следующий свободный порт),
Uvicorn поверх существующего FastAPI-приложения, ожидание готовности
``/api/health`` с совпадающим build ID, открытие браузера. Второй запуск видит
живую блокировку, находит работающий экземпляр через health и открывает его URL,
не привязывая второй сервер. Аварийное завершение в GUI-режиме (pythonw) пишет
код поддержки в журнал и одну строку в stderr без traceback.

Сам механизм живёт в листьях: ``lnt.launch_server`` (блокировка, порт, Uvicorn)
и ``lnt.launch_health`` (health-опрос, фокус второго запуска, браузер). Этот
модуль владеет только argparse-поверхностью ``lnt-app``, диспетчем
CLI-подкоманд замороженного exe и «немым» отчётом об аварии; остальные имена он
реэкспортирует, сохраняя тождество объектам листьев (см.
tests/test_launcher_characterization.py).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Канонический список подкоманд живёт в lnt.cli_spec (очередь A4): этот модуль
# лишь реэкспортирует его для диспетча замороженного exe. Тождество списку
# и реальному парсеру lnt.cli проверяет тест
# test_gui_main_cli_subcommands_match_parser (tests/test_launcher.py).
from lnt.cli_spec import CLI_SUBCOMMANDS
from lnt.errors import InputError
from lnt.launch_health import (
    FOCUS_PROBE_TIMEOUT_S,
    HEALTH_ATTEMPTS,
    HEALTH_INTERVAL_S,
    PORT_FALLBACK_SPAN,
    UI_URL_TEMPLATE,
    BrowserOpener,
    _focus_running_instance,
    _health_payload,
    _open_when_ready,
)
from lnt.launch_server import (
    _INSTALL_HINT,
    _UI_DEPENDENCIES,
    LOCK_FILENAME,
    MAX_PORT,
    PREFERRED_PORT,
    SUPPORT_CODE_PREFIX,
    _build_id,
    _create_application,
    _logging_settings,
    _run_uvicorn,
    acquire_instance_lock,
    bind_first_free_port,
    launch,
    support_code,
)

__all__ = [
    "CLI_SUBCOMMANDS",
    "FOCUS_PROBE_TIMEOUT_S",
    "HEALTH_ATTEMPTS",
    "HEALTH_INTERVAL_S",
    "LOCK_FILENAME",
    "MAX_PORT",
    "PORT_FALLBACK_SPAN",
    "PREFERRED_PORT",
    "SUPPORT_CODE_PREFIX",
    "UI_URL_TEMPLATE",
    "_INSTALL_HINT",
    "_UI_DEPENDENCIES",
    "BrowserOpener",
    "_build_id",
    "_create_application",
    "_focus_running_instance",
    "_health_payload",
    "_logging_settings",
    "_open_when_ready",
    "_run_uvicorn",
    "acquire_instance_lock",
    "bind_first_free_port",
    "gui_main",
    "launch",
    "support_code",
]


def _guard_null_streams() -> None:
    """Замещает отсутствующие консольные потоки devnull (windowed-сборка).

    Дефект из smoke Todo 48: в PyInstaller windowed-экземпляре sys.stdout и
    sys.stderr равны None, и первый же print()/лог-запись ронял запуск с
    AttributeError: 'NoneType' object has no attribute 'write' (в GUI-режиме
    это выглядело как немой отказ или модальный диалог загрузчика).
    """
    devnull = Path(os.devnull)
    if sys.stdout is None:
        sys.stdout = devnull.open("w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = devnull.open("w", encoding="utf-8")


def gui_main(argv: list[str] | None = None) -> int:
    """Точка входа упакованного приложения: без traceback в консоль GUI."""
    _guard_null_streams()
    tokens = list(sys.argv[1:] if argv is None else argv)
    if tokens and tokens[0] in CLI_SUBCOMMANDS:
        # Дефект, найденный smoke-прогоном Todo 48: замороженный exe умел только
        # GUI-лаунчер, и `LNT.exe selftest` падал с exit 2 через argparse.
        # Зарегистрированные CLI-подкоманды пробрасываются настоящему парсеру;
        # запуск без позиционных аргументов сохраняет прежнее поведение GUI.
        from lnt.cli import main as cli_main  # noqa: PLC0415

        try:
            return cli_main(tokens)
        except KeyboardInterrupt:
            return 0
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
    causes: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        causes.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    logging.getLogger("lnt.launcher").critical(
        "аварийное завершение; код поддержки=%s; ошибка=%s",
        code,
        " -> ".join(causes),
    )
    sys.stderr.write(f"Аварийное завершение LNT. Код поддержки: {code}\n")


if __name__ == "__main__":
    raise SystemExit(gui_main())
