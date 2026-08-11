"""Bounded versioned experiment and protocol-run routes."""
# ruff: noqa: D103, TC001

from __future__ import annotations

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from lnt.acquisition_quality import AcquisitionQuality
from lnt.experiments import Experiment, ExperimentConflictError, ExperimentStore
from lnt.experiments.runner import AutoConfirmationRejectedError, CaptureArtifact, ProtocolRunner
from lnt.experiments.runner_models import ProtocolRunMode, ProtocolRunStatus
from lnt.experiments.runner_store import ProtocolRunStore
from lnt.runtime.scheduler import OperationScheduler
from lnt.ui.dependencies import AppServices, get_services
from lnt.ui.research_models import ExperimentWrite, RunConfirm, RunStart

router = APIRouter(prefix="/api/v2")
Services = Annotated[AppServices, Depends(get_services)]
PageSize = Annotated[int, Query(ge=1, le=200)]


def _cursor(raw: str | None) -> int:
    if raw is None:
        return 0
    try:
        return int(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode())
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(422, "некорректный cursor") from error


def _next(index: int, total: int) -> str | None:
    return (
        base64.urlsafe_b64encode(str(index).encode()).decode().rstrip("=")
        if index < total
        else None
    )


def _experiments(services: AppServices) -> ExperimentStore:
    return ExperimentStore(services.root)


def _load(store: ExperimentStore, experiment_id: str) -> Experiment:
    try:
        return store.load(experiment_id)
    except (KeyError, FileNotFoundError) as error:
        raise HTTPException(404, "эксперимент не найден") from error


@router.post("/experiments", status_code=201)
def create_experiment(request: ExperimentWrite, services: Services) -> JSONResponse:
    try:
        saved = _experiments(services).save(
            request.experiment, expected_revision=request.expected_revision
        )
    except ExperimentConflictError as error:
        raise HTTPException(409, {"code": error.reason_code, "detail": str(error)}) from error
    return JSONResponse(saved.model_dump(mode="json"), status_code=201)


@router.put("/experiments/{experiment_id}")
def update_experiment(
    experiment_id: str, request: ExperimentWrite, services: Services
) -> JSONResponse:
    if request.experiment.experiment_id != experiment_id:
        raise HTTPException(
            422, {"code": "experiment_id_mismatch", "detail": "id эксперимента не совпадает"}
        )
    try:
        saved = _experiments(services).save(
            request.experiment, expected_revision=request.expected_revision
        )
    except ExperimentConflictError as error:
        raise HTTPException(409, {"code": error.reason_code, "detail": str(error)}) from error
    return JSONResponse(saved.model_dump(mode="json"))


@router.get("/experiments")
def list_experiments(
    services: Services, page_size: PageSize = 50, cursor: str | None = None
) -> JSONResponse:
    start = _cursor(cursor)
    store = _experiments(services)
    ids = (
        tuple(sorted(path.name for path in store.root.iterdir() if path.is_dir()))
        if store.root.is_dir()
        else ()
    )
    page = ids[start : start + page_size]
    items = [store.load(item).model_dump(mode="json") for item in page]
    return JSONResponse({"items": items, "next_cursor": _next(start + len(page), len(ids))})


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, services: Services) -> JSONResponse:
    return JSONResponse(_load(_experiments(services), experiment_id).model_dump(mode="json"))


@router.get("/experiments/{experiment_id}/revisions")
def revisions(
    experiment_id: str, services: Services, page_size: PageSize = 50, cursor: str | None = None
) -> JSONResponse:
    history = _experiments(services).history(experiment_id)
    start = _cursor(cursor)
    page = history[start : start + page_size]
    return JSONResponse(
        {
            "items": [item.model_dump(mode="json") for item in page],
            "next_cursor": _next(start + len(page), len(history)),
        }
    )


def _component_page(
    experiment_id: str, component: str, services: AppServices, size: int, raw: str | None
) -> JSONResponse:
    experiment = _load(_experiments(services), experiment_id)
    values = experiment.members if component == "members" else experiment.steps
    start = _cursor(raw)
    page = values[start : start + size]
    return JSONResponse(
        {
            "items": [item.model_dump(mode="json") for item in page],
            "next_cursor": _next(start + len(page), len(values)),
        }
    )


