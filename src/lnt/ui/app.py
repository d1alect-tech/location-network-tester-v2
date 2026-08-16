"""Фабрика локального веб-приложения LNT."""
# ruff: noqa: PLR0915

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

import anyio
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from lnt.app_paths import resolve_app_paths
from lnt.runtime.store import JobStore
from lnt.ui import (
    routes_analysis_v2,
    routes_catalog,
    routes_context,
    routes_device,
    routes_experiments,
    routes_jobs,
    routes_profiles,
    routes_quality,
    routes_research,
    routes_sessions,
    routes_statistics,
)
from lnt.ui.dependencies import AppServices, install_services
from lnt.ui.jobs import JobManager
from lnt.ui.operations import JobBackend, LntBackend
from lnt.ui.research_jobs import ResearchJobService
from lnt.ui.security import LocalSecurityMiddleware, create_security_context

_STATIC: Final = Path(__file__).with_name("static")


def create_app(
    *,
    root: Path,
    backend: JobBackend | None = None,
    catalog_db: Path | None = None,
    runtime_db: Path | None = None,
) -> FastAPI:
    """Создаёт изолированный экземпляр панели для указанного каталога сессий."""
    security = create_security_context(_STATIC)
    hashed_app_name = f"app.{security.static_asset_hash}.js"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Устанавливает сервисы приложения и освобождает рабочий поток."""
        await anyio.Path(root).mkdir(parents=True, exist_ok=True)
        runtime_path = runtime_db if runtime_db is not None else resolve_app_paths().runtime_db
        store = JobStore(runtime_path)
        store.interrupt_nonterminal()
        manager = JobManager(
            backend=backend if backend is not None else LntBackend(),
            root=root,
            store=store,
        )
        research_jobs = ResearchJobService(store)
        install_services(
            app,
            AppServices(
                root=root,
                catalog_db=(
                    catalog_db if catalog_db is not None else root / ".lnt" / "catalog.sqlite3"
                ),
                runtime_db=runtime_path,
                jobs=manager,
                research_jobs=research_jobs,
            ),
        )
        app.state.lnt_security = security
        try:
            yield
        finally:
            research_jobs.close()
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
    app.state.lnt_security = security
    app.add_middleware(LocalSecurityMiddleware)
    app.include_router(routes_sessions.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_catalog.router)
    app.include_router(routes_context.router)
    app.include_router(routes_profiles.router)
    app.include_router(routes_analysis_v2.router)
    app.include_router(routes_device.router)
    app.include_router(routes_experiments.router)
    app.include_router(routes_statistics.router)
    app.include_router(routes_research.router)
    app.include_router(routes_quality.router)

    def hashed_app() -> FileResponse:
        response = FileResponse(_STATIC / "app.js", media_type="text/javascript")
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    app.get(f"/static/{hashed_app_name}", include_in_schema=False)(hashed_app)
    app.mount("/static/v2", StaticFiles(directory=_STATIC / "v2"), name="static_v2")
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    def index_v2() -> Response:
        """Возвращает главную страницу локальной панели v2."""
        index_path = _STATIC / "v2" / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="v2 index.html not found")
        html = index_path.read_text(encoding="utf-8")
        response = Response(html, media_type="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    app.get("/v2/", include_in_schema=False)(index_v2)
    app.get("/v2", include_in_schema=False)(index_v2)

    def index() -> Response:
        """Возвращает главную страницу локальной панели."""
        html = (_STATIC / "index.html").read_text(encoding="utf-8")
        html = html.replace(
            '<html lang="ru">',
            f'<html lang="ru" data-build-id="{security.build_id}">',
        )
        html = html.replace("/static/app.js", f"/static/{hashed_app_name}")
        response = Response(html, media_type="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    app.get("/", include_in_schema=False)(index)

    def showcase() -> Response:
        """Возвращает страницу витрины дизайн-системы."""
        html = (_STATIC / "showcase.html").read_text(encoding="utf-8")
        response = Response(html, media_type="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    app.get("/showcase", include_in_schema=False)(showcase)
    return app
