"""Типизированные ошибки LNT.

Таксономия привязана к exit-кодам CLI: `InputError` (и наследники) -> 2,
`DeviceNotFoundError` -> 3. Любая другая ошибка -- дефект программы.
"""


class LntError(Exception):
    """Базовая ошибка LNT; несёт человекочитаемое сообщение."""

    def __init__(self, message: str) -> None:
        """Сохраняет сообщение и инициализирует базовый Exception."""
        super().__init__(message)
        self.message: str = message


class InputError(LntError):
    """Некорректный вход: файлы, аргументы, манифесты (exit 2)."""


class SessionTooShortError(InputError):
    """Запись короче минимума циклов сети для line-sync анализа."""

    def __init__(self, *, cycles_found: int, cycles_required: int) -> None:
        """Фиксирует найденное и требуемое число циклов сети."""
        super().__init__(
            f"запись слишком короткая: {cycles_found} циклов сети, нужно >= {cycles_required}",
        )
        self.cycles_found: int = cycles_found
        self.cycles_required: int = cycles_required


class DeviceNotFoundError(LntError):
    """Осциллограф Hantek 6022BE не найден или недоступен (exit 3)."""


class AnalysisError(LntError):
    """Данные прочитаны, но анализ невозможен (вырожденный сигнал и т.п.)."""
