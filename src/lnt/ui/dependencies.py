"""Зависимости FastAPI и единое преобразование ошибок панели."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fastapi import FastAPI, HTTPException, Request, status

from lnt.errors import InputError
from lnt.runtime.scheduler import AnalysisQueueFullError
from lnt.ui.jobs import (
    JobBusyError,
    JobManager,
    JobNotCancellableError,
    UnknownJobError,
)
from lnt.ui.research_jobs import ResearchJobService
from lnt.ui.security import MUTATION_NONCE_HEADER, require_mutation_nonce
from lnt.ui.sessions import resolve_session_dir

CSRF_HEADER: Final = MUTATION_NONCE_HEADER
CSRF_VALUE: Final = "deprecated-static-value-not-authorized"

_SESSION_NAME_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


@dataclass(frozen=True, slots=True, kw_only=True)
class AppServices:
    """Сервисы, принадлежащие одному экземпляру приложения панели."""

    root: Path
    catalog_db: Path
    runtime_db: Path
    jobs: JobManager
    research_jobs: ResearchJobService | None = None


def install_services(app: FastAPI, services: AppServices) -> None:
    """Сохраняет типизированные сервисы в состоянии приложения."""
    app.state.lnt_services = services
    if not hasattr(app.state, "lnt_security"):
        from lnt.ui.security import create_security_context  # noqa: PLC0415

        app.state.lnt_security = create_security_context(Path(__file__).with_name("static"))


def get_services(request: Request) -> AppServices:
    """Возвращает сервисы приложения или сообщает об ошибке инициализации."""
    try:
        services: AppServices = request.app.state.lnt_services
    except AttributeError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="сервисы не инициализированы",
        ) from error
    return services


def require_csrf(request: Request) -> None:
    """Совместимое имя dependency: требует nonce текущего запуска."""
    require_mutation_nonce(request)


def http_not_found(message: str) -> HTTPException:
    """Создаёт HTTP-ошибку отсутствующего ресурса."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def http_conflict(message: str) -> HTTPException:
    """Создаёт HTTP-ошибку конфликта состояния."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def http_unprocessable(message: str) -> HTTPException:
    """Создаёт HTTP-ошибку некорректного входа."""
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def map_domain_error(exc: Exception) -> HTTPException:
    """Преобразует ожидаемые синхронные ошибки маршрутов в HTTP-ошибки."""
    match exc:
        case InputError():
            return http_unprocessable(str(exc))
        case JobBusyError():
            return http_conflict("уже выполняется задача")
        case AnalysisQueueFullError():
            return http_conflict(str(exc))
        case UnknownJobError():
            return http_not_found("задача не найдена")
        case JobNotCancellableError():
            return http_conflict("задача уже завершена")
        case _:
            raise exc


def resolve_session_or_404(root: Path, name: str) -> Path:
    """Разрешает сессию: безопасное отсутствующее имя даёт 404, прочие ошибки — 422."""
    try:
        return resolve_session_dir(root, name)
    except InputError as error:
        name_is_safe = (
            name not in {".", ".."}
            and "/" not in name
            and "\\" not in name
            and _SESSION_NAME_PATTERN.fullmatch(name) is not None
        )
        if name_is_safe and not (root / name).exists():
            raise http_not_found("сессия не найдена") from error
        raise http_unprocessable(str(error)) from error
