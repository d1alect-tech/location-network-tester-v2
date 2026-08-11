"""Типизированные ошибки вычисления спектрограмм."""

from pathlib import Path

from lnt.errors import InputError


class SpectrogramLimitError(InputError):
    """Запрос превысил один из пределов безопасного вычисления."""

    def __init__(self, limit_kind: str, requested: float, maximum: float) -> None:
        """Фиксирует имя, запрос и допустимый максимум."""
        super().__init__(
            f"спектрограмма: превышен предел {limit_kind}: {requested:g} > {maximum:g}",
        )
        self.limit_kind: str = limit_kind
        self.requested: float = requested
        self.maximum: float = maximum


class SpectrogramCancelledError(InputError):
    """Вычисление отменено между ограниченными порциями работы."""

    def __init__(self) -> None:
        """Создаёт стабильную ошибку отмены."""
        super().__init__("спектрограмма: вычисление отменено")


class SpectrogramArtifactError(InputError):
    """Сохранённый обзор отсутствует, повреждён или несовместим."""

    def __init__(self, path: Path, reason_code: str) -> None:
        """Фиксирует путь и причину повреждения."""
        super().__init__(f"артефакт спектрограммы повреждён: {path} ({reason_code})")
        self.path: Path = path
        self.reason_code: str = reason_code
