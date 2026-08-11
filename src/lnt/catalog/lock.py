"""Межпроцессный lock единственного writer перестраиваемого каталога."""

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

from lnt.errors import InputError


class CatalogBusyError(InputError):
    """Другой процесс уже изменяет каталог."""

    reason_code: Final = "catalog_busy"

    def __init__(self, path: Path) -> None:
        """Сохраняет путь занятого lock-файла и подсказку оператору."""
        location = f"каталог занят другой операцией: {path.parent}; "
        super().__init__(location + "закройте другую операцию записи и повторите попытку")
        self.path: Path = path


@contextmanager
def catalog_writer_lock(path: Path, *, timeout_s: float) -> Generator[None]:
    """Ожидает O_EXCL lock до timeout и удаляет его после записи."""
    deadline = time.monotonic() + timeout_s
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            if time.monotonic() >= deadline:
                raise CatalogBusyError(path) from error
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)
