"""Bounded artifact-backed HTTP API for immutable analysis recipes."""

from __future__ import annotations

import csv
import io
from dataclasses import replace
from typing import Annotated, Final

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from lnt.analysis_store import AnalysisRecipe
from lnt.analysis_v2 import AnalysisOrchestrator, DefaultAnalysisEngine
from lnt.analysis_v2.jobs import AnalysisJobStore
from lnt.analysis_v2.recipes import RecipeCatalog
from lnt.errors import InputError
from lnt.ui.analysis_v2_files import (
    read_default_pointer,
    validate_job_id,
    validate_session_inputs,
    validate_sha256,
    verified_output,
    write_default_pointer,
)
from lnt.ui.decimation import min_max_envelope
from lnt.ui.dependencies import (
    AppServices,
    get_services,
    http_not_found,
    http_unprocessable,
    require_csrf,
    resolve_session_or_404,
)
from lnt.ui.models_analysis_v2 import (  # noqa: TC001 - FastAPI resolves request models
    AnalysisRunRequest,
    RecipeCloneRequest,
    RecipeCreateRequest,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis-v2"])
Services = Annotated[AppServices, Depends(get_services)]
MAX_POINTS: Final = 50_000
MIN_POINTS: Final = 4
MAX_RANGE: Final = 10_000_000.0


@router.post("/recipes", dependencies=[Depends(require_csrf)], status_code=201)
def create_recipe(request: RecipeCreateRequest, services: Services) -> dict[str, object]:
    """Persist one immutable recipe."""
    recipe = AnalysisRecipe.from_mapping(request.recipe)
    return (
        RecipeCatalog(services.root / ".lnt" / "analysis-recipes")
        .create(request.name, recipe)
        .payload()
    )


@router.get("/recipes")
def list_recipes(services: Services) -> dict[str, object]:
    """List all immutable recipes; a tampered catalog fails closed."""
    try:
        items = RecipeCatalog(services.root / ".lnt" / "analysis-recipes").list()
    except InputError as error:
        raise http_unprocessable(str(error)) from error
    return {"items": [item.payload() for item in items]}


@router.post("/recipes/{recipe_id}/clone", dependencies=[Depends(require_csrf)], status_code=201)
def clone_recipe(
    recipe_id: str, request: RecipeCloneRequest, services: Services
) -> dict[str, object]:
    """Clone a recipe without changing its source."""
    validate_sha256(recipe_id, label="recipe_id")
    try:
        return (
            RecipeCatalog(services.root / ".lnt" / "analysis-recipes")
            .clone(recipe_id, request.name)
            .payload()
        )
    except FileNotFoundError as error:
        raise http_not_found("рецепт анализа не найден") from error
    except InputError as error:
        raise http_unprocessable(str(error)) from error


@router.delete("/recipes/{recipe_id}", dependencies=[Depends(require_csrf)])
def reject_recipe_delete(recipe_id: str) -> None:
    """Reject deletion because published artifacts may reference recipes."""
    validate_sha256(recipe_id, label="recipe_id")
    raise HTTPException(
        status.HTTP_409_CONFLICT, f"рецепт {recipe_id} неизменяем и может быть указан в artifact"
    )


@router.post("/runs", dependencies=[Depends(require_csrf)], status_code=202)
def run_analysis(request: AnalysisRunRequest, services: Services) -> dict[str, str | int | None]:
    """Run through the durable job seam; computation remains cooperative and bounded."""
    session_dir = resolve_session_or_404(services.root, request.session)
    try:
        recipe = RecipeCatalog(services.root / ".lnt" / "analysis-recipes").get(request.recipe_id)
    except FileNotFoundError as error:
        raise http_not_found("рецепт анализа не найден") from error
    except InputError as error:
        raise http_unprocessable(str(error)) from error
    analysis_recipe = recipe.recipe
    if not isinstance(analysis_recipe, AnalysisRecipe):
        raise http_unprocessable("выполнение рецепта characterization пока не подключено")
    validate_session_inputs(
        session_dir, analysis_recipe.channels, make_default=request.make_default
    )
    jobs = AnalysisJobStore(services.root / ".lnt" / "analysis-jobs")
    job = jobs.create()

    def progress(stage: str, completed: int, total: int) -> None:
        jobs.write(replace(job, stage=stage, completed=completed, total=total))

    try:
        result = AnalysisOrchestrator(engine=DefaultAnalysisEngine()).run(
            session_dir,
            analysis_recipe,
            progress=progress,
            project_legacy=request.make_default,
        )
        if request.make_default:
            write_default_pointer(session_dir, recipe.recipe_id, result.artifact_key)
    except (InputError, OSError, ValueError) as error:
        failed = replace(job, status="failed", stage="done", error=str(error))
        jobs.write(failed)
        return failed.payload()
    succeeded = replace(
        job,
        status="succeeded",
        stage="done",
        completed=1,
        total=1,
        artifact_key=result.artifact_key,
    )
    jobs.write(succeeded)
    return succeeded.payload()


@router.get("/runs/{job_id}")
def analysis_status(job_id: str, services: Services) -> dict[str, str | int | None]:
    """Return the latest durable analysis job snapshot."""
    validate_job_id(job_id)
    try:
        return AnalysisJobStore(services.root / ".lnt" / "analysis-jobs").get(job_id).payload()
    except OSError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "задача анализа не найдена") from error


