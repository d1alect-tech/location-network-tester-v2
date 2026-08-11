"""Межпроцессный writer-lock контекста через эксклюзивный lock-файл."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from lnt.errors import InputError


class ContextLockError(InputError):
    """Writer-lock текущей сессии уже занят."""

    def __init__(self, path: Path) -> None:
        """Сохраняет занятый путь lock-файла."""
        super().__init__(f"контекст сессии уже изменяется: {path.parent}")
        self.path: Path = path


@contextmanager
def session_writer_lock(path: Path) -> Generator[None]:
    """Удерживает O_EXCL lock до завершения записи события и cache."""
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ContextLockError(path) from error
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)
