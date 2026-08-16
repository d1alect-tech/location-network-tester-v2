"""Локальная same-origin граница безопасности веб-панели."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from importlib import metadata
from typing import TYPE_CHECKING, Final, override
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from lnt.analysis_store.identity import CodeIdentity

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.responses import Response

MUTATION_NONCE_HEADER: Final = "X-LNT-Mutation-Nonce"
MAX_REQUEST_BODY_BYTES: Final = 1_048_576
_MUTATING_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost"})
_CSP: Final = (
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityContext:
    """Неизменяемые идентичности одного запуска приложения."""

    mutation_nonce: str
    build_id: str
    static_asset_hash: str


def create_security_context(static_dir: Path) -> SecurityContext:
    """Создаёт nonce запуска и content/code identities."""
    identity = CodeIdentity.current()
    code_hash = hashlib.sha256(identity.identity_string.encode()).hexdigest()[:16]
    build_id = f"{metadata.version('lnt')}+{code_hash}"
    asset_digest = hashlib.sha256()
    for script in sorted(static_dir.glob("*.js")):
        asset_digest.update(script.name.encode())
        asset_digest.update(script.read_bytes())
    asset_hash = asset_digest.hexdigest()[:16]
    return SecurityContext(
        mutation_nonce=secrets.token_urlsafe(32),
        build_id=build_id,
        static_asset_hash=asset_hash,
    )


def get_security_context(request: Request) -> SecurityContext:
    """Возвращает контекст безопасности текущего приложения."""
    context: SecurityContext = request.app.state.lnt_security
    return context


def require_mutation_nonce(request: Request) -> None:
    """Проверяет непредсказуемый nonce текущего запуска."""
    context = get_security_context(request)
    supplied = request.headers.get(MUTATION_NONCE_HEADER, "")
    if not secrets.compare_digest(supplied, context.mutation_nonce):
        raise _forbidden(
            "mutation_nonce_invalid",
            "изменяющий запрос отклонён: неверный одноразовый nonce запуска",
        )


class LocalSecurityMiddleware(BaseHTTPMiddleware):
    """Проверяет loopback/same-origin и ставит защитные заголовки."""

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        host = request.url.hostname
        test_client = request.client is not None and request.client.host == "testclient"
        if host not in _LOOPBACK_HOSTS and not (test_client and host == "testserver"):
            return _error_response("host_not_loopback", "запрос отклонён: Host не loopback")
        if request.method in _MUTATING_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and urlsplit(origin).hostname not in _LOOPBACK_HOSTS:
                return _error_response(
                    "origin_not_loopback",
                    "изменяющий запрос отклонён: Origin не loopback",
                )
            body = await request.body()
            if len(body) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={
                        "code": "request_body_too_large",
                        "detail": "тело запроса превышает допустимый размер",
                    },
                )
            try:
                require_mutation_nonce(request)
            except HTTPException as error:
                return JSONResponse(status_code=error.status_code, content=error.detail)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/static/") and "Cache-Control" not in response.headers:
            # Hashed assets in static/v2/assets should have long-cache headers
            if "/static/v2/assets/" in request.url.path:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-store"
        return response


def _forbidden(code: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": code, "detail": detail},
    )


def _error_response(code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"code": code, "detail": detail},
    )