@router.get("/sessions/{session_name}/artifacts/{artifact_key}/{filename}")
def artifact_file(
    session_name: str, artifact_key: str, filename: str, services: Services
) -> Response:
    """Serve bytes only after manifest integrity verification."""
    path = verified_output(services, session_name, artifact_key, filename)
    media = "application/json" if filename.endswith(".json") else "application/octet-stream"
    return Response(path.read_bytes(), media_type=media)


@router.get("/sessions/{session_name}/artifacts/{artifact_key}/plot/spectrum")
def spectrum_plot(
    session_name: str,
    artifact_key: str,
    services: Services,
    max_points: Annotated[int, Query()] = 5000,
) -> dict[str, object]:
    """Return a bounded extrema-preserving spectrum payload."""
    return _spectrum_payload(services, session_name, artifact_key, None, None, max_points)


@router.get("/sessions/{session_name}/artifacts/{artifact_key}/plot/spectrum/zoom")
def spectrum_zoom(  # noqa: PLR0913, PLR0917 - FastAPI path/query boundary
    session_name: str,
    artifact_key: str,
    services: Services,
    start: float,
    end: float,
    max_points: Annotated[int, Query()] = 5000,
) -> dict[str, object]:
    """Return range-selected extrema-preserving spectrum points."""
    if end <= start or end - start > MAX_RANGE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "диапазон zoom вне предела")
    return _spectrum_payload(services, session_name, artifact_key, start, end, max_points)


@router.get("/sessions/{session_name}/.lnt-default-analysis.json")
def default_analysis_pointer(session_name: str, services: Services) -> dict[str, str]:
    """Return a default pointer only after pointer and artifact verification."""
    return read_default_pointer(services, session_name)


def _spectrum_payload(  # noqa: PLR0913, PLR0917 - shared route boundary
    services: AppServices,
    session_name: str,
    artifact_key: str,
    start: float | None,
    end: float | None,
    max_points: int,
) -> dict[str, object]:
    if not MIN_POINTS <= max_points <= MAX_POINTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "max_points вне предела 4..50000"
        )
    spectrum_path = verified_output(services, session_name, artifact_key, "spectrum.csv")
    rows = tuple(csv.DictReader(io.StringIO(spectrum_path.read_text(encoding="utf-8"))))
    x = np.asarray([float(row["frequency_hz"]) for row in rows], dtype=np.float64)
    y = np.asarray([float(row["psd_v2_per_hz"]) for row in rows], dtype=np.float64)
    if start is not None and end is not None:
        selected = (x >= start) & (x <= end)
        x, y = x[selected], y[selected]
    series = min_max_envelope(x, y, max_points=max_points)
    return {"x": series.x, "y": series.y, "point_count": series.point_count}
