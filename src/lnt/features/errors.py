"""Типизированные ошибки схемы спектральных признаков."""

from __future__ import annotations

from typing import final, override


@final
class FeatureSchemaError(Exception):
    """Ошибка разбора или проверки feature schema."""

    __slots__: tuple[str, ...] = ("message",)
    message: str

    def __init__(self, message: str) -> None:
        """Сохраняет русское диагностическое сообщение."""
        super().__init__(message)
        self.message = message

    @override
    def __str__(self) -> str:
        """Возвращает сообщение для CLI/API boundary."""
        return self.message
