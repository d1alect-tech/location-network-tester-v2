"""Маршруты чтения состояния и дисковых сессий панели.

Обработчики синхронны: FastAPI выполняет файловый ввод-вывод payload-функций
во внешнем пуле потоков, не блокируя цикл событий.
"""

from typing import Annotated, TypedDict

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from lnt.acquire import DEFAULT_RANGE_V, DEFAULT_SAMPLE_RATE_HZ, RANGE_CODES
from lnt.errors import InputError
from lnt.signals import PROFILES
from lnt.ui import payloads
from lnt.ui.dependencies import (
    AppServices,
    get_services,
    map_domain_error,
    resolve_session_or_404,
)
from lnt.ui.security import get_security_context


class HealthPayload(TypedDict):
    """Ответ проверки доступности API."""

    status: str
    build_id: str


class SimulateDefaults(TypedDict):
    """Параметры новой синтетической задачи по умолчанию."""

    duration_s: float
    sample_rate_hz: float
    seed: int
    repeat: int
    interval_s: float


class CaptureDefaults(TypedDict):
    """Параметры новой задачи захвата по умолчанию."""

    duration_s: float
    sample_rate_hz: float
    range_v: float
    repeat: int
    interval_s: float


class OperationDefaults(TypedDict):
    """Набор параметров операций по умолчанию."""

    simulate: SimulateDefaults
    capture: CaptureDefaults
    ranges: list[float]


class ConfigPayload(TypedDict):
    """Конфигурация, необходимая клиенту панели."""

    root: str
    profiles: list[str]
    defaults: OperationDefaults
    build_id: str
    mutation_nonce: str
    static_asset_hash: str
    static_assets: dict[str, str]


router = APIRouter(prefix="/api")

Services = Annotated[AppServices, Depends(get_services)]
SpectrumLimit = Annotated[int, Query(ge=16, le=20_000)]
WaveformLimit = Annotated[int, Query(ge=16, le=4_000)]
Channel = Annotated[str, Query(pattern=r"^ch[12]$")]


@router.get("/health")
def health(_services: Services, request: Request) -> HealthPayload:
    """Подтверждает готовность API и установленных сервисов."""
    return {"status": "ok", "build_id": get_security_context(request).build_id}


@router.get("/config")
def config(services: Services, request: Request) -> ConfigPayload:
    """Возвращает корень хранилища и доступные настройки операций."""
    security = get_security_context(request)
    return {
        "root": str(services.root),
        "profiles": list(PROFILES),
        "defaults": {
            "simulate": {
                "duration_s": 2.4,
                "sample_rate_hz": 500_000.0,
                "seed": 6022,
                "repeat": 1,
                "interval_s": 0.0,
            },
            "capture": {
                "duration_s": 2.4,
                "sample_rate_hz": DEFAULT_SAMPLE_RATE_HZ,
                "range_v": DEFAULT_RANGE_V,
                "repeat": 1,
                "interval_s": 0.0,
            },
            "ranges": list(RANGE_CODES),
        },
        "build_id": security.build_id,
        "mutation_nonce": security.mutation_nonce,
        "static_asset_hash": security.static_asset_hash,
        "static_assets": {"app": f"/static/app.{security.static_asset_hash}.js"},
    }


@router.get("/sessions")
def sessions(services: Services) -> JSONResponse:
    """Возвращает краткий список доступных дисковых сессий."""
    return JSONResponse(payloads.sessions_payload(services.root))


@router.get("/sessions/{name}")
def session_detail(name: str, services: Services) -> JSONResponse:
    """Возвращает манифест, анализ и доступность графиков сессии."""
    resolve_session_or_404(services.root, name)
    try:
        return JSONResponse(payloads.session_detail_payload(services.root, name))
    except InputError as error:
        raise map_domain_error(error) from error


@router.get("/sessions/{name}/spectrum")
def spectrum(
    name: str,
    services: Services,
    max_points: SpectrumLimit = 5_000,
) -> JSONResponse:
    """Возвращает ограниченный спектр существующей сессии."""
    resolve_session_or_404(services.root, name)
    try:
        return JSONResponse(
            payloads.spectrum_payload(services.root, name, max_points=max_points),
        )
    except InputError as error:
        raise map_domain_error(error) from error


@router.get("/sessions/{name}/waveform")
def waveform(
    name: str,
    services: Services,
    channel: Channel = "ch1",
    max_points: WaveformLimit = 4_000,
) -> JSONResponse:
    """Возвращает ограниченную форму волны выбранного канала."""
    resolve_session_or_404(services.root, name)
    try:
        return JSONResponse(
            payloads.waveform_payload(
                services.root,
                name,
                channel=channel,
                max_points=max_points,
            ),
        )
    except InputError as error:
        raise map_domain_error(error) from error
