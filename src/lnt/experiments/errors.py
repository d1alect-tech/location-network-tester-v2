"""Типизированные ошибки схемы и хранения экспериментов."""

from typing import Final, override

from lnt.errors import InputError


class ExperimentValidationError(InputError):
    """Нарушен машиночитаемый контракт experiment schema 1."""

    def __init__(self, reason_code: str, detail: str) -> None:
        """Сохраняет стабильный код и локализованную деталь."""
        self.reason_code: str = reason_code
        self.detail: str = detail
        super().__init__(self.__str__())

    @override
    def __str__(self) -> str:
        """Возвращает русское сообщение boundary-слою."""
        return f"эксперимент: {self.detail}"


class ExperimentConflictError(InputError):
    """Ожидаемая revision не совпала с сохранённой."""

    reason_code: Final = "experiment_revision_conflict"

    def __init__(self, expected_revision: int, actual_revision: int) -> None:
        """Сохраняет ожидаемую и фактическую revisions."""
        self.expected_revision: int = expected_revision
        self.actual_revision: int = actual_revision
        super().__init__(self.__str__())

    @override
    def __str__(self) -> str:
        """Возвращает русское описание конфликта."""
        return (
            "эксперимент: конфликт revision: ожидалась "
            f"{self.expected_revision}, сохранена {self.actual_revision}"
        )


class ExperimentChainError(InputError):
    """Append-only журнал эксперимента повреждён."""

    def __init__(self, reason_code: str, detail: str) -> None:
        """Сохраняет причину повреждения цепочки."""
        self.reason_code: str = reason_code
        self.detail: str = detail
        super().__init__(self.__str__())

    @override
    def __str__(self) -> str:
        """Возвращает русское описание повреждения."""
        return f"эксперимент: журнал revisions: {self.detail}"
