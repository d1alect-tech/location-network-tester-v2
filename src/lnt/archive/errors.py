"""Типизированные отказы архивного trust boundary."""

from dataclasses import dataclass
from typing import override


@dataclass(frozen=True, slots=True)
class ArchiveError(Exception):
    """Архив отклонён до публикации конечного каталога."""

    message: str

    @override
    def __str__(self) -> str:
        return self.message
