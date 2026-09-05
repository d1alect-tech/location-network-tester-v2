"""Характеризационные тесты фасада lnt.launcher перед разводкой на листья.

Очередь C4 (хвост): launcher.py дублировал код launch_health.py и
launch_server.py байт-в-байт, листья висели мёртвым грузом. Эти тесты
фиксируют наблюдаемый контракт фасада ДО прореживания:

* набор публичных имён точки входа и их значения;
* паритет ``CLI_SUBCOMMANDS`` с реальным парсером ``lnt.cli`` (инвариант A4);
* поведение health-опроса на путях «готов» и «не готов» с точными русскими
  сообщениями;
* обращение ``gui_main`` к ``launch`` через глобальное имя модуля — это
  единственный способ, которым monkeypatch ``lnt.launcher.launch`` работает.

Отдельный тест ``test_leaf_functions_are_reexported_by_identity`` — контракт
самой разводки: до прореживания он КРАСНЫЙ (фасад держит собственные копии
функций), после — зелёный (фасад реэкспортирует объекты листьев).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import types
import urllib.request
from typing import TYPE_CHECKING, Final, Self

import pytest

from lnt import launch_health, launch_server, launcher
from lnt.cli import _build_parser  # pyright: ignore[reportPrivateUsage]
from lnt.cli_spec import CLI_SUBCOMMANDS
from lnt.errors import InputError

if TYPE_CHECKING:
    from pathlib import Path

_HEALTH_CONSTANTS: Final = (
    "FOCUS_PROBE_TIMEOUT_S",
    "HEALTH_ATTEMPTS",
    "HEALTH_INTERVAL_S",
    "PORT_FALLBACK_SPAN",
    "UI_URL_TEMPLATE",
    "BrowserOpener",
)
_HEALTH_FUNCTIONS: Final = (
    "_focus_running_instance",
    "_health_payload",
    "_open_when_ready",
)
_SERVER_CONSTANTS: Final = (
    "LOCK_FILENAME",
    "MAX_PORT",
    "PREFERRED_PORT",
    "SUPPORT_CODE_PREFIX",
    "_INSTALL_HINT",
    "_UI_DEPENDENCIES",
)
_SERVER_FUNCTIONS: Final = (
    "_build_id",
    "_create_application",
    "_logging_settings",
    "_run_uvicorn",
    "acquire_instance_lock",
    "bind_first_free_port",
    "launch",
    "support_code",
)
# Точка входа GUI остаётся в самом фасаде: он владеет argparse-поверхностью,
# диспетчем CLI-подкоманд и «немым» отчётом об аварии.
_LOCAL_FUNCTIONS: Final = ("_guard_null_streams", "_report_crash", "gui_main")

_LEAVES: Final = {"launch_health": launch_health, "launch_server": launch_server}
_LEAF_CONSTANTS: Final = tuple(
    [("launch_health", name) for name in _HEALTH_CONSTANTS]
    + [("launch_server", name) for name in _SERVER_CONSTANTS]
)
_LEAF_FUNCTIONS: Final = tuple(
    [("launch_health", name) for name in _HEALTH_FUNCTIONS]
    + [("launch_server", name) for name in _SERVER_FUNCTIONS]
)
_PUBLIC_SURFACE: Final = (
    "CLI_SUBCOMMANDS",
    *_HEALTH_CONSTANTS,
    *_SERVER_CONSTANTS,
    *_HEALTH_FUNCTIONS,
    *_SERVER_FUNCTIONS,
    *_LOCAL_FUNCTIONS,
)


class _FakeResponse:
    """Минимальный ответ urlopen: контекст-менеджер с ``read`` для json.load."""

    _body: bytes

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, *_args: object) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _install_urlopen(monkeypatch: pytest.MonkeyPatch, body: bytes | None) -> list[str]:
    """Подменяет urlopen: ``None`` — экземпляр молчит, иначе отдаёт body."""
    seen: list[str] = []

    def fake_urlopen(url: str, timeout: float = 0.0) -> _FakeResponse:
        del timeout
        seen.append(url)
        if body is None:
            raise OSError(61, "соединение отклонено")
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


@pytest.fixture
def instant_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Убирает ожидание между health-попытками, сохраняя их количество."""

    def no_sleep(seconds: float) -> None:
        del seconds

    monkeypatch.setattr(time, "sleep", no_sleep)


def _parser_choices() -> set[str]:
    for action in _build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):  # pyright: ignore[reportPrivateUsage]
            return set(action.choices)
    raise AssertionError("у lnt.cli нет subparsers")


@pytest.mark.parametrize("name", _PUBLIC_SURFACE)
def test_entry_surface_name_exists(name: str) -> None:
    """Каждое имя поверхности запуска остаётся доступным на фасаде."""
    assert hasattr(launcher, name), f"lnt.launcher потерял имя {name}"


@pytest.mark.parametrize(("leaf", "name"), _LEAF_CONSTANTS)
def test_leaf_constants_agree_with_facade(leaf: str, name: str) -> None:
    """Константы фасада совпадают со значениями листа-владельца."""
    assert getattr(launcher, name) == getattr(_LEAVES[leaf], name)


@pytest.mark.parametrize(("leaf", "name"), _LEAF_FUNCTIONS)
def test_leaf_functions_are_reexported_by_identity(leaf: str, name: str) -> None:
    """Контракт разводки: фасад отдаёт ОБЪЕКТ листа, а не собственную копию."""
    assert getattr(launcher, name) is getattr(_LEAVES[leaf], name)


