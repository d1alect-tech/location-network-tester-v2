"""Типизированные отказы потоковой оценки PSD."""

from __future__ import annotations

from lnt.errors import InputError


class PsdError(InputError):
    """Базовая ошибка входа или выполнения PSD."""


class PsdSettingsError(PsdError):
    """Настройки PSD нарушают явный контракт метода."""


class PsdDataError(PsdError):
    """Массив данных пуст, короток или не содержит конечные значения."""


class PsdCancelledError(PsdError):
    """Расчёт PSD отменён между ограниченными порциями."""
