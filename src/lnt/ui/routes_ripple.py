"""Read-only HTTP-раздача сохранённого сайдкара ripple.json сессии.

Контракт (поправки исполнения №6): GET никогда не считает и не мутирует —
отдаются сохранённые байты после проверки схемы, типа файла и хэшей входов;
absent=404, corrupt/stale/schema-incompatible=409, ambiguous=409,
unsafe ID=422; параметры запроса не принимаются, nonce не нужен.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from lnt.analysis_v2.artifact_inputs import sha256_file
from lnt.analysis_v2.ripple_write import SIDECAR_FILENAME
from lnt.errors import InputError
from lnt.manifest import manifest_from_json
from lnt.safe_paths import ensure_safe_filename, is_linked_path
from lnt.ui.dependencies import AppServices, get_services, resolve_session_or_404
from lnt.ui.models_ripple import RippleArtifact, RippleSchemaError, parse_ripple_artifact

if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter(prefix="/api/sessions", tags=["ripple"])
Services = Annotated[AppServices, Depends(get_services)]
_MEDIA_TYPE_JSON: Final = "application/json"
_MANIFEST_FILENAME: Final = "manifest.json"
_STALE_INPUT: Final = "stale_input"


@router.get("/{session_name}/ripple")
def get_ripple_artifact(session_name: str, request: Request, services: Services) -> Response:
    """Отдаёт сохранённый ripple.json как есть; вычислений и мутаций нет."""
    if request.query_params:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "GET ripple не принимает параметры запроса"
        )
    session_dir = resolve_session_or_404(services.root, session_name)
    sidecar = session_dir / SIDECAR_FILENAME
    if is_linked_path(sidecar):
        raise _conflict("unsafe_sidecar", "ripple.json не должен быть ссылкой")
    if not sidecar.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"detail": "ripple-артефакт не построен", "reason": "not_built"},
        )
    if not sidecar.is_file():
        raise _conflict("corrupt", "ripple.json не является обычным файлом")
    try:
        data = sidecar.read_bytes()
        artifact = parse_ripple_artifact(data.decode("utf-8"))
    except RippleSchemaError as error:
        raise _conflict(error.reason, str(error)) from error
    except UnicodeDecodeError as error:
        raise _conflict("corrupt", "ripple.json не является UTF-8") from error
    except OSError as error:
        raise _conflict("corrupt", f"ripple.json не читается: {error}") from error
    _verify_current_inputs(session_dir, artifact)
    return Response(
        content=data,
        media_type=_MEDIA_TYPE_JSON,
        headers={"Cache-Control": "no-store"},
    )


def _verify_current_inputs(session_dir: Path, artifact: RippleArtifact) -> None:
    """Свежесть входов: manifest.json и ch1 сессии совпадают с хэшами сайдкара."""
    manifest_path = session_dir / _MANIFEST_FILENAME
    _match_digest(manifest_path, artifact.manifest_sha256)
    try:
        manifest = manifest_from_json(manifest_path.read_text(encoding="utf-8"))
    except (InputError, OSError, UnicodeDecodeError) as error:
        raise _conflict(
            _STALE_INPUT, f"manifest.json не читается для сверки входов: {error}"
        ) from error
    ch1_name = ensure_safe_filename(manifest.ch1.filename, label="ch1: имя файла")
    _match_digest(session_dir / ch1_name, artifact.ch1_sha256)


def _match_digest(path: Path, expected: str) -> None:
    """Хэш входа обязан совпасть с записанным в сайдкаре, иначе результат устарел."""
    try:
        actual = sha256_file(path)
    except OSError as error:
        raise _conflict(_STALE_INPUT, f"вход сессии недоступен: {path.name}") from error
    if actual != expected:
        raise _conflict(_STALE_INPUT, f"вход сессии изменился после публикации: {path.name}")


def _conflict(reason: str, message: str) -> HTTPException:
    """409 со структурной причиной: код машины + человекочитаемое пояснение."""
    return HTTPException(status.HTTP_409_CONFLICT, detail={"detail": message, "reason": reason})