@pytest.mark.parametrize("name", _LOCAL_FUNCTIONS)
def test_facade_keeps_its_own_entry_point_functions(name: str) -> None:
    """GUI-точка входа и аварийный отчёт остаются определены в самом фасаде."""
    assert getattr(launcher, name).__module__ == "lnt.launcher"


def test_cli_subcommands_mirror_the_real_parser() -> None:
    """Инвариант A4: CLI_SUBCOMMANDS тождественен единому источнику и парсеру."""
    assert launcher.CLI_SUBCOMMANDS is CLI_SUBCOMMANDS
    assert set(launcher.CLI_SUBCOMMANDS) == _parser_choices()
    assert "selftest" in launcher.CLI_SUBCOMMANDS
    assert "ui" in launcher.CLI_SUBCOMMANDS


def test_health_payload_returns_dict_when_instance_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _install_urlopen(monkeypatch, b'{"status": "ok", "build_id": "abc"}')

    payload = launcher._health_payload(8765)

    assert payload == {"status": "ok", "build_id": "abc"}
    assert seen == ["http://127.0.0.1:8765/api/health"]


def test_health_payload_returns_none_when_instance_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_urlopen(monkeypatch, None)

    assert launcher._health_payload(8765) is None


def test_focus_running_instance_opens_url_of_the_live_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_urlopen(monkeypatch, b'{"status": "ok"}')
    opened: list[str] = []

    exit_code = launcher._focus_running_instance(
        8765,
        open_browser=True,
        browser_opener=opened.append,
    )

    assert exit_code == 0
    assert opened == ["http://127.0.0.1:8765/"]


def test_focus_running_instance_reports_exact_dead_lock_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_urlopen(monkeypatch, None)
    opened: list[str] = []
    expected = "экземпляр LNT уже запущен, но не отвечает на health; порты 8765..8780"

    with pytest.raises(InputError, match=re.escape(expected)) as excinfo:
        launcher._focus_running_instance(8765, open_browser=True, browser_opener=opened.append)

    assert str(excinfo.value) == expected


def test_open_when_ready_opens_browser_on_matching_build_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_urlopen(monkeypatch, json.dumps({"status": "ok", "build_id": "сбор"}).encode())
    opened: list[str] = []

    launcher._open_when_ready("http://127.0.0.1:8765/", 8765, "сбор", opened.append)

    assert opened == ["http://127.0.0.1:8765/"]


@pytest.mark.usefixtures("instant_sleep")
def test_open_when_ready_never_opens_browser_for_mismatched_build_id(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _install_urlopen(monkeypatch, b'{"status": "ok", "build_id": "another"}')
    opened: list[str] = []

    with caplog.at_level(logging.DEBUG, logger="lnt.launcher"):
        launcher._open_when_ready("http://127.0.0.1:8765/", 8765, "сбор", opened.append)

    assert opened == []
    assert "интерфейс не подтвердил готовность до истечения ожидания" in caplog.text


def test_bind_first_free_port_rejects_out_of_range_port() -> None:
    expected = "порт должен быть в диапазоне 1..65535"

    with pytest.raises(InputError, match=re.escape(expected)) as excinfo:
        launcher.bind_first_free_port(0)

    assert str(excinfo.value) == expected


def test_support_code_prefixes_eight_hex_digits() -> None:
    code = launcher.support_code(RuntimeError("сбой захвата"))

    assert code.startswith(launcher.SUPPORT_CODE_PREFIX)
    int(code.removeprefix(launcher.SUPPORT_CODE_PREFIX), 16)


def test_gui_main_calls_launch_through_the_module_global(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """monkeypatch ``lnt.launcher.launch`` обязан перехватывать запуск."""
    seen: dict[str, object] = {}

    def fake_launch(*, root: Path, preferred_port: int, open_browser: bool) -> int:
        seen["root"] = root
        seen["preferred_port"] = preferred_port
        seen["open_browser"] = open_browser
        return 42

    monkeypatch.setattr("lnt.launcher.launch", fake_launch)
    root = tmp_path / "сессии"

    exit_code = launcher.gui_main(["--root", str(root), "--port", "9001", "--no-browser"])

    assert exit_code == 42
    assert seen == {"root": root, "preferred_port": 9001, "open_browser": False}


def test_gui_main_dispatches_cli_subcommands_and_reports_crash_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def fake_cli_main(argv: list[str]) -> int:
        assert argv == ["selftest"]
        return 7

    monkeypatch.setattr("lnt.cli.main", fake_cli_main)
    assert launcher.gui_main(["selftest"]) == 7

    def explode(**_kwargs: object) -> int:
        raise RuntimeError("взрыв в рабочем режиме")

    monkeypatch.setattr("lnt.launcher.launch", explode)
    exit_code = launcher.gui_main(["--root", str(tmp_path / "сессии"), "--no-browser"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Traceback" not in captured.err
    assert captured.err.startswith("Аварийное завершение LNT. Код поддержки: LNT-SUP-")


def test_run_uvicorn_is_reachable_through_the_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeConfig:
        def __init__(
            self,
            application: object,
            log_level: str = "info",
            log_config: object = "sentinel",
        ) -> None:
            del application, log_level
            captured["log_config"] = log_config

    class FakeServer:
        def __init__(self, config: FakeConfig) -> None:
            del config

        def run(self, sockets: list[object]) -> None:
            captured["sockets"] = sockets

    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        types.SimpleNamespace(Config=FakeConfig, Server=FakeServer),
    )
    sentinel = object()

    launcher._run_uvicorn(object(), server_socket=sentinel)  # pyright: ignore[reportArgumentType]

    assert captured["log_config"] is None
    assert captured["sockets"] == [sentinel]
