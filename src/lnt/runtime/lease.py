"""Межпроцессная аренда единственного аппаратного владельца LNT."""

from __future__ import annotations

import ctypes
import json
import os
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Self, TypedDict, final, override

_CREATE_FLAGS: Final = os.O_CREAT | os.O_EXCL | os.O_WRONLY
_WINDOWS_QUERY_LIMITED_INFORMATION: Final = 0x1000
_PROC_START_INDEX: Final = 21


class _OwnerPayload(TypedDict):
    pid: int
    process_start_time: int
    build_id: str
    acquired_utc: str


@dataclass(frozen=True, slots=True)
class LeaseOwner:
    """Диагностика процесса, записанная в аренду."""

    pid: int
    process_start_time: int
    build_id: str
    acquired_utc: str

    def to_payload(self) -> _OwnerPayload:
        """Возвращает устойчивую JSON-форму владельца."""
        return {
            "pid": self.pid,
            "process_start_time": self.process_start_time,
            "build_id": self.build_id,
            "acquired_utc": self.acquired_utc,
        }


@dataclass(frozen=True, slots=True)
class HardwareLeaseHeldError(Exception):
    """Живой процесс уже владеет аппаратной арендой."""

    owner: LeaseOwner
    code: str = "hardware_lease_held"

    @override
    def __str__(self) -> str:
        return (
            "аппарат уже занят: "
            f"PID={self.owner.pid}, запуск={self.owner.process_start_time}, "
            f"сборка={self.owner.build_id}, получено={self.owner.acquired_utc}"
        )


@dataclass(frozen=True, slots=True)
class InvalidLeaseError(Exception):
    """Файл аренды повреждён и не может быть безопасно вытеснен."""

    path: Path
    code: str = "hardware_lease_invalid"

    @override
    def __str__(self) -> str:
        return f"повреждён файл аппаратной аренды: {self.path}"


ProcessProbe = Callable[[int], int | None]


@final
class HardwareLease:
    """Эксклюзивный файл, удаляемый только создавшим его владельцем."""

    def __init__(self, path: Path, owner: LeaseOwner) -> None:
        """Запоминает путь и точную идентичность полученной аренды."""
        self.path: Path = path
        self.owner: LeaseOwner = owner
        self._released = False

    @classmethod
    def acquire(
        cls,
        path: Path,
        *,
        build_id: str,
        process_probe: ProcessProbe | None = None,
    ) -> Self:
        """Атомарно получает аренду, вытесняя только мёртвый или переиспользованный PID."""
        probe = process_probe or current_process_start_time
        path.parent.mkdir(parents=True, exist_ok=True)
        pid = os.getpid()
        start = probe(pid)
        if start is None:
            raise InvalidLeaseError(path)
        owner = LeaseOwner(pid, start, build_id, datetime.now(UTC).isoformat())
        while True:
            try:
                descriptor = os.open(path, _CREATE_FLAGS, 0o600)
            except FileExistsError:
                existing, identity = _read_owner(path)
                observed_start = probe(existing.pid)
                if observed_start == existing.process_start_time:
                    raise HardwareLeaseHeldError(existing) from None
                _unlink_if_unchanged(path, identity)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as lease_file:
                json.dump(owner.to_payload(), lease_file, ensure_ascii=False)
                lease_file.flush()
                os.fsync(lease_file.fileno())
            return cls(path, owner)

    def release(self) -> None:
        """Освобождает только всё ещё принадлежащий этому объекту файл."""
        if self._released:
            return
        try:
            owner, identity = _read_owner(self.path)
        except FileNotFoundError:
            self._released = True
            return
        if owner == self.owner:
            _unlink_if_unchanged(self.path, identity)
        self._released = True

    def __enter__(self) -> Self:
        """Возвращает полученную аренду."""
        return self

    def __exit__(self, *_error: object) -> None:
        """Всегда освобождает аренду при выходе."""
        self.release()


def current_process_start_time(pid: int) -> int | None:
    """Возвращает неизменяемое время создания процесса без psutil.

    На Windows используется ``GetProcessTimes`` с минимальным правом
    ``PROCESS_QUERY_LIMITED_INFORMATION``. На POSIX читается стартовый tick из procfs.
    """
    if sys.platform == "win32":
        return _windows_process_start_time(pid)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    return int(fields[_PROC_START_INDEX]) if len(fields) > _PROC_START_INDEX else None


def bind_exclusive_loopback(port: int) -> socket.socket:
    """Связывает слушающий loopback-сокет без допуска Windows ``SO_REUSEADDR``."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        server.bind(("127.0.0.1", port))
        server.listen()
    except OSError:
        server.close()
        raise
    return server


def _read_owner(path: Path) -> tuple[LeaseOwner, tuple[int, int, int]]:
    before = path.stat()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        owner = LeaseOwner(
            pid=int(payload["pid"]),
            process_start_time=int(payload["process_start_time"]),
            build_id=str(payload["build_id"]),
            acquired_utc=str(payload["acquired_utc"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise InvalidLeaseError(path) from error
    return owner, (before.st_dev, before.st_ino, before.st_mtime_ns)


def _unlink_if_unchanged(path: Path, identity: tuple[int, int, int]) -> None:
    current = path.stat()
    if (current.st_dev, current.st_ino, current.st_mtime_ns) != identity:
        return
    path.unlink()


def _windows_process_start_time(pid: int) -> int | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_WINDOWS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not handle:
        return None
    creation = ctypes.c_ulonglong()
    exit_time = ctypes.c_ulonglong()
    kernel = ctypes.c_ulonglong()
    user = ctypes.c_ulonglong()
    try:
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        return int(creation.value) if ok else None
    finally:
        kernel32.CloseHandle(handle)
