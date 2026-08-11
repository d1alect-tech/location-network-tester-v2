"""Фабрика локального веб-приложения LNT."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final, override

import anyio
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from lnt.ui import routes_catalog, routes_context, routes_jobs, routes_profiles, routes_sessions
from lnt.ui.dependencies import AppServices, install_services
from lnt.ui.jobs import JobManager
from lnt.ui.operations import JobBackend, LntBackend

_STATIC: Final = Path(__file__).with_name("static")


class _NoCacheMiddleware(BaseHTTPMiddleware):
    """Запрещает залипание UI в кэше браузера: ответы всегда ревалидируются (ETag/304)."""

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(*, root: Path, backend: JobBackend | None = None) -> FastAPI:
    """Создаёт изолированный экземпляр панели для указанного каталога сессий."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Устанавливает сервисы приложения и освобождает рабочий поток."""
        await anyio.Path(root).mkdir(parents=True, exist_ok=True)
        manager = JobManager(
            backend=backend if backend is not None else LntBackend(),
            root=root,
        )
        install_services(app, AppServices(root=root, jobs=manager))
        try:
            yield
        finally:
            await manager.aclose()

    app = FastAPI(
        title="LNT",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    async def request_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        """Возвращает только компактные пути ошибочных параметров на русском."""
        locations = ",".join(
            ".".join(str(part) for part in item["loc"] if part != "body") for item in error.errors()
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": f"некорректные параметры запроса: {locations}"},
        )

    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        content = error.detail if isinstance(error.detail, dict) else {"detail": error.detail}
        return JSONResponse(status_code=error.status_code, content=content)

    app.exception_handler(RequestValidationError)(request_validation_error)
    app.exception_handler(HTTPException)(http_error)
    app.add_middleware(_NoCacheMiddleware)
    app.include_router(routes_sessions.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_catalog.router)
    app.include_router(routes_context.router)
    app.include_router(routes_profiles.router)
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    def index() -> FileResponse:
        """Возвращает главную страницу локальной панели."""
        return FileResponse(_STATIC / "index.html", media_type="text/html")

    app.get("/", include_in_schema=False)(index)
    return app
