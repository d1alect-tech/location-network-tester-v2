"""Тесты одноэкземплярного запуска: блокировка, fallback порта, второй запуск."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from lnt.launcher import (
    LOCK_FILENAME,
    SUPPORT_CODE_PREFIX,
    acquire_instance_lock,
    bind_first_free_port,
    gui_main,
    launch,
    support_code,
)
from lnt.runtime.lease import bind_exclusive_loopback

_HEALTH_TIMEOUT_S = 30.0
_STOP_TIMEOUT_S = 15.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _health(port: int) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health",
            timeout=1.0,
        ) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _wait_health(port: int, timeout_s: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        payload = _health(port)
        if payload is not None and payload.get("status") == "ok":
            return payload
        time.sleep(0.1)
    pytest.fail(f"сервер на порту {port} не ответил за {timeout_s} с")


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Callable[[int], subprocess.Popen[str]]]:
    """Запускает реальный процесс-лаунчер и гарантирует завершение в teardown."""
    processes: list[subprocess.Popen[str]] = []

    def start(port: int) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "lnt.launcher",
                "--root",
                str(tmp_path / "сессии"),
                "--port",
                str(port),
                "--no-browser",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        processes.append(process)
        return process

    yield start
    for process in processes:
        process.kill()
        process.wait(timeout=_STOP_TIMEOUT_S)


def test_two_processes_yield_one_server_and_second_focuses_url(
    tmp_path: Path,
    server: Callable[[int], subprocess.Popen[str]],
) -> None:
    port = _free_port()
    root = tmp_path / "сессии"
    process = server(port)
    first_health = _wait_health(port, _HEALTH_TIMEOUT_S)

    opened: list[str] = []
    exit_code = launch(
        root=root,
        preferred_port=port,
        open_browser=True,
        browser_opener=opened.append,
    )

    assert exit_code == 0
    assert opened == [f"http://127.0.0.1:{port}/"]
    second_health = _health(port)
    assert second_health == first_health
    assert process.poll() is None


def test_stale_pid_lock_is_recovered_by_clean_takeover(tmp_path: Path) -> None:
    paths = tmp_path / "state"
    paths.mkdir()
    lock_path = paths / LOCK_FILENAME
    dead = subprocess.Popen(
        [sys.executable, "-c", "pass"],
    )
    dead.wait(timeout=30)
    lock_path.write_text(
        json.dumps(
            {
                "pid": dead.pid,
                "process_start_time": -1,
                "build_id": "устаревшая-сборка",
                "acquired_utc": "2026-01-01T00:00:00+00:00",
            },
        ),
        encoding="utf-8",
    )

    lease = acquire_instance_lock(lock_path, build_id="текущая-сборка")

    try:
        assert lease.owner.pid == os.getpid()
    finally:
        lease.release()
    assert not lock_path.exists()


def test_port_fallback_is_deterministic_next_free(tmp_path: Path) -> None:
    del tmp_path
    preferred = _free_port()
    blocker = bind_exclusive_loopback(preferred)
    try:
        bound, chosen = bind_first_free_port(preferred)
    finally:
        blocker.close()

    try:
        assert chosen == preferred + 1
        assert bound.getsockname()[1] == preferred + 1
    finally:
        bound.close()


def test_support_code_is_stable_short_and_distinct() -> None:
    first = support_code(RuntimeError("сбой захвата"))
    same = support_code(RuntimeError("сбой захвата"))
    other = support_code(RuntimeError("другой сбой"))

    assert first == same
    assert first != other
    assert first.startswith(SUPPORT_CODE_PREFIX)
    body = first.removeprefix(SUPPORT_CODE_PREFIX)
    assert len(body) == 8
    int(body, 16)


def test_gui_main_crash_writes_support_code_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def explode(**_kwargs: object) -> int:
        raise RuntimeError("взрыв в рабочем режиме")

    monkeypatch.setattr("lnt.launcher.launch", explode)

    exit_code = gui_main(
        ["--root", str(tmp_path / "сессии"), "--port", str(_free_port()), "--no-browser"],
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert SUPPORT_CODE_PREFIX in captured.err