@router.get("/experiments/{experiment_id}/members")
def members(
    experiment_id: str, services: Services, page_size: PageSize = 50, cursor: str | None = None
) -> JSONResponse:
    return _component_page(experiment_id, "members", services, page_size, cursor)


@router.get("/experiments/{experiment_id}/steps")
def steps(
    experiment_id: str, services: Services, page_size: PageSize = 50, cursor: str | None = None
) -> JSONResponse:
    return _component_page(experiment_id, "steps", services, page_size, cursor)


def _runner(services: AppServices) -> ProtocolRunner:
    quality = AcquisitionQuality(
        quality_thresholds_version=1,
        channels=(),
        findings=(),
        maximum_callback_gap_s=0.0,
        short_block_count=0,
    )
    return ProtocolRunner(
        store=ProtocolRunStore(services.root.parent / "protocol-runs"),
        scheduler=OperationScheduler(cpu_workers=1, cpu_queue_limit=1),
        preflight=lambda: (),
        capture=lambda order: CaptureArtifact(
            session_id=f"simulator-{order}",
            storage_ref=f"simulator-{order}",
            artifact_refs=(),
            quality=quality,
        ),
    )


@router.post("/experiments/{experiment_id}/runs", status_code=201)
def start_run(experiment_id: str, request: RunStart, services: Services) -> JSONResponse:
    runner = _runner(services)
    try:
        record = runner.start(
            run_id=request.run_id,
            experiment=_load(_experiments(services), experiment_id),
            mode=ProtocolRunMode(request.mode),
            seed=request.seed,
        )
    finally:
        runner.close()
    return JSONResponse(record.model_dump(mode="json"), status_code=201)


@router.get("/protocol-runs/{run_id}")
def run_status(run_id: str, services: Services) -> JSONResponse:
    try:
        record = ProtocolRunStore(services.root.parent / "protocol-runs").load(run_id)
    except FileNotFoundError as error:
        raise HTTPException(404, "запуск протокола не найден") from error
    return JSONResponse(record.model_dump(mode="json"))


@router.post("/protocol-runs/{run_id}/confirm")
def confirm_run(run_id: str, request: RunConfirm, services: Services) -> JSONResponse:
    runner = _runner(services)
    try:
        record = runner.confirm(run_id, actor=request.actor, auto_confirm=request.auto_confirm)
    except AutoConfirmationRejectedError as error:
        raise HTTPException(403, {"code": error.code, "detail": str(error)}) from error
    finally:
        runner.close()
    return JSONResponse(record.model_dump(mode="json"))


@router.post("/protocol-runs/{run_id}/resume")
def resume_run(run_id: str, services: Services) -> JSONResponse:
    """Resume a persisted run without crossing confirmation boundaries."""
    runner = _runner(services)
    try:
        record = runner.resume(run_id)
    except FileNotFoundError as error:
        raise HTTPException(404, "запуск протокола не найден") from error
    finally:
        runner.close()
    return JSONResponse(record.model_dump(mode="json"))


@router.post("/protocol-runs/{run_id}/cancel", status_code=202)
def cancel_run(run_id: str, services: Services) -> JSONResponse:
    """Persist cancellation at the current safe protocol boundary."""
    store = ProtocolRunStore(services.root.parent / "protocol-runs")
    try:
        record = store.load(run_id)
    except FileNotFoundError as error:
        raise HTTPException(404, "запуск протокола не найден") from error
    if record.status not in {ProtocolRunStatus.COMPLETED, ProtocolRunStatus.CANCELLED}:
        record = store.record(
            record.model_copy(
                update={
                    "revision": record.revision + 1,
                    "status": ProtocolRunStatus.CANCELLED,
                }
            ),
            transition="run_cancelled",
            actor="user:api",
        )
    return JSONResponse(record.model_dump(mode="json"), status_code=202)
