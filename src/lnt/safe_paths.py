"""Единый runtime-барьер путей (GAP-2): имена файлов и пути не покидают свой корень.

Продуктовые границы, которые обязаны проходить через этот модуль:
- имена файлов каналов из манифеста (``manifest.ch1.filename`` / ``ch2``) —
  чтение и запись в каталоге сессии;
- разрешение каталога сессии по имени пользователя внутри корня сессий;
- раздача файлов артефактов анализа по HTTP.

Классифицирующие контуры (каталог reconcile) используют :func:`is_safe_filename`
как предикат, а не исключение. Правила: только имя файла (без разделителей
путей), без ``..``, без абсолютных/UNC/устройных путей, без двоеточий
(диск/ADS) и без зарезервированных имён Windows.
"""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from typing import Final

from lnt.errors import InputError

_RESERVED_WINDOWS_NAMES: Final[frozenset[str]] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)

_TRAILING_DOTS_SPACES: Final[re.Pattern[str]] = re.compile(r"[. ]$")
_MAX_FILENAME_LENGTH: Final = 255


def is_safe_filename(filename: str) -> bool:
    """Возвращает True, если имя не может выйти за пределы своего каталога."""
    if not filename or filename in {".", ".."}:
        return False
    if len(filename) >= _MAX_FILENAME_LENGTH:
        return False
    windows = PureWindowsPath(filename)
    if windows.is_absolute() or windows.drive or windows.name != filename:
        # drive (C:, \\server), разделители / или \\, хвостовые точки/пробелы,
        # которые Windows отбрасывает при разрешении имени.
        return False
    if ":" in filename or "/" in filename or "\\" in filename:
        return False
    if _TRAILING_DOTS_SPACES.search(filename) is not None:
        return False
    stem = filename.split(".", maxsplit=1)[0].upper()
    return stem not in _RESERVED_WINDOWS_NAMES


def ensure_safe_filename(filename: str, *, label: str = "имя файла") -> str:
    """Возвращает ``filename`` или ``InputError`` с компактным русским текстом."""
    if not is_safe_filename(filename):
        raise InputError(f"{label} небезопасно: {filename!r}")
    return filename


def ensure_within_root(root: Path, candidate: Path) -> Path:
    """Проверяет, что ``candidate`` остаётся внутри ``root`` после разрешения.

    Возвращает нормализованный путь; иначе ``InputError``. Reparse points и
    symlink-компоненты проверяет вызывающая сторона там, где это применимо.
    """
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise InputError(
            f"путь выходит за пределы корня: {candidate}",
        ) from error
    return resolved_candidate
