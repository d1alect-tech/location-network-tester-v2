"""Типизированные ошибки immutable-хранилища анализа."""

from pathlib import Path

from lnt.errors import InputError


class RecipeError(InputError):
    """Рецепт анализа не соответствует строгой schema 1."""


class ArtifactCorruptError(InputError):
    """Опубликованный artifact не прошёл проверку целостности."""

    def __init__(self, path: Path, reason_code: str) -> None:
        """Фиксирует путь и машиночитаемую причину повреждения."""
        super().__init__(f"артефакт анализа повреждён: {path} ({reason_code})")
        self.path: Path = path
        self.reason_code: str = reason_code


class ArtifactConflictError(InputError):
    """Публикация столкнулась с уже существующим artifact того же ключа."""

    def __init__(self, path: Path) -> None:
        """Фиксирует конфликтующий путь публикации."""
        super().__init__(f"конфликт публикации артефакта анализа: {path}")
        self.path: Path = path
