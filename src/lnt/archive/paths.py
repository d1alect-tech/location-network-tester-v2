"""Windows-safe нормализация путей ZIP до материализации."""

from __future__ import annotations

import re
import stat
import unicodedata
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from .errors import ArchiveError
from .models import ArchivePath

_RESERVED: Final = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.IGNORECASE)
_REPARSE_POINT: Final = 0x400
_CONTROL_LIMIT: Final = 32

if TYPE_CHECKING:
    import zipfile


def validate_member_name(raw: str) -> ArchivePath:
    """Парсит только относительный portable путь обычного файла."""
    normalized = unicodedata.normalize("NFC", raw.replace("\\", "/"))
    if not normalized or normalized.startswith(("/", "//")) or ":" in normalized:
        raise ArchiveError(f"небезопасный путь ZIP: {raw!r}")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArchiveError(f"небезопасный путь ZIP: {raw!r}")
    for part in parts:
        if part.endswith((".", " ")) or _RESERVED.match(part):
            raise ArchiveError(f"небезопасное имя Windows: {raw!r}")
        if any(ord(character) < _CONTROL_LIMIT for character in part):
            raise ArchiveError(f"управляющий символ в пути: {raw!r}")
    return ArchivePath("/".join(parts))


def collision_key(path: ArchivePath) -> str:
    """Даёт NFC+casefold ключ Windows case-insensitive namespace."""
    return unicodedata.normalize("NFC", str(path)).casefold()


def ensure_regular_file(info: zipfile.ZipInfo) -> None:
    """Отклоняет каталоги, symlink и special/reparse metadata."""
    if info.is_dir() or info.filename.endswith(("/", "\\")):
        raise ArchiveError(f"каталоги ZIP не разрешены: {info.filename!r}")
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if file_type not in {0, stat.S_IFREG} or info.external_attr & _REPARSE_POINT:
        raise ArchiveError(f"ссылка или special entry запрещены: {info.filename!r}")
